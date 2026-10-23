"""
Tests for the backup console's path handling.

Everything here guards the same thing: values arriving from a browser must
never be able to reach outside the folders backups are allowed to live in, or
name a file that is not an archive.

    python -m pytest backup/test_app.py
"""

import importlib
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture()
def console(tmp_path, monkeypatch):
    allowed = tmp_path / 'mnt'
    allowed.mkdir()
    monkeypatch.setenv('ALLOWED_BACKUP_ROOTS', str(allowed))
    monkeypatch.setenv('CONFIG_STORE', str(tmp_path / 'config'))
    monkeypatch.setenv('BACKUP_DEST', str(allowed))
    module = importlib.reload(importlib.import_module('app'))
    return module, allowed


@pytest.mark.parametrize('path', [
    '/etc', '/', '/etc/passwd',
    '/mnt/../etc',                 # climbing out with ..
    'relative/path',               # not absolute
    '',                            # nothing at all
])
def test_destinations_outside_the_allowed_roots_are_refused(console, path):
    module, _ = console
    with pytest.raises(ValueError):
        module.validate_destination(path)


def test_a_sibling_sharing_a_prefix_is_refused(console):
    """/mnt-secret must not pass just because it starts with /mnt."""
    module, allowed = console
    with pytest.raises(ValueError):
        module.validate_destination(str(allowed) + 'secret')


def test_paths_inside_the_allowed_root_are_accepted(console):
    module, allowed = console
    assert module.validate_destination(str(allowed)) == allowed
    assert module.validate_destination(str(allowed / 'lab-suite')) == allowed / 'lab-suite'
    # Tidied, but still inside.
    assert module.validate_destination(str(allowed / 'a' / '..' / 'b')) == allowed / 'b'


@pytest.mark.parametrize('name', [
    '../../etc/passwd',
    'lab-suite-2026-10-09_020000.tar.gz/../../etc/passwd',
    '/etc/passwd',
    'notanarchive.txt',
    'lab-suite-bogus.tar.gz',
    '',
])
def test_only_real_archive_names_resolve(console, name):
    module, _ = console
    with pytest.raises(ValueError):
        module.archive_path(name)


def test_a_well_formed_archive_name_resolves_inside_the_destination(console):
    module, allowed = console
    resolved = module.archive_path('lab-suite-2026-10-09_020000.tar.gz')
    assert resolved.parent == allowed


def test_every_api_route_requires_signing_in(console):
    """No route may expose anything before an administrator has signed in."""
    module, _ = console
    module.app.config.update(TESTING=True, SECRET_KEY='test')
    client = module.app.test_client()
    for method, path in [
        ('get', '/api/status'), ('get', '/api/archives'), ('get', '/api/browse'),
        ('post', '/api/settings'), ('post', '/api/backup/run'),
        ('post', '/api/destination/prepare'), ('post', '/api/browse/mkdir'),
        ('post', '/api/archives/upload'),
        ('get', '/api/archives/lab-suite-2026-10-09_020000.tar.gz/download'),
        ('post', '/api/archives/lab-suite-2026-10-09_020000.tar.gz/restore'),
        ('post', '/api/archives/lab-suite-2026-10-09_020000.tar.gz/verify'),
        ('delete', '/api/archives/lab-suite-2026-10-09_020000.tar.gz'),
    ]:
        response = getattr(client, method)(path)
        assert response.status_code == 401, f'{method.upper()} {path} answered {response.status_code}'


def test_health_and_the_page_itself_stay_public(console):
    module, _ = console
    module.app.config.update(TESTING=True, SECRET_KEY='test')
    client = module.app.test_client()
    assert client.get('/health').status_code == 200
    assert client.get('/api/session').status_code == 200


def test_restore_needs_the_archive_name_typed_back(console, monkeypatch):
    module, allowed = console
    module.app.config.update(TESTING=True, SECRET_KEY='test')
    client = module.app.test_client()
    with client.session_transaction() as flask_session:
        flask_session['admin'] = True
        flask_session['username'] = 'tester'
    name = 'lab-suite-2026-10-09_020000.tar.gz'
    (allowed / name).write_bytes(b'not really an archive')
    # Without the confirmation, nothing is attempted.
    assert client.post(f'/api/archives/{name}/restore', json={}).status_code == 400
    assert client.post(f'/api/archives/{name}/restore',
                       json={'confirm': 'something else'}).status_code == 400


def test_the_moclo_default_password_never_opens_the_console(console):
    module, _ = console
    module.app.config.update(TESTING=True, SECRET_KEY='test')
    module.check_admin = lambda username, password: True   # even if it matched
    r = module.app.test_client().post('/api/login', json={'username': 'admin', 'password': 'admin123'})
    assert r.status_code == 403
    assert 'default password' in r.get_json()['error']


# ---------------------------------------------------------------------------
# Inside the suite: the proxy says who is signed in
# ---------------------------------------------------------------------------

@pytest.fixture()
def suite_console(tmp_path, monkeypatch):
    import sqlite3
    directory = tmp_path / 'moclo.db'
    conn = sqlite3.connect(directory)
    conn.execute('CREATE TABLE users (username TEXT, password_hash TEXT, is_admin INTEGER)')
    conn.executemany('INSERT INTO users VALUES (?, ?, ?)', [('boss', 'x', 1), ('alice', 'x', 0)])
    conn.commit()
    conn.close()
    allowed = tmp_path / 'mnt'
    allowed.mkdir()
    monkeypatch.setenv('ALLOWED_BACKUP_ROOTS', str(allowed))
    monkeypatch.setenv('CONFIG_STORE', str(tmp_path / 'config'))
    monkeypatch.setenv('BACKUP_DEST', str(allowed))
    monkeypatch.setenv('MOCLO_DB', str(directory))
    monkeypatch.setenv('EDITOR_DB', str(tmp_path / 'missing.db'))
    monkeypatch.setenv('SUITE_AUTH', 'proxy')
    module = importlib.reload(importlib.import_module('app'))
    module.app.config.update(TESTING=True, SECRET_KEY='test')
    return module.app.test_client()


def test_a_suite_administrator_is_let_in(suite_console):
    r = suite_console.get('/api/session', headers={'X-Suite-User': 'boss'})
    assert r.get_json()['authenticated'] is True
    assert suite_console.get('/api/archives', headers={'X-Suite-User': 'boss'}).status_code == 200


def test_a_suite_member_is_not(suite_console):
    session = suite_console.get('/api/session', headers={'X-Suite-User': 'alice'}).get_json()
    assert session['authenticated'] is False
    assert session['signed_in_as'] == 'alice'
    assert suite_console.get('/api/archives', headers={'X-Suite-User': 'alice'}).status_code == 401


def test_signing_out_of_the_suite_signs_out_here(suite_console):
    suite_console.get('/api/session', headers={'X-Suite-User': 'boss'})
    assert suite_console.get('/api/archives').status_code == 401


def test_the_console_has_no_sign_in_of_its_own_in_the_suite(suite_console):
    r = suite_console.post('/api/login', json={'username': 'boss', 'password': 'x'})
    assert r.status_code == 403
    assert r.get_json()['login_url'] == '/account/login'


def test_in_the_suite_the_console_is_a_dashboard_tab(suite_console):
    r = suite_console.get('/', headers={'X-Suite-User': 'boss'})
    assert r.status_code == 302 and r.headers['Location'] == '/account/#backups'
    assert suite_console.get('/?embed=1', headers={'X-Suite-User': 'boss'}).status_code == 200
    tabs = suite_console.get('/suite-manifest.json').get_json()['tabs']
    assert tabs == [{'id': 'backups', 'title': 'Backups', 'icon': '💾', 'glyph': 'archive', 'section': 'admin',
                     'roles': ['admin'], 'src': '/backup/?embed=1'}]
