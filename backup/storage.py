"""
Where backup archives are kept: a folder, or a network share reached over SMB.

A folder is any path the container can see, which is how a drive the server
has mounted itself is used. A network share is reached directly from inside
the container, with its own credentials, so a Windows file server or NAS works
without mounting anything on the host. That needs no extra privileges: the
share is spoken to over SMB in user space, never mounted, which keeps the
backup containers as unprivileged as they were.

Both kinds offer the same small set of operations, so the console and the
nightly job do not care which one is configured. The command line at the
bottom is how backup.sh talks to a share:

    storage.py check                  can the destination be used? (exit 1 if not)
    storage.py publish ARCHIVE        copy an archive and its .sha256 there, verified
    storage.py prune DAILY WEEKLY MONTHLY
    storage.py count                  archives held
    storage.py free                   free space, human-readable, or "unknown"
    storage.py status STATUS DETAIL [ARCHIVE]
    storage.py append-log FILE
"""

import hashlib
import json
import os
import re
import shutil
import sys
import time
from datetime import date
from pathlib import Path


def config_dir() -> Path:
    return Path(os.environ.get('CONFIG_STORE', '/config-store'))


def settings_file() -> Path:
    return config_dir() / 'settings.json'


def smb_secret_file() -> Path:
    """The share's password: apart from the settings, private, never sent to a browser."""
    return config_dir() / 'smb-password'


def last_status_file() -> Path:
    """The last run's outcome, kept locally so the healthcheck never needs the share."""
    return config_dir() / 'last-status.json'

ARCHIVE_RE = re.compile(r'^lab-suite-(\d{4}-\d{2}-\d{2})_\d{6}\.tar\.gz$')
MARKER = '.backup-target'
MARKER_TEXT = (
    'This directory is the backup destination for the Gardiner Lab tool suite.\n'
    'Marked from the backup console on {when}.\n\n'
    'The backup refuses to run if this file is missing, so that a drive that\n'
    'failed to mount, or the wrong share, is never silently filled up instead.\n')

_HOST_RE = re.compile(r'^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$')
_PART_RE = re.compile(r'^[^<>:"|?*\x00-\x1f]+$')


class StorageError(Exception):
    """The destination cannot be used; the message says why, in plain words."""


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def load_settings() -> dict:
    try:
        return json.loads(settings_file().read_text())
    except (OSError, ValueError):
        return {}


def smb_password() -> str:
    try:
        return smb_secret_file().read_text()
    except OSError:
        return ''


def save_smb_password(password: str) -> None:
    config_dir().mkdir(parents=True, exist_ok=True)
    tmp = smb_secret_file().with_suffix('.part')
    # Created private, rather than tightened after being written.
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as handle:
        handle.write(password)
    tmp.replace(smb_secret_file())


def parse_share(raw: str):
    r"""
    Split a share location into (server, share, folder parts).

    Accepts the forms people paste: \\server\share\folder, //server/share/folder
    and smb://server/share/folder.
    """
    text = (raw or '').strip()
    if text.lower().startswith('smb:'):
        text = text[4:]
    text = text.replace('\\', '/')
    if not text.startswith('//'):
        raise ValueError(r'Give the share as \\server\share\folder')
    parts = [p for p in text[2:].split('/') if p]
    if len(parts) < 2:
        raise ValueError(r'Give both a server and a share name, as \\server\share\folder')
    server, share, folders = parts[0], parts[1], parts[2:]
    if not _HOST_RE.match(server):
        raise ValueError(f'"{server}" is not a server name')
    for part in [share] + folders:
        if part in ('.', '..') or not _PART_RE.match(part):
            raise ValueError(f'"{part}" is not allowed in a share path')
    return server, share, folders


def unc(server: str, share: str, folders=()) -> str:
    return '\\\\' + '\\'.join([server, share, *folders])


# ---------------------------------------------------------------------------
# The two kinds of destination
# ---------------------------------------------------------------------------

class FolderStore:
    """A directory the container can see, perhaps a drive the host mounted."""

    kind = 'folder'

    def __init__(self, path):
        self.root = Path(path)

    def describe(self) -> str:
        return str(self.root)

    def _path(self, name: str) -> Path:
        return self.root / name

    def check(self) -> dict:
        exists = self.root.is_dir()
        return {
            'reachable': exists,
            'marked': (self.root / MARKER).exists(),
            'writable': os.access(self.root, os.W_OK) if exists else False,
            'error': None if exists else f'{self.root} does not exist inside the container',
        }

    def prepare(self) -> None:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            probe = self.root / '.write-test'
            probe.write_text('ok')
            probe.unlink()
        except OSError as exc:
            raise StorageError(f'Cannot write to {self.root}: {exc}. '
                               'Is the drive mounted on the server, and writable?')
        self.write_text(MARKER, MARKER_TEXT.format(when=time.strftime('%Y-%m-%d %H:%M:%S')))

    def list(self) -> list:
        out = []
        try:
            entries = sorted(self.root.glob('lab-suite-*.tar.gz'), reverse=True)
        except OSError:
            return out
        for item in entries:
            if not ARCHIVE_RE.match(item.name):
                continue
            try:
                info = item.stat()
            except OSError:
                continue
            out.append({'name': item.name, 'bytes': info.st_size, 'mtime': info.st_mtime,
                        'has_checksum': Path(str(item) + '.sha256').exists()})
        return out

    def exists(self, name: str) -> bool:
        return self._path(name).is_file()

    def read_text(self, name: str) -> str:
        try:
            return self._path(name).read_text()
        except OSError as exc:
            raise StorageError(str(exc))

    def write_text(self, name: str, text: str) -> None:
        tmp = self._path(name + '.part')
        tmp.write_text(text)
        tmp.replace(self._path(name))

    def append_text(self, name: str, text: str) -> None:
        with open(self._path(name), 'a') as handle:
            handle.write(text)

    def put(self, local: Path, name: str) -> None:
        tmp = self._path(name + '.part')
        shutil.copyfile(local, tmp)
        tmp.replace(self._path(name))

    def fetch(self, name: str, local: Path) -> None:
        shutil.copyfile(self._path(name), local)

    def local_path(self, name: str):
        """A path that can be read in place, so nothing need be copied."""
        return self._path(name)

    def delete(self, name: str) -> None:
        self._path(name).unlink(missing_ok=True)

    def free(self):
        try:
            usage = shutil.disk_usage(self.root)
            return {'free': usage.free, 'total': usage.total}
        except OSError:
            return {'free': None, 'total': None}


class SmbStore:
    r"""A folder on a Windows or NAS share, e.g. \\fileserver\lab\backups."""

    kind = 'smb'

    def __init__(self, location: str, username: str = '', password: str = ''):
        self.server, self.share, self.folders = parse_share(location)
        self.username = username or None
        self.password = password or None
        self._session = False

    def describe(self) -> str:
        return unc(self.server, self.share, self.folders)

    def _client(self):
        # Imported here so the folder destination, and the tests, work without
        # the SMB library installed.
        import smbclient
        if not self._session:
            try:
                smbclient.register_session(self.server, username=self.username,
                                           password=self.password, connection_timeout=15)
            except Exception as exc:  # noqa: BLE001 - the library raises many kinds
                raise StorageError(self._explain(exc))
            self._session = True
        return smbclient

    def _explain(self, exc) -> str:
        text = str(exc) or exc.__class__.__name__
        lowered = text.lower()
        if 'logon_failure' in lowered or 'logon failure' in lowered or 'access_denied' in lowered:
            return (f'{self.server} refused the username or password. For a domain '
                    'account, give the username as DOMAIN\\name.')
        if 'bad_network_name' in lowered or 'status_not_found' in lowered:
            return f'{self.server} has no share called "{self.share}".'
        if 'object_path_not_found' in lowered or 'object_name_not_found' in lowered:
            return f'{self.describe()} does not exist.'
        if 'timed out' in lowered or 'failed to connect' in lowered or 'name or service' in lowered:
            return f'Could not reach {self.server}. Check the name and that this server can reach it.'
        return f'{self.describe()}: {text}'

    def _path(self, name: str = '') -> str:
        return unc(self.server, self.share, self.folders + ([name] if name else []))

    def _call(self, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except StorageError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise StorageError(self._explain(exc))

    def check(self) -> dict:
        result = {'reachable': False, 'marked': False, 'writable': False, 'error': None}
        try:
            client = self._client()
            if not self._call(client.path.isdir, self._path()):
                result['error'] = f'{self.describe()} does not exist on the share yet.'
                return result
            result['reachable'] = True
            result['marked'] = self._call(client.path.isfile, self._path(MARKER))
            probe = self._path('.write-test')
            self._call(self._write_bytes, probe, b'ok')
            self._call(client.remove, probe)
            result['writable'] = True
        except StorageError as exc:
            result['error'] = str(exc)
        return result

    def prepare(self) -> None:
        client = self._client()
        self._call(client.makedirs, self._path(), exist_ok=True)
        probe = self._path('.write-test')
        try:
            self._write_bytes(probe, b'ok')
            client.remove(probe)
        except Exception as exc:  # noqa: BLE001
            raise StorageError(f'Cannot write to {self.describe()}: {self._explain(exc)}')
        self.write_text(MARKER, MARKER_TEXT.format(when=time.strftime('%Y-%m-%d %H:%M:%S')))

    def _write_bytes(self, path: str, data: bytes) -> None:
        with self._client().open_file(path, mode='wb') as handle:
            handle.write(data)

    def list(self) -> list:
        client = self._client()
        names = set()
        out = []
        entries = self._call(lambda: list(client.scandir(self._path())))
        for entry in entries:
            names.add(entry.name)
        for entry in entries:
            if not ARCHIVE_RE.match(entry.name) or not entry.is_file():
                continue
            info = self._call(entry.stat)
            out.append({'name': entry.name, 'bytes': info.st_size, 'mtime': info.st_mtime,
                        'has_checksum': entry.name + '.sha256' in names})
        return sorted(out, key=lambda a: a['name'], reverse=True)

    def exists(self, name: str) -> bool:
        return self._call(self._client().path.isfile, self._path(name))

    def read_text(self, name: str) -> str:
        def read():
            with self._client().open_file(self._path(name), mode='r') as handle:
                return handle.read()
        return self._call(read)

    def write_text(self, name: str, text: str) -> None:
        tmp = self._path(name + '.part')
        self._call(self._write_bytes, tmp, text.encode())
        self._call(self._client().replace, tmp, self._path(name))

    def append_text(self, name: str, text: str) -> None:
        def append():
            with self._client().open_file(self._path(name), mode='ab') as handle:
                handle.write(text.encode())
        self._call(append)

    def put(self, local: Path, name: str) -> None:
        client = self._client()
        tmp = self._path(name + '.part')

        def copy():
            with open(local, 'rb') as src, client.open_file(tmp, mode='wb') as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)
        self._call(copy)
        self._call(client.replace, tmp, self._path(name))

    def fetch(self, name: str, local: Path) -> None:
        def copy():
            with self._client().open_file(self._path(name), mode='rb') as src, \
                    open(local, 'wb') as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)
        self._call(copy)

    def local_path(self, name: str):
        return None

    def delete(self, name: str) -> None:
        client = self._client()
        if self._call(client.path.isfile, self._path(name)):
            self._call(client.remove, self._path(name))

    def free(self):
        try:
            client = self._client()
            info = client.stat_volume(self._path())
            return {'free': info.caller_available_size, 'total': info.total_size}
        except Exception:  # noqa: BLE001 - not every server reports it
            return {'free': None, 'total': None}

    def sha256(self, name: str) -> str:
        """Hash the copy on the share by reading it back."""
        def digest():
            h = hashlib.sha256()
            with self._client().open_file(self._path(name), mode='rb') as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b''):
                    h.update(block)
            return h.hexdigest()
        return self._call(digest)


def store_for(settings: dict, default_folder: str = '/backup'):
    """The destination the settings describe."""
    if settings.get('destination_type') == 'smb':
        return SmbStore(settings.get('smb_path', ''), settings.get('smb_username', ''),
                        smb_password())
    return FolderStore(settings.get('destination') or default_folder)


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------

def to_prune(names, keep_daily: int, keep_weekly: int, keep_monthly: int) -> list:
    """
    The archives retention lets go, newest first being kept.

    The newest `keep_daily` are kept outright, then the newest archive of each
    of the last `keep_weekly` weeks and `keep_monthly` months, so older history
    thins out instead of disappearing all at once. Same rule as backup.sh.
    """
    keep = set()
    weeks, months = [], []
    dated = []
    for name in names:
        m = ARCHIVE_RE.match(name)
        if m:
            dated.append(name)
    for index, name in enumerate(sorted(dated, reverse=True), start=1):
        day = date.fromisoformat(ARCHIVE_RE.match(name).group(1))
        week = '%d-%02d' % day.isocalendar()[:2]
        month = day.strftime('%Y-%m')
        if index <= keep_daily:
            keep.add(name)
        if week not in weeks:
            weeks.append(week)
            if len(weeks) <= keep_weekly:
                keep.add(name)
        if month not in months:
            months.append(month)
            if len(months) <= keep_monthly:
                keep.add(name)
    return [n for n in dated if n not in keep]


def human(n) -> str:
    if n is None:
        return 'unknown'
    for unit in ('B', 'K', 'M', 'G', 'T'):
        if n < 1024 or unit == 'T':
            return f'{n:.1f}{unit}' if unit != 'B' else f'{n}B'
        n /= 1024
    return str(n)


# ---------------------------------------------------------------------------
# Command line, for backup.sh
# ---------------------------------------------------------------------------

def write_last_status(record: dict) -> None:
    try:
        config_dir().mkdir(parents=True, exist_ok=True)
        tmp = last_status_file().with_suffix('.part')
        tmp.write_text(json.dumps(record, indent=2))
        tmp.replace(last_status_file())
    except OSError:
        pass


def main(argv) -> int:
    if not argv:
        print(__doc__)
        return 2
    command, args = argv[0], argv[1:]
    store = store_for(load_settings(), os.environ.get('BACKUP_DEST', '/backup'))
    try:
        if command == 'check':
            state = store.check()
            if state['error']:
                print(state['error'])
                return 1
            if not state['marked']:
                print(f'{store.describe()} is not marked as the backup destination. Open the '
                      'backup console and press "Use this destination" once. This guard exists '
                      'so that the wrong folder is never mistaken for the backup target.')
                return 1
            if not state['writable']:
                print(f'{store.describe()} is not writable')
                return 1
            return 0

        if command == 'publish':
            archive = Path(args[0])
            checksum = Path(str(archive) + '.sha256')
            expected = checksum.read_text().split()[0]
            store.put(archive, archive.name)
            store.put(checksum, checksum.name)
            # A truncated transfer must never look like a good backup.
            if isinstance(store, SmbStore) and store.sha256(archive.name) != expected:
                store.delete(archive.name)
                print(f'the copy on {store.describe()} does not match its checksum')
                return 1
            return 0

        if command == 'prune':
            daily, weekly, monthly = (int(a) for a in args[:3])
            names = [a['name'] for a in store.list()]
            gone = to_prune(names, daily, weekly, monthly)
            for name in gone:
                store.delete(name)
                store.delete(name + '.sha256')
            print(len(gone))
            return 0

        if command == 'count':
            print(len(store.list()))
            return 0

        if command == 'free':
            print(human(store.free()['free']))
            return 0

        if command == 'status':
            record = {'status': args[0], 'detail': args[1],
                      'archive': args[2] if len(args) > 2 else '',
                      'finished_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                      'host': os.uname().nodename if hasattr(os, 'uname') else '',
                      'destination': store.describe()}
            write_last_status(record)
            try:
                store.write_text('status.json', json.dumps(record, indent=2))
            except StorageError:
                pass        # recorded locally; the destination may be the problem
            return 0

        if command == 'append-log':
            store.append_text('backup.log', Path(args[0]).read_text())
            return 0

    except StorageError as exc:
        print(str(exc))
        return 1
    print(f'unknown command {command}')
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
