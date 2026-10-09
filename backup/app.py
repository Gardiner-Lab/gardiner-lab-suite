"""
Backup console for the Gardiner Lab suite.

A small admin interface for the backup system: choose where backups are
written, run one now, see what is held, download an archive, upload one from
another machine, and restore.

Two things shape the design:

* **Restores do not stop the stack.** They use SQLite's online backup API in
  reverse, which overwrites a live database safely while the applications hold
  it open. That avoids giving this service the Docker socket, which would make
  it root-equivalent on the host.

* **It is an administrative interface**, so everything behind the login can
  overwrite lab data. Sign-in reuses the Plasmid Editor's admin accounts rather
  than introducing another password, and every path that comes from the browser
  is validated against an allowed root before it is touched.
"""

import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import tempfile
import time
from datetime import timedelta
from functools import wraps
from pathlib import Path

import bcrypt
from flask import Flask, jsonify, request, send_file, session

APP_VERSION = '1.0.0'

CONFIG_DIR = Path(os.environ.get('CONFIG_STORE', '/config-store'))
SETTINGS_FILE = CONFIG_DIR / 'settings.json'
# Backups may only be written below these roots. The host mounts the network
# drive somewhere under one of them.
ALLOWED_ROOTS = [Path(p) for p in os.environ.get('ALLOWED_BACKUP_ROOTS', '/mnt:/backup').split(':') if p]
EDITOR_DB = Path(os.environ.get('EDITOR_DB', '/data/plasmid_editor.db'))

# The databases this console can restore, and where they live.
DATABASES = {
    'moclo.db': Path(os.environ.get('MOCLO_DB', '/moclo/moclo.db')),
    'parts.db': Path(os.environ.get('PARTS_DB', '/moclo/parts.db')),
    'plasmid_editor.db': Path(os.environ.get('EDITOR_DB', '/data/plasmid_editor.db')),
}

ARCHIVE_RE = re.compile(r'^lab-suite-\d{4}-\d{2}-\d{2}_\d{6}\.tar\.gz$')
MAX_UPLOAD = 2 * 1024 * 1024 * 1024  # 2 GiB

DEFAULTS = {
    'destination': os.environ.get('BACKUP_DEST', '/backup'),
    'hour': 2, 'minute': 30,
    'keep_daily': 14, 'keep_weekly': 8, 'keep_monthly': 12,
    'enabled': True,
}

app = Flask(__name__, static_folder=None)
app.config.update(
    SECRET_KEY=os.environ.get('SECRET_KEY', os.urandom(32).hex()),
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    SESSION_COOKIE_NAME='lab_backup_session',
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    MAX_CONTENT_LENGTH=MAX_UPLOAD,
)
if os.environ.get('SESSION_COOKIE_SECURE', '').lower() in ('1', 'true', 'yes'):
    app.config['SESSION_COOKIE_SECURE'] = True


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def load_settings() -> dict:
    data = dict(DEFAULTS)
    try:
        data.update(json.loads(SETTINGS_FILE.read_text()))
    except (OSError, ValueError):
        pass
    return data


def save_settings(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_FILE.with_suffix('.part')
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(SETTINGS_FILE)


def destination() -> Path:
    return Path(load_settings()['destination'])


def validate_destination(raw: str) -> Path:
    """A destination must be an absolute path under one of the allowed roots."""
    text = (raw or '').strip()
    if not text:
        raise ValueError('Give a path for the backup destination')
    path = Path(text)
    if not path.is_absolute():
        raise ValueError('The destination must be an absolute path, e.g. /mnt/labbackup/lab-suite')
    resolved = os.path.normpath(str(path))
    if not any(resolved == str(root) or resolved.startswith(str(root) + os.sep)
               for root in ALLOWED_ROOTS):
        allowed = ', '.join(str(r) for r in ALLOWED_ROOTS)
        raise ValueError(f'The destination must be under one of: {allowed}. '
                         'Mount the drive there on the server first.')
    return Path(resolved)


def archive_path(name: str) -> Path:
    """Resolve an archive name, refusing anything that is not a plain archive."""
    if not ARCHIVE_RE.match(name or ''):
        raise ValueError('Not a backup archive name')
    return destination() / name


# ---------------------------------------------------------------------------
# Authentication: the Plasmid Editor's admin accounts
# ---------------------------------------------------------------------------

def check_admin(username: str, password: str) -> bool:
    if not EDITOR_DB.exists():
        return False
    try:
        conn = sqlite3.connect(f'file:{EDITOR_DB}?mode=ro', uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        row = conn.execute('SELECT password_hash, is_admin FROM users WHERE username = ?',
                           ((username or '').strip(),)).fetchone()
        conn.close()
    except sqlite3.Error:
        return False
    if row is None or not row['is_admin']:
        return False
    try:
        return bcrypt.checkpw((password or '').encode(), row['password_hash'].encode())
    except (ValueError, TypeError):
        return False


def require_admin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get('admin'):
            return jsonify({'error': 'Sign in as an administrator first'}), 401
        return fn(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def disk_free(path: Path) -> dict:
    try:
        usage = shutil.disk_usage(path)
        return {'free': usage.free, 'total': usage.total}
    except OSError:
        return {'free': None, 'total': None}


def list_archives() -> list:
    dest = destination()
    out = []
    try:
        entries = sorted(dest.glob('lab-suite-*.tar.gz'), reverse=True)
    except OSError:
        return out
    for item in entries:
        try:
            stat = item.stat()
        except OSError:
            continue
        out.append({
            'name': item.name,
            'bytes': stat.st_size,
            'created_at': time.strftime('%Y-%m-%d %H:%M', time.localtime(stat.st_mtime)),
            'has_checksum': item.with_suffix(item.suffix + '.sha256').exists()
            or Path(str(item) + '.sha256').exists(),
        })
    return out


@app.route('/api/session')
def session_status():
    return jsonify({
        'authenticated': bool(session.get('admin')),
        'username': session.get('username'),
        'version': APP_VERSION,
    })


@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    username = data.get('username', '')
    if not check_admin(username, data.get('password', '')):
        time.sleep(1)       # blunt the obvious guessing attack
        return jsonify({'error': 'Not an administrator account, or the password is wrong'}), 401
    session.clear()
    session['admin'] = True
    session['username'] = username.strip()
    session.permanent = True
    return jsonify({'authenticated': True, 'username': session['username']})


@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'ok': True})


@app.route('/api/status')
@require_admin
def status():
    settings = load_settings()
    dest = Path(settings['destination'])
    marker = dest / '.backup-target'
    last = {}
    try:
        last = json.loads((dest / 'status.json').read_text())
    except (OSError, ValueError):
        pass
    archives = list_archives()
    return jsonify({
        'settings': settings,
        'allowed_roots': [str(r) for r in ALLOWED_ROOTS],
        'destination_exists': dest.is_dir(),
        'destination_marked': marker.exists(),
        'destination_writable': os.access(dest, os.W_OK) if dest.is_dir() else False,
        'disk': disk_free(dest),
        'last_run': last,
        'archive_count': len(archives),
        'newest': archives[0] if archives else None,
        'databases': {name: path.exists() for name, path in DATABASES.items()},
    })


@app.route('/api/archives')
@require_admin
def archives():
    return jsonify({'archives': list_archives(), 'destination': str(destination())})


# ---------------------------------------------------------------------------
# Settings and running a backup
# ---------------------------------------------------------------------------

@app.route('/api/settings', methods=['POST'])
@require_admin
def update_settings():
    data = request.get_json(silent=True) or {}
    settings = load_settings()
    try:
        if 'destination' in data:
            settings['destination'] = str(validate_destination(data['destination']))
        for key, low, high in (('hour', 0, 23), ('minute', 0, 59), ('keep_daily', 1, 365),
                               ('keep_weekly', 0, 520), ('keep_monthly', 0, 240)):
            if key in data:
                value = int(data[key])
                if not low <= value <= high:
                    raise ValueError(f'{key} must be between {low} and {high}')
                settings[key] = value
        if 'enabled' in data:
            settings['enabled'] = bool(data['enabled'])
    except (ValueError, TypeError) as exc:
        return jsonify({'error': str(exc)}), 400
    save_settings(settings)
    return jsonify({'settings': settings})


@app.route('/api/destination/prepare', methods=['POST'])
@require_admin
def prepare_destination():
    """
    Create the destination and mark it, which is what lets backups run.

    The marker is how an operator says "this really is the backup drive"; the
    nightly job refuses to write without it, so an unmounted network drive
    cannot be mistaken for the destination and silently fill the local disk.
    """
    data = request.get_json(silent=True) or {}
    try:
        dest = validate_destination(data.get('destination') or str(destination()))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    try:
        dest.mkdir(parents=True, exist_ok=True)
        probe = dest / '.write-test'
        probe.write_text('ok')
        probe.unlink()
    except OSError as exc:
        return jsonify({'error': f'Cannot write to {dest}: {exc}. '
                                 'Is the drive mounted on the server, and writable?'}), 400
    (dest / '.backup-target').write_text(
        'This directory is the backup destination for the Gardiner Lab tool suite.\n'
        f'Marked from the backup console on {time.strftime("%Y-%m-%d %H:%M:%S")}.\n\n'
        'The backup refuses to run if this file is missing, so that an unmounted\n'
        'network drive is never silently filled up instead.\n')
    settings = load_settings()
    settings['destination'] = str(dest)
    save_settings(settings)
    return jsonify({'ok': True, 'destination': str(dest)})


@app.route('/api/backup/run', methods=['POST'])
@require_admin
def run_backup():
    env = dict(os.environ, BACKUP_DEST=str(destination()))
    settings = load_settings()
    for key in ('keep_daily', 'keep_weekly', 'keep_monthly'):
        env[key.upper()] = str(settings[key])
    try:
        done = subprocess.run(['/usr/local/bin/backup.sh'], env=env, capture_output=True,
                              text=True, timeout=3600)
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'The backup took longer than an hour and was stopped'}), 500
    output = (done.stdout or '') + (done.stderr or '')
    if done.returncode != 0:
        return jsonify({'error': 'The backup failed', 'output': output}), 500
    return jsonify({'ok': True, 'output': output, 'archives': list_archives()})


# ---------------------------------------------------------------------------
# Archives: download, upload, verify, restore, delete
# ---------------------------------------------------------------------------

@app.route('/api/archives/<name>/download')
@require_admin
def download(name):
    try:
        path = archive_path(name)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    if not path.is_file():
        return jsonify({'error': 'No such archive'}), 404
    return send_file(path, as_attachment=True, download_name=name)


@app.route('/api/archives/upload', methods=['POST'])
@require_admin
def upload():
    """Take an archive from another machine, so a move is download then upload."""
    item = request.files.get('file')
    if item is None:
        return jsonify({'error': 'No file was uploaded'}), 400
    name = os.path.basename(item.filename or '')
    if not ARCHIVE_RE.match(name):
        return jsonify({'error': 'Expected a lab-suite-YYYY-MM-DD_HHMMSS.tar.gz archive'}), 400
    dest = destination()
    if not dest.is_dir():
        return jsonify({'error': f'{dest} is not available'}), 400
    target = dest / name
    staging = target.with_suffix('.part')
    item.save(staging)
    problem = inspect_archive(staging)
    if problem:
        staging.unlink(missing_ok=True)
        return jsonify({'error': f'That archive is not usable: {problem}'}), 400
    staging.replace(target)
    return jsonify({'ok': True, 'name': name, 'archives': list_archives()})


def inspect_archive(path: Path):
    """None if the archive unpacks and its databases pass an integrity check."""
    import tarfile
    try:
        with tarfile.open(path, 'r:gz') as tar:
            names = tar.getnames()
    except (tarfile.TarError, OSError) as exc:
        return f'it could not be opened ({exc})'
    if not any(n.endswith('.db') for n in names):
        return 'it contains no databases'
    if any(n.startswith('/') or '..' in Path(n).parts for n in names):
        return 'it contains unsafe paths'
    return None


def extract_databases(path: Path, into: Path) -> dict:
    """Unpack just the databases, and integrity-check each one."""
    import tarfile
    found = {}
    with tarfile.open(path, 'r:gz') as tar:
        for member in tar.getmembers():
            parts = Path(member.name).parts
            if not member.isfile() or len(parts) < 3 or parts[1] != 'databases':
                continue
            if '..' in parts or member.name.startswith('/'):
                continue
            name = parts[-1]
            if name not in DATABASES:
                continue
            source = tar.extractfile(member)
            if source is None:
                continue
            out = into / name
            out.write_bytes(source.read())
            found[name] = out
    return found


@app.route('/api/archives/<name>/verify', methods=['POST'])
@require_admin
def verify(name):
    try:
        path = archive_path(name)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    if not path.is_file():
        return jsonify({'error': 'No such archive'}), 404
    problem = inspect_archive(path)
    if problem:
        return jsonify({'ok': False, 'error': problem}), 400
    report = []
    with tempfile.TemporaryDirectory() as tmp:
        found = extract_databases(path, Path(tmp))
        if not found:
            return jsonify({'ok': False, 'error': 'no recognised databases inside'}), 400
        for db_name, db_path in sorted(found.items()):
            conn = sqlite3.connect(db_path)
            check = conn.execute('PRAGMA integrity_check;').fetchone()[0]
            tables = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table';").fetchone()[0]
            conn.close()
            report.append({'name': db_name, 'integrity': check, 'tables': tables,
                           'bytes': db_path.stat().st_size})
    bad = [r for r in report if r['integrity'] != 'ok']
    return jsonify({'ok': not bad, 'databases': report}), (400 if bad else 200)


@app.route('/api/archives/<name>/restore', methods=['POST'])
@require_admin
def restore(name):
    """
    Put an archive's databases back.

    Each live database is replaced through SQLite's online backup API, which
    takes the write lock and swaps the contents page by page. The applications
    can stay up: a reader sees the old contents until the swap completes, and
    never a half-written file. The replaced database is copied aside first.
    """
    data = request.get_json(silent=True) or {}
    if data.get('confirm') != name:
        return jsonify({'error': 'Confirm the restore by sending the archive name'}), 400
    try:
        path = archive_path(name)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    if not path.is_file():
        return jsonify({'error': 'No such archive'}), 404

    results = []
    with tempfile.TemporaryDirectory() as tmp:
        found = extract_databases(path, Path(tmp))
        if not found:
            return jsonify({'error': 'That archive contains no databases to restore'}), 400

        # Check every database before touching anything live.
        for db_name, db_path in found.items():
            conn = sqlite3.connect(db_path)
            check = conn.execute('PRAGMA integrity_check;').fetchone()[0]
            conn.close()
            if check != 'ok':
                return jsonify({'error': f'{db_name} is damaged in that archive '
                                         f'({check}); nothing was changed'}), 400

        for db_name, db_path in sorted(found.items()):
            target = DATABASES[db_name]
            if not target.parent.is_dir():
                results.append({'name': db_name, 'status': 'skipped',
                                'detail': f'{target.parent} is not mounted'})
                continue
            try:
                # The applications run as an unprivileged user while this runs
                # as root. Ownership must survive the restore, or the tools come
                # back up able to read but not write.
                reference = target if target.exists() else target.parent
                info = reference.stat()
                keep = target.with_name(target.name + '.before-restore')
                if target.exists():
                    shutil.copy2(target, keep)
                    os.chown(keep, info.st_uid, info.st_gid)
                source = sqlite3.connect(db_path)
                live = sqlite3.connect(str(target), timeout=30)
                source.backup(live)       # online restore: safe with readers attached
                live.close()
                source.close()
                os.chown(target, info.st_uid, info.st_gid)
                if reference is target:
                    os.chmod(target, stat.S_IMODE(info.st_mode))
                results.append({'name': db_name, 'status': 'restored',
                                'detail': f'previous kept as {target.name}.before-restore'})
            except (sqlite3.Error, OSError) as exc:
                results.append({'name': db_name, 'status': 'failed', 'detail': str(exc)})

    failed = [r for r in results if r['status'] == 'failed']
    return jsonify({'ok': not failed, 'results': results,
                    'note': 'The applications were not stopped; reload them to see restored data.'
                    }), (500 if failed else 200)


@app.route('/api/archives/<name>', methods=['DELETE'])
@require_admin
def delete_archive(name):
    try:
        path = archive_path(name)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    if not path.is_file():
        return jsonify({'error': 'No such archive'}), 404
    path.unlink()
    Path(str(path) + '.sha256').unlink(missing_ok=True)
    return jsonify({'ok': True, 'archives': list_archives()})


# ---------------------------------------------------------------------------
# The page itself
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    return send_file(Path(__file__).parent / 'console.html')


@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'version': APP_VERSION})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002)
