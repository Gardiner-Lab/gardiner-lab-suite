"""
Tests for backup destinations, folders and network shares.

The share is stood in for by a folder that behaves like one from the outside:
it must be fetched from rather than read in place, and it checks credentials.
The real SMB client is exercised against a Samba server by hand; see
docs/BACKUP.md.

    python -m pytest backup/test_storage.py
"""

import importlib
import io
import json
import os
import sys
import tarfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import storage  # noqa: E402

ARCHIVE = 'lab-suite-2026-10-09_020000.tar.gz'


# ---------------------------------------------------------------------------
# Share locations
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('raw', [
    r'\\fs.example.org\lab\backups\suite',
    '//fs.example.org/lab/backups/suite',
    'smb://fs.example.org/lab/backups/suite',
    r'  \\fs.example.org\lab\backups\suite\  ',
])
def test_share_locations_in_every_common_form(raw):
    assert storage.parse_share(raw) == ('fs.example.org', 'lab', ['backups', 'suite'])


def test_a_share_without_a_folder_is_fine():
    assert storage.parse_share(r'\\nas\backup') == ('nas', 'backup', [])


@pytest.mark.parametrize('raw', [
    '', '/mnt/backup', r'\\server', r'\\server\share\..\other',
    r'\\bad host\share', r'\\server\share\a:b', r'\\-server\share',
])
def test_bad_share_locations_are_refused(raw):
    with pytest.raises(ValueError):
        storage.parse_share(raw)


# ---------------------------------------------------------------------------
# Retention, the same rule as backup.sh
# ---------------------------------------------------------------------------

def _names(days):
    return [f'lab-suite-{d}_020000.tar.gz' for d in days]


def test_recent_dailies_are_all_kept():
    names = _names(['2026-10-01', '2026-10-02', '2026-10-03'])
    assert storage.to_prune(names, 14, 8, 12) == []


def test_older_history_thins_to_one_per_week_and_month():
    days = [f'2026-{m:02d}-{d:02d}' for m in (8, 9, 10) for d in range(1, 29)]
    names = _names(days)
    gone = set(storage.to_prune(names, 3, 2, 2))
    kept = sorted(set(names) - gone, reverse=True)
    # The newest three, then the newest of this week and last, and of this
    # month and last: September 28th is both last month's and a week's newest.
    assert kept == _names(['2026-10-28', '2026-10-27', '2026-10-26', '2026-10-25',
                           '2026-09-28'])


def test_files_that_are_not_archives_are_never_pruned():
    names = _names(['2026-01-01', '2026-01-02']) + ['notes.txt', 'lab-suite-bogus.tar.gz']
    assert storage.to_prune(names, 1, 0, 0) == _names(['2026-01-01'])


# ---------------------------------------------------------------------------
# A stand-in for a network share
# ---------------------------------------------------------------------------

class FakeShare(storage.FolderStore):
    """A folder that has to be fetched from, and wants the right password."""

    kind = 'smb'
    root_dir = None

    def __init__(self, location, username='', password=''):
        self.server, self.share, self.folders = storage.parse_share(location)
        super().__init__(Path(self.root_dir, self.share, *self.folders))
        self.password = password

    def _auth(self):
        if self.password != 'secret':
            raise storage.StorageError(f'{self.server} refused the username or password.')

    def describe(self):
        return storage.unc(self.server, self.share, self.folders)

    def check(self):
        try:
            self._auth()
        except storage.StorageError as exc:
            return {'reachable': False, 'marked': False, 'writable': False, 'error': str(exc)}
        state = super().check()
        if not state['reachable']:
            state['error'] = f'{self.describe()} does not exist on the share yet.'
        return state

    def prepare(self):
        self._auth()
        super().prepare()

    def local_path(self, name):
        return None


@pytest.fixture()
def console(tmp_path, monkeypatch):
    allowed = tmp_path / 'mnt'
    allowed.mkdir()
    share_root = tmp_path / 'server'
    (share_root / 'lab').mkdir(parents=True)
    monkeypatch.setenv('ALLOWED_BACKUP_ROOTS', str(allowed))
    monkeypatch.setenv('CONFIG_STORE', str(tmp_path / 'config'))
    monkeypatch.setenv('BACKUP_DEST', str(allowed))
    FakeShare.root_dir = share_root
    monkeypatch.setattr(storage, 'SmbStore', FakeShare)
    module = importlib.reload(importlib.import_module('app'))
    module.app.config.update(TESTING=True, SECRET_KEY='test')
    client = module.app.test_client()
    with client.session_transaction() as flask_session:
        flask_session['admin'] = True
        flask_session['username'] = 'tester'
    return client, share_root / 'lab' / 'backups', tmp_path


def _archive_bytes():
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as tar:
        data = b'SQLite format 3\x00'
        info = tarfile.TarInfo('lab-suite-2026-10-09_020000/databases/parts.db')
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


SHARE = {'path': r'\\fs.example.org\lab\backups', 'username': r'LAB\backup', 'password': 'secret'}


def test_a_share_is_tested_without_changing_anything(console):
    client, folder, _ = console
    r = client.post('/api/destination/share/test', json=SHARE)
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['exists'] is False
    assert not folder.exists()


def test_a_wrong_password_is_reported_plainly(console):
    client, _, _ = console
    r = client.post('/api/destination/share', json=dict(SHARE, password='wrong'))
    assert r.status_code == 400
    assert 'refused the username or password' in r.get_json()['error']


def test_using_a_share_creates_and_marks_the_folder(console):
    client, folder, tmp = console
    r = client.post('/api/destination/share', json=SHARE)
    assert r.status_code == 200, r.get_json()
    assert (folder / storage.MARKER).exists()

    status = client.get('/api/status').get_json()
    assert status['destination_type'] == 'smb'
    assert status['destination_label'] == r'\\fs.example.org\lab\backups'
    assert status['destination_exists'] and status['destination_marked']
    assert status['smb_password_set'] is True
    # The password is kept apart, privately, and never sent back.
    assert 'secret' not in json.dumps(status)
    assert 'secret' not in (tmp / 'config' / 'settings.json').read_text()
    secret = tmp / 'config' / 'smb-password'
    assert secret.read_text() == 'secret'
    if os.name == 'posix':
        assert secret.stat().st_mode & 0o077 == 0


def test_the_saved_password_is_reused_when_left_blank(console):
    client, _, _ = console
    client.post('/api/destination/share', json=SHARE)
    r = client.post('/api/destination/share/test', json=dict(SHARE, password=''))
    assert r.status_code == 200, r.get_json()
    # But not handed to a different account.
    r = client.post('/api/destination/share/test',
                    json=dict(SHARE, username='someone-else', password=''))
    assert r.status_code == 400


def test_archives_on_a_share_can_be_listed_downloaded_and_deleted(console):
    client, folder, _ = console
    client.post('/api/destination/share', json=SHARE)
    payload = _archive_bytes()
    (folder / ARCHIVE).write_bytes(payload)
    (folder / (ARCHIVE + '.sha256')).write_text('x  ' + ARCHIVE)

    listed = client.get('/api/archives').get_json()['archives']
    assert [a['name'] for a in listed] == [ARCHIVE]
    assert listed[0]['has_checksum']

    download = client.get(f'/api/archives/{ARCHIVE}/download')
    assert download.status_code == 200
    assert download.data == payload
    download.close()

    assert client.delete(f'/api/archives/{ARCHIVE}').status_code == 200
    assert not (folder / ARCHIVE).exists()
    assert not (folder / (ARCHIVE + '.sha256')).exists()


def test_an_uploaded_archive_lands_on_the_share(console):
    client, folder, _ = console
    client.post('/api/destination/share', json=SHARE)
    payload = _archive_bytes()
    r = client.post('/api/archives/upload', content_type='multipart/form-data',
                    data={'file': (io.BytesIO(payload), ARCHIVE)})
    assert r.status_code == 200, r.get_json()
    assert (folder / ARCHIVE).read_bytes() == payload


def test_choosing_a_folder_again_switches_back(console):
    client, _, tmp = console
    client.post('/api/destination/share', json=SHARE)
    r = client.post('/api/destination/prepare', json={'destination': str(tmp / 'mnt' / 'here')})
    assert r.status_code == 200, r.get_json()
    assert client.get('/api/status').get_json()['destination_type'] == 'folder'


def test_share_routes_require_signing_in(console):
    client, _, _ = console
    with client.session_transaction() as flask_session:
        flask_session.clear()
    for path in ('/api/destination/share', '/api/destination/share/test'):
        assert client.post(path, json=SHARE).status_code == 401


# ---------------------------------------------------------------------------
# The command line backup.sh uses
# ---------------------------------------------------------------------------

def test_publish_prune_and_status_from_the_command_line(tmp_path, monkeypatch):
    dest = tmp_path / 'dest'
    dest.mkdir()
    monkeypatch.setenv('CONFIG_STORE', str(tmp_path / 'config'))
    monkeypatch.setenv('BACKUP_DEST', str(dest))

    assert storage.main(['check']) == 1, 'unmarked destinations are refused'
    storage.FolderStore(dest).prepare()
    assert storage.main(['check']) == 0

    outbox = tmp_path / 'outbox'
    outbox.mkdir()
    for day in ('2026-10-01', '2026-10-02', '2026-10-03'):
        archive = outbox / f'lab-suite-{day}_020000.tar.gz'
        archive.write_bytes(b'data')
        Path(str(archive) + '.sha256').write_text(f'abc  {archive.name}\n')
        assert storage.main(['publish', str(archive)]) == 0
    assert len(list(dest.glob('*.tar.gz'))) == 3

    assert storage.main(['prune', '1', '0', '0']) == 0
    assert [p.name for p in dest.glob('*.tar.gz')] == ['lab-suite-2026-10-03_020000.tar.gz']
    assert not (dest / 'lab-suite-2026-10-01_020000.tar.gz.sha256').exists()

    assert storage.main(['status', 'ok', '1 archive(s) held', 'x.tar.gz']) == 0
    local = json.loads((tmp_path / 'config' / 'last-status.json').read_text())
    assert local['status'] == 'ok'
    assert json.loads((dest / 'status.json').read_text())['status'] == 'ok'
