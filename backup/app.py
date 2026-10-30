"""
Backup console for Trellis Tools.

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
  is validated against an allowed root before it is touched. Inside the suite
  (SUITE_AUTH=proxy) there is no sign-in here at all: the suite's sign-in says
  who is there, and only an administrator gets in.
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
from flask import Flask, jsonify, redirect, request, send_file, session

import storage
from storage import StorageError

APP_VERSION = '2.19.0'

CONFIG_DIR = Path(os.environ.get('CONFIG_STORE', '/config-store'))
SETTINGS_FILE = CONFIG_DIR / 'settings.json'
# Backups may only be written below these roots. The host mounts the network
# drive somewhere under one of them.
# Separated the way PATH is on this platform, so a Windows checkout can run the
# tests even though the service itself only ever runs in a Linux container.
ALLOWED_ROOTS = [Path(p) for p in
                 os.environ.get('ALLOWED_BACKUP_ROOTS', f'/mnt{os.pathsep}/backup').split(os.pathsep)
                 if p]
EDITOR_DB = Path(os.environ.get('EDITOR_DB', '/data/plasmid_editor.db'))
# Accounts are shared across the suite; the MoClo user table is the directory.
MOCLO_DB = Path(os.environ.get('MOCLO_DB', '/moclo/moclo.db'))

# The databases this console can restore, and where they live.
DATABASES = {
    'moclo.db': Path(os.environ.get('MOCLO_DB', '/moclo/moclo.db')),
    'parts.db': Path(os.environ.get('PARTS_DB', '/moclo/parts.db')),
    'plasmid_editor.db': Path(os.environ.get('EDITOR_DB', '/data/plasmid_editor.db')),
    'suite.db': Path(os.environ.get('SUITE_DB', '/suite/suite.db')),
    'notebook.db': Path(os.environ.get('NOTEBOOK_DB', '/notebook/notebook.db')),
    'seeds.db': Path(os.environ.get('SEEDS_DB', '/seeds/seeds.db')),
    'stocks.db': Path(os.environ.get('STOCKS_DB', '/stocks/stocks.db')),
    'booking.db': Path(os.environ.get('BOOKING_DB', '/booking/booking.db')),
}

# The MoClo tool creates 'admin' with this password when no such account exists.
MOCLO_DEFAULT_PASSWORD = 'admin123'

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


def store():
    """The configured destination: a folder, or a network share."""
    return storage.store_for(load_settings(), DEFAULTS['destination'])


class _LocalCopy:
    """
    An archive as a local file, for reading: the file itself in a folder
    destination, or a temporary copy fetched from a network share.
    """

    def __init__(self, name: str):
        self.name = name
        self.tmp = None

    def __enter__(self) -> Path:
        target = store()
        in_place = target.local_path(self.name)
        if in_place is not None:
            return in_place
        self.tmp = tempfile.TemporaryDirectory()
        path = Path(self.tmp.name) / self.name
        target.fetch(self.name, path)
        return path

    def __exit__(self, *exc):
        if self.tmp is not None:
            self.tmp.cleanup()
        return False


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


def check_archive_name(name: str) -> str:
    """Refuse anything that is not a plain archive name."""
    if not ARCHIVE_RE.match(name or ''):
        raise ValueError('Not a backup archive name')
    return name


def archive_path(name: str) -> Path:
    """Resolve an archive name in a folder destination."""
    return destination() / check_archive_name(name)


# ---------------------------------------------------------------------------
# Authentication: the Plasmid Editor's admin accounts
# ---------------------------------------------------------------------------

def _lookup(db: Path, username: str):
    """A user row from one of the suite's databases, or None."""
    if not db.exists():
        return None
    try:
        conn = sqlite3.connect(f'file:{db}?mode=ro', uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        row = conn.execute('SELECT password_hash, is_admin FROM users WHERE username = ?',
                           ((username or '').strip(),)).fetchone()
        conn.close()
        return row
    except sqlite3.Error:
        return None


def check_admin(username: str, password: str) -> bool:
    """
    Accounts are shared across the suite, so the MoClo user table is the
    directory and is consulted first. The Plasmid Editor's own table is the
    fallback, for a deployment without the MoClo tool.

    Only administrators get in: this console can overwrite every database.
    """
    row = _lookup(MOCLO_DB, username) or _lookup(EDITOR_DB, username)
    if row is None or not row['is_admin']:
        return False
    try:
        return bcrypt.checkpw((password or '').encode(), row['password_hash'].encode())
    except (ValueError, TypeError):
        return False


# Inside the suite, the proxy says who is signed in (X-Suite-User), and people
# sign in and out on the suite's own page rather than here.
SUITE_AUTH = os.environ.get('SUITE_AUTH', '').strip().lower() == 'proxy'
SUITE_LOGIN_URL = os.environ.get('SUITE_LOGIN_URL', '/account/login')
SUITE_LOGOUT_URL = os.environ.get('SUITE_LOGOUT_URL', '/account/logout')
# The suite's dashboard, which shows this console in its Backups tab.
SUITE_DASHBOARD_URL = os.environ.get('SUITE_DASHBOARD_URL', '/account/')


@app.before_request
def follow_suite_sign_in():
    """Take the suite's signed-in user as this console's, if an administrator."""
    if not SUITE_AUTH:
        return
    username = request.headers.get('X-Suite-User', '').strip()
    row = (_lookup(MOCLO_DB, username) or _lookup(EDITOR_DB, username)) if username else None
    if row is not None and row['is_admin']:
        if session.get('username') != username or not session.get('admin'):
            session.clear()
            session['admin'] = True
            session['username'] = username
            session.permanent = True
    else:
        session.clear()
        if username:
            # Signed in to the suite, but not as an administrator.
            session['visitor'] = username


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

def list_archives() -> list:
    try:
        found = store().list()
    except (StorageError, ValueError):
        return []
    return [{
        'name': item['name'],
        'bytes': item['bytes'],
        'created_at': time.strftime('%d-%m-%Y %H:%M', time.localtime(item['mtime'])),
        'has_checksum': item['has_checksum'],
    } for item in found]


@app.route('/api/session')
def session_status():
    answer = {
        'authenticated': bool(session.get('admin')),
        'username': session.get('username'),
        'version': APP_VERSION,
    }
    if SUITE_AUTH:
        answer.update(login_url=SUITE_LOGIN_URL, logout_url=SUITE_LOGOUT_URL,
                      signed_in_as=session.get('username') or session.get('visitor'))
    return jsonify(answer)


@app.route('/api/login', methods=['POST'])
def login():
    if SUITE_AUTH:
        return jsonify({'error': 'Sign in on the lab tools sign-in page', 'login_url': SUITE_LOGIN_URL}), 403
    data = request.get_json(silent=True) or {}
    username = data.get('username', '')
    if data.get('password') == MOCLO_DEFAULT_PASSWORD:
        # Published in the MoClo tool's source, so it proves nothing. This
        # console can overwrite every database; it must not open with it.
        return jsonify({'error': "That is the MoClo tool's published default password. "
                                 'Change it first, then sign in here.'}), 403
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
    target = None
    try:
        target = store()
        state = target.check()
        label = target.describe()
        disk = target.free() if state['reachable'] else {'free': None, 'total': None}
    except ValueError as exc:       # a share setting that no longer parses
        state = {'reachable': False, 'marked': False, 'writable': False, 'error': str(exc)}
        label, disk = settings.get('smb_path', ''), {'free': None, 'total': None}
    # The outcome of the last run is kept locally, so it shows even when the
    # destination cannot be reached; older installs only have it there.
    last = {}
    try:
        last = json.loads(storage.last_status_file().read_text())
    except (OSError, ValueError):
        if target is not None and state['reachable']:
            try:
                last = json.loads(target.read_text('status.json'))
            except (StorageError, ValueError):
                pass
    archives = list_archives() if state['reachable'] else []
    return jsonify({
        'settings': settings,
        'allowed_roots': [str(r) for r in ALLOWED_ROOTS],
        'destination_type': settings.get('destination_type', 'folder'),
        'destination_label': label,
        'destination_error': state['error'],
        'smb_password_set': bool(storage.smb_password()),
        'destination_exists': state['reachable'],
        'destination_marked': state['marked'],
        'destination_writable': state['writable'],
        'disk': disk,
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
        'This directory is the backup destination for Trellis Tools.\n'
        f'Marked from the backup console on {time.strftime("%Y-%m-%d %H:%M:%S")}.\n\n'
        'The backup refuses to run if this file is missing, so that an unmounted\n'
        'network drive is never silently filled up instead.\n')
    settings = load_settings()
    settings['destination'] = str(dest)
    settings['destination_type'] = 'folder'
    save_settings(settings)
    return jsonify({'ok': True, 'destination': str(dest)})


def _share_from(data: dict):
    """A share store from the form, reusing the saved password if none is typed."""
    location = (data.get('path') or '').strip()
    storage.parse_share(location)           # raises ValueError with a plain message
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    if not password and username == load_settings().get('smb_username', ''):
        password = storage.smb_password()
    return storage.SmbStore(location, username, password), username, password


@app.route('/api/destination/share/test', methods=['POST'])
@require_admin
def test_share():
    """Try a network share without changing anything."""
    try:
        target, _, _ = _share_from(request.get_json(silent=True) or {})
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    state = target.check()
    if state['error'] and not state['reachable'] and 'does not exist' not in state['error']:
        return jsonify({'error': state['error']}), 400
    archives = 0
    if state['reachable']:
        try:
            archives = len(target.list())
        except StorageError:
            pass
    return jsonify({'ok': True, 'location': target.describe(), 'exists': state['reachable'],
                    'marked': state['marked'], 'writable': state['writable'],
                    'archives': archives, 'note': state['error']})


@app.route('/api/destination/share', methods=['POST'])
@require_admin
def use_share():
    """
    Back up to a folder on a network share from now on.

    The folder is created if need be, written to as a test, and marked, so the
    nightly job will use it. The password is stored apart from the settings,
    readable only inside the backup containers, and never sent back.
    """
    try:
        target, username, password = _share_from(request.get_json(silent=True) or {})
        target.prepare()
    except (ValueError, StorageError) as exc:
        return jsonify({'error': str(exc)}), 400
    storage.save_smb_password(password)
    settings = load_settings()
    settings.update({'destination_type': 'smb', 'smb_path': target.describe(),
                     'smb_username': username})
    save_settings(settings)
    return jsonify({'ok': True, 'destination': target.describe()})


@app.route('/api/browse')
@require_admin
def browse():
    """
    List the folders inside a path, for choosing a destination.

    Only folders are listed, and only within the allowed roots, so this cannot
    be used to look around the rest of the server. Asking for nothing lists the
    roots themselves.
    """
    raw = (request.args.get('path') or '').strip()
    if not raw:
        return jsonify({
            'path': '', 'parent': None, 'is_root_list': True,
            'entries': [{'name': str(r), 'path': str(r), 'exists': r.is_dir()}
                        for r in ALLOWED_ROOTS],
        })
    try:
        here = validate_destination(raw)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    if not here.is_dir():
        return jsonify({'error': f'{here} is not a folder on the server'}), 404

    entries = []
    try:
        for item in sorted(here.iterdir(), key=lambda p: p.name.lower()):
            if not item.is_dir() or item.name.startswith('.'):
                continue
            try:
                count = sum(1 for _ in item.glob('lab-suite-*.tar.gz'))
            except OSError:
                count = 0
            entries.append({'name': item.name, 'path': str(item), 'archives': count,
                            'writable': os.access(item, os.W_OK)})
    except PermissionError:
        return jsonify({'error': f'No permission to read {here}'}), 403

    # Offer the parent only while it stays inside an allowed root.
    parent = None
    if str(here) not in [str(r) for r in ALLOWED_ROOTS]:
        try:
            parent = str(validate_destination(str(here.parent)))
        except ValueError:
            parent = None
    return jsonify({
        'path': str(here), 'parent': parent, 'is_root_list': False,
        'writable': os.access(here, os.W_OK),
        'archives': sum(1 for _ in here.glob('lab-suite-*.tar.gz')),
        'entries': entries,
    })


@app.route('/api/browse/mkdir', methods=['POST'])
@require_admin
def make_folder():
    """Create a folder while choosing a destination."""
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name or '/' in name or name in ('.', '..') or name.startswith('.'):
        return jsonify({'error': 'Give a simple folder name'}), 400
    try:
        parent = validate_destination(data.get('path') or '')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    target = parent / name
    try:
        target.mkdir(parents=False, exist_ok=True)
    except OSError as exc:
        return jsonify({'error': f'Could not create {target}: {exc}'}), 400
    return jsonify({'ok': True, 'path': str(target)})


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
        check_archive_name(name)
        target = store()
        if not target.exists(name):
            return jsonify({'error': 'No such archive'}), 404
        in_place = target.local_path(name)
        if in_place is not None:
            return send_file(in_place, as_attachment=True, download_name=name)
        # From a share: fetched to a temporary file, removed once it is sent.
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        local = Path(tmp.name) / name
        target.fetch(name, local)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except StorageError as exc:
        return jsonify({'error': str(exc)}), 502
    response = send_file(local, as_attachment=True, download_name=name)
    response.call_on_close(tmp.cleanup)
    return response


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
    target = store()
    if not target.check()['reachable']:
        return jsonify({'error': f'{target.describe()} is not available'}), 400
    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp) / name
        item.save(staging)
        problem = inspect_archive(staging)
        if problem:
            return jsonify({'error': f'That archive is not usable: {problem}'}), 400
        try:
            target.put(staging, name)
        except (StorageError, OSError) as exc:
            return jsonify({'error': f'Could not store the archive: {exc}'}), 502
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
        check_archive_name(name)
        if not store().exists(name):
            return jsonify({'error': 'No such archive'}), 404
        with _LocalCopy(name) as path:
            return _verify(path)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except StorageError as exc:
        return jsonify({'error': str(exc)}), 502


def _verify(path: Path):
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
        check_archive_name(name)
        if not store().exists(name):
            return jsonify({'error': 'No such archive'}), 404
        with _LocalCopy(name) as path:
            return _restore(path)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except StorageError as exc:
        return jsonify({'error': str(exc)}), 502


def _restore(path: Path):
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
        check_archive_name(name)
        target = store()
        if not target.exists(name):
            return jsonify({'error': 'No such archive'}), 404
        target.delete(name)
        target.delete(name + '.sha256')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except StorageError as exc:
        return jsonify({'error': str(exc)}), 502
    return jsonify({'ok': True, 'archives': list_archives()})


# ---------------------------------------------------------------------------
# The page itself
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    # Inside the suite, the console is the Backups tab of its dashboard, shown
    # there with ?embed=1; opened on its own, it goes to that tab.
    if SUITE_AUTH and request.args.get('embed') != '1':
        return redirect(f'{SUITE_DASHBOARD_URL}#backups')
    return send_file(Path(__file__).parent / 'console.html')


@app.route('/suite-manifest.json')
def suite_manifest():
    """The tab this console adds to the suite's dashboard."""
    return jsonify({'tool': 'Backups', 'tabs': [
        {'id': 'backups', 'title': 'Backups', 'icon': '💾', 'glyph': 'archive', 'section': 'admin',
         'roles': ['admin'], 'src': '/backup/?embed=1'}]})


@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'version': APP_VERSION})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002)
