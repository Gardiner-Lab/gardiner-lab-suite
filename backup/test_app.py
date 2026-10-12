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
