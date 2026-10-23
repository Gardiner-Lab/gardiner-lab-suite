"""
Tests for the suite's sign-in, registration and labs service.

    python -m pytest portal/
"""

import importlib
import sqlite3
import sys
from pathlib import Path

import bcrypt
import pytest

sys.path.insert(0, str(Path(__file__).parent))


def make_directory(path: Path, users):
    conn = sqlite3.connect(path)
    conn.execute('CREATE TABLE users (id TEXT PRIMARY KEY, username TEXT UNIQUE, password_hash TEXT, '
                 'is_admin INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    for username, password, is_admin in users:
        conn.execute('INSERT INTO users (id, username, password_hash, is_admin) VALUES (?, ?, ?, ?)',
                     (username, username,
                      bcrypt.hashpw(password.encode(), bcrypt.gensalt(4)).decode(), int(is_admin)))
    conn.commit()
    conn.close()


def make_editor_db(path: Path):
    """An editor database from before the suite owned labs: labs, codes, members, a lead."""
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE users (id TEXT, username TEXT, password_hash TEXT, lab_source TEXT,
                            is_admin INTEGER, created_at TEXT, role TEXT);
        CREATE TABLE labs (id TEXT PRIMARY KEY, name TEXT, registration_code TEXT,
                           code_updated_by TEXT, code_updated_at TEXT, created_at TEXT);
        INSERT INTO labs VALUES ('lab-g', 'Gardiner Lab', 'old-code-12', 'boss', '2026-10-01', '2026-09-01');
        INSERT INTO labs VALUES ('lab-s', 'Smith Lab', NULL, NULL, NULL, '2026-09-02');
        INSERT INTO users VALUES ('1', 'alice', 'x', 'Gardiner Lab', 0, NULL, 'lab_lead');
        INSERT INTO users VALUES ('2', 'bob', 'x', 'smith lab', 0, NULL, NULL);
        INSERT INTO users VALUES ('3', 'carol', 'x', NULL, 0, NULL, NULL);
    """)
    conn.commit()
    conn.close()


def load(monkeypatch, moclo, editor, suite, **env):
    monkeypatch.setenv('MOCLO_DB', str(moclo))
    monkeypatch.setenv('EDITOR_DB', str(editor))
    monkeypatch.setenv('SUITE_DB', str(suite))
    monkeypatch.setenv('SECRET_KEY', 'test')
    for key in ('DEFAULT_LAB_SOURCE', 'REQUIRE_REGISTRATION_CODE', 'ALLOW_REGISTRATION', 'SUITE_PUBLIC_URL'):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    module = importlib.reload(importlib.import_module('portal'))
    monkeypatch.setattr(module.time, 'sleep', lambda _: None)
    return module


@pytest.fixture()
def portal(tmp_path, monkeypatch):
    moclo = tmp_path / 'moclo.db'
    make_directory(moclo, [('alice', 'alice-password', False), ('boss', 'boss-password', True),
                           ('admin', 'admin123', True)])
    module = load(monkeypatch, moclo, tmp_path / 'missing.db', tmp_path / 'suite.db',
                  DEFAULT_LAB_SOURCE='Gardiner Lab')
    return module, module.app.test_client(), moclo


def sign_in(client, username, password, **extra):
    return client.post('/api/login', json={'username': username, 'password': password, **extra})


def gardiner(module):
    return module.labs.by_name('Gardiner Lab')


# ---------------------------------------------------------------------------
# Signing in
# ---------------------------------------------------------------------------

def check(client, path='/parts'):
    """The proxy's question about one request."""
    return client.get('/api/check', headers={'X-Original-URI': path})


@pytest.mark.parametrize('path', ['/', '/tools.json', '/parts', '/admin?embed=1', '/editor/',
                                  '/editor/api/sequences', '/backup/', '/api/admin/parts',
                                  '/health/../parts', '/healthy', ''])
def test_nothing_is_visible_before_signing_in(portal, path):
    _, client, _ = portal
    assert check(client, path).status_code == 401


@pytest.mark.parametrize('path', ['/health', '/editor/health', '/backup/health', '/health?x=1'])
def test_health_checks_stay_public(portal, path):
    _, client, _ = portal
    r = check(client, path)
    assert r.status_code == 200
    assert 'X-Suite-User' not in r.headers


def test_a_refused_page_visit_goes_to_sign_in_and_back(portal):
    _, client, _ = portal
    r = client.get('/api/signin', headers={'X-Original-URI': '/admin?embed=1&tab=parts',
                                            'Accept': 'text/html,application/xhtml+xml'})
    assert r.status_code == 302
    assert r.headers['Location'] == '/account/login?next=/admin%3Fembed%3D1%26tab%3Dparts'


def test_a_refused_api_call_gets_a_401(portal):
    _, client, _ = portal
    r = client.get('/api/signin', headers={'X-Original-URI': '/api/parts', 'Accept': '*/*'})
    assert r.status_code == 401
    assert r.get_json()['login_url'].startswith('/account/login?next=')
    r = client.post('/api/signin', headers={'X-Original-URI': '/parts', 'Accept': 'text/html'})
    assert r.status_code == 401


def test_sign_in_never_sends_people_off_the_site(portal):
    _, client, _ = portal
    r = client.get('/api/signin', headers={'X-Original-URI': '//evil.example/', 'Accept': 'text/html'})
    assert r.headers['Location'] == '/account/login?next=/'


def test_signed_in_check_names_the_user(portal):
    _, client, _ = portal
    assert sign_in(client, 'alice', 'alice-password').status_code == 200
    assert check(client).headers['X-Suite-User'] == 'alice'
    assert client.get('/api/session').get_json()['user']['username'] == 'alice'


def test_wrong_password_is_refused(portal):
    _, client, _ = portal
    assert sign_in(client, 'alice', 'nope').status_code == 401
    assert sign_in(client, 'nobody', 'alice-password').status_code == 401
    assert check(client).status_code == 401


def test_the_default_password_signs_in_only_to_change_it(portal):
    module, client, _ = portal
    r = sign_in(client, 'admin', 'admin123', next='/parts')
    assert r.status_code == 200
    assert r.get_json()['must_change'] is True and r.get_json()['next'] == '/account/#account'
    assert client.get('/api/session').get_json()['user']['must_change'] is True
    # Nothing opens yet: no tool, no landing page, no administration.
    assert check(client, '/parts').status_code == 401
    assert check(client, '/').status_code == 401
    assert client.get('/api/admin/overview').status_code == 403
    page = client.get('/api/signin', headers={'X-Original-URI': '/parts', 'Accept': 'text/html'})
    assert page.headers['Location'] == '/account/#account'
    # The default cannot be chosen again; a new password opens everything.
    assert client.post('/api/account/password', json={'current': 'admin123', 'new': 'admin123'}).status_code == 400
    assert client.post('/api/account/password', json={'current': 'admin123', 'new': 'a-real-password'}).status_code == 200
    assert check(client, '/parts').headers['X-Suite-User'] == 'admin'
    assert client.get('/api/session').get_json()['user']['must_change'] is False
    assert client.get('/api/admin/overview').status_code == 200
    # And the default no longer works at all.
    assert sign_in(module.app.test_client(), 'admin', 'admin123').status_code == 401


def test_signing_out_ends_it_everywhere(portal):
    _, client, _ = portal
    sign_in(client, 'alice', 'alice-password')
    assert client.post('/api/logout').status_code == 200
    assert check(client).status_code == 401


def test_get_logout_goes_back_to_the_sign_in_page(portal):
    _, client, _ = portal
    r = client.get('/logout')
    assert r.status_code == 302
    assert r.headers['Location'].endswith('/account/login')


def test_a_password_change_ends_old_sessions(portal):
    _, client, moclo = portal
    sign_in(client, 'alice', 'alice-password')
    conn = sqlite3.connect(moclo)
    conn.execute("UPDATE users SET password_hash = ? WHERE username = 'alice'",
                 (bcrypt.hashpw(b'a-new-password', bcrypt.gensalt(4)).decode(),))
    conn.commit()
    conn.close()
    assert check(client).status_code == 401


def test_a_deleted_account_is_signed_out(portal):
    _, client, moclo = portal
    sign_in(client, 'alice', 'alice-password')
    conn = sqlite3.connect(moclo)
    conn.execute("DELETE FROM users WHERE username = 'alice'")
    conn.commit()
    conn.close()
    assert check(client).status_code == 401


def test_a_forged_cookie_is_ignored(portal):
    _, client, _ = portal
    client.set_cookie('lab_suite_session', 'eyJ1c2VybmFtZSI6ImJvc3MifQ.forged.sig')
    assert check(client).status_code == 401


def test_editor_accounts_are_the_fallback(tmp_path, monkeypatch):
    editor = tmp_path / 'editor.db'
    make_directory(editor, [('carol', 'carol-password', False)])
    module = load(monkeypatch, tmp_path / 'missing.db', editor, tmp_path / 'suite.db')
    client = module.app.test_client()
    assert sign_in(client, 'carol', 'carol-password').status_code == 200
    assert check(client).headers['X-Suite-User'] == 'carol'


@pytest.mark.parametrize('target, expected', [
    ('/parts', '/parts'),
    ('/editor/library?x=1', '/editor/library?x=1'),
    ('https://evil.example/', '/'),
    ('//evil.example/', '/'),
    ('/\\evil.example', '/'),
    ('javascript:alert(1)', '/'),
    ('', '/'),
    # Signing in starts at the landing page, not the dashboard.
    ('/account/', '/'),
    ('/account/#users', '/'),
    ('/account', '/'),
    ('/account/login', '/'),
    ('/accounting/report', '/accounting/report'),
])
def test_only_local_pages_are_returned_to(portal, target, expected):
    _, client, _ = portal
    assert sign_in(client, 'alice', 'alice-password', next=target).get_json()['next'] == expected


def test_signed_in_visitors_skip_the_sign_in_page(portal):
    _, client, _ = portal
    sign_in(client, 'alice', 'alice-password')
    r = client.get('/login?next=/parts')
    assert r.status_code == 302
    assert r.headers['Location'].endswith('/parts')


def test_login_needs_json(portal):
    _, client, _ = portal
    r = client.post('/api/login', data={'username': 'alice', 'password': 'alice-password'})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Registering
# ---------------------------------------------------------------------------

def register(client, lab, code, username='dave', password='dave-password', **extra):
    return client.post('/api/register', json={'lab': lab, 'code': code, 'username': username,
                                              'password': password, **extra})


def test_the_default_lab_gets_a_generated_code(portal):
    module, _, _ = portal
    lab = gardiner(module)
    assert lab['registration_code']
    assert len(lab['registration_code'].split('-')) == 4


def test_registering_with_the_labs_code(portal):
    module, client, moclo = portal
    lab = gardiner(module)
    r = register(client, lab['id'], lab['registration_code'].upper() + '  ', next='/parts')
    assert r.status_code == 201, r.get_json()
    assert r.get_json()['next'] == '/parts'
    # In the directory, so every tool knows it, and signed in at once.
    row = sqlite3.connect(moclo).execute("SELECT is_admin FROM users WHERE username = 'dave'").fetchone()
    assert row == (0,)
    assert check(client).headers['X-Suite-User'] == 'dave'
    assert module.labs.membership('dave')['lab'] == 'Gardiner Lab'


def test_a_wrong_code_is_refused(portal):
    module, client, moclo = portal
    r = register(client, gardiner(module)['id'], 'not-the-code')
    assert r.status_code == 403
    assert sqlite3.connect(moclo).execute("SELECT 1 FROM users WHERE username = 'dave'").fetchone() is None


def test_a_closed_lab_takes_nobody(portal):
    module, client, _ = portal
    lab = gardiner(module)
    module.labs.close(lab['id'], 'boss')
    assert register(client, lab['id'], lab['registration_code']).status_code == 403


def test_one_labs_code_does_not_open_another(portal):
    module, client, _ = portal
    other = module.labs.create('Smith Lab', 'boss')
    assert register(client, other['id'], gardiner(module)['registration_code']).status_code == 403


def test_taken_usernames_and_weak_passwords_are_refused(portal):
    module, client, _ = portal
    lab = gardiner(module)
    assert register(client, lab['id'], lab['registration_code'], username='alice').status_code == 400
    assert register(client, lab['id'], lab['registration_code'], password='short').status_code == 400
    assert register(client, lab['id'], lab['registration_code'], username='no spaces').status_code == 400


def test_registration_can_be_closed(tmp_path, monkeypatch):
    make_directory(tmp_path / 'moclo.db', [('boss', 'boss-password', True)])
    module = load(monkeypatch, tmp_path / 'moclo.db', tmp_path / 'missing.db', tmp_path / 'suite.db',
                  DEFAULT_LAB_SOURCE='Gardiner Lab', ALLOW_REGISTRATION='false')
    lab = gardiner(module)
    client = module.app.test_client()
    assert register(client, lab['id'], lab['registration_code']).status_code == 403


def test_the_first_account_needs_no_code_and_runs_the_place(tmp_path, monkeypatch):
    make_directory(tmp_path / 'moclo.db', [])
    module = load(monkeypatch, tmp_path / 'moclo.db', tmp_path / 'missing.db', tmp_path / 'suite.db')
    client = module.app.test_client()
    assert client.get('/api/labs').get_json()['code_required'] is False
    r = register(client, 'Brand New Lab', '', username='founder')
    assert r.status_code == 201, r.get_json()
    assert module.directory.find('founder')['is_admin'] is True
    # And from now on, codes are needed.
    assert client.get('/api/labs').get_json()['code_required'] is True


def test_the_registration_form_never_sees_codes(portal):
    _, client, _ = portal
    body = client.get('/api/labs').get_data(as_text=True)
    assert 'Gardiner Lab' in body
    assert 'registration_code' not in body and '"code"' not in body


# ---------------------------------------------------------------------------
# Labs, codes and roles
# ---------------------------------------------------------------------------

def test_only_administrators_and_lab_leads_see_the_labs(portal):
    module, client, _ = portal
    assert client.get('/api/admin/overview').status_code == 401
    sign_in(client, 'alice', 'alice-password')
    assert client.get('/api/admin/overview').status_code == 403


def test_an_administrator_manages_labs_and_codes(portal):
    module, client, _ = portal
    sign_in(client, 'boss', 'boss-password')
    lab = client.post('/api/admin/labs', json={'name': '  Smith   Lab '}).get_json()['lab']
    assert lab['name'] == 'Smith Lab'
    assert lab['code']                                    # generated straight away
    old = lab['code']
    lab = client.post(f'/api/admin/labs/{lab["id"]}/code').get_json()['lab']
    assert lab['code'] and lab['code'] != old and lab['code_updated_by'] == 'boss'
    lab = client.delete(f'/api/admin/labs/{lab["id"]}/code').get_json()['lab']
    assert lab['code'] is None
    assert client.patch(f'/api/admin/labs/{lab["id"]}', json={'name': 'Jones Lab'}).status_code == 200
    assert client.post('/api/admin/labs', json={'name': 'jones lab'}).status_code == 400
    assert client.delete(f'/api/admin/labs/{lab["id"]}').status_code == 200


def test_an_administrator_puts_labs_in_chair_groups(portal):
    module, client, _ = portal
    lab = gardiner(module)
    module.labs.set_lab('alice', lab['id'])
    module.labs.set_role('alice', 'lab_admin', lab['id'])
    # Only an administrator: a lab admin sees their lab's chair group, and changes nothing.
    sign_in(client, 'alice', 'alice-password')
    assert client.post('/api/admin/chair-groups', json={'name': 'Plant Biology'}).status_code == 403
    assert client.put(f'/api/admin/labs/{lab["id"]}/chair-group', json={'chair_group_id': 'x'}).status_code == 403
    client.post('/api/logout')
    sign_in(client, 'boss', 'boss-password')
    assert client.post('/api/admin/chair-groups', json={'name': ' '}).status_code == 400
    group = client.post('/api/admin/chair-groups', json={'name': ' Plant   Biology '}).get_json()['chair_group']
    assert group['name'] == 'Plant Biology' and group['labs'] == []
    assert client.post('/api/admin/chair-groups', json={'name': 'plant biology'}).status_code == 400
    smith = client.post('/api/admin/labs', json={'name': 'Smith Lab'}).get_json()['lab']
    jones = client.post('/api/admin/labs', json={'name': 'Jones Lab'}).get_json()['lab']
    for one in (lab, smith):
        assert client.put(f'/api/admin/labs/{one["id"]}/chair-group',
                          json={'chair_group_id': group['id']}).get_json()['lab']['chair_group'] == 'Plant Biology'
    assert client.put(f'/api/admin/labs/{jones["id"]}/chair-group', json={'chair_group_id': 'nope'}).status_code == 404
    seen = client.get('/api/admin/overview').get_json()
    assert [g['labs'] for g in seen['chair_groups']] == [['Gardiner Lab', 'Smith Lab']]
    assert {x['name']: x['chair_group'] for x in seen['labs']} == {'Gardiner Lab': 'Plant Biology', 'Jones Lab': None,
                                                                    'Smith Lab': 'Plant Biology'}
    assert client.patch(f'/api/admin/chair-groups/{group["id"]}', json={'name': 'Plant Ecophysiology'}).status_code == 200
    # Out of it again: none.
    client.put(f'/api/admin/labs/{smith["id"]}/chair-group', json={'chair_group_id': ''})
    client.post('/api/logout')
    sign_in(client, 'alice', 'alice-password')
    mine = client.get('/api/admin/overview').get_json()
    assert mine['labs'][0]['chair_group'] == 'Plant Ecophysiology'
    assert [g['labs'] for g in mine['chair_groups']] == [['Gardiner Lab']]
    client.post('/api/logout')
    sign_in(client, 'boss', 'boss-password')
    # Removed: its labs stay, in none.
    assert client.delete(f'/api/admin/chair-groups/{group["id"]}').status_code == 200
    assert gardiner(module)['chair_group_id'] is None
    assert client.delete(f'/api/admin/chair-groups/{group["id"]}').status_code == 404


def test_a_suite_database_from_before_gets_chair_groups(tmp_path, monkeypatch):
    make_directory(tmp_path / 'moclo.db', [('boss', 'boss-password', True)])
    conn = sqlite3.connect(tmp_path / 'suite.db')
    conn.executescript("""
        CREATE TABLE labs (id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE, registration_code TEXT,
                           code_updated_by TEXT, code_updated_at TIMESTAMP, created_at TIMESTAMP);
        INSERT INTO labs (id, name) VALUES ('lab-g', 'Gardiner Lab');
    """)
    conn.commit()
    conn.close()
    module = load(monkeypatch, tmp_path / 'moclo.db', tmp_path / 'missing.db', tmp_path / 'suite.db')
    assert module.labs.get('lab-g')['chair_group_id'] is None and module.labs.chair_groups() == []


def test_a_lab_with_members_cannot_be_removed(portal):
    module, client, _ = portal
    lab = gardiner(module)
    module.labs.set_lab('alice', lab['id'])
    sign_in(client, 'boss', 'boss-password')
    assert client.delete(f'/api/admin/labs/{lab["id"]}').status_code == 400


def test_roles_and_labs_are_set_here(portal):
    module, client, moclo = portal
    lab = gardiner(module)
    sign_in(client, 'boss', 'boss-password')
    # A lab lead needs a lab first.
    assert client.put('/api/admin/users/alice/role', json={'role': 'lab_lead'}).status_code == 400
    assert client.put('/api/admin/users/alice/lab', json={'lab_id': lab['id']}).status_code == 200
    assert client.put('/api/admin/users/alice/role', json={'role': 'lab_lead'}).status_code == 200
    assert module.labs.membership('alice')['role'] == 'lab_lead'
    # Administrator status goes to the directory, where every tool reads it.
    assert client.put('/api/admin/users/alice/role', json={'role': 'admin'}).status_code == 200
    assert module.directory.find('alice')['is_admin'] is True
    assert module.labs.membership('alice')['role'] == 'member'
    assert client.put('/api/admin/users/boss/role', json={'role': 'member'}).status_code == 400


def test_a_lab_lead_sees_their_own_lab_read_only(portal):
    module, client, _ = portal
    lab = gardiner(module)
    other = module.labs.create('Smith Lab', 'boss')
    module.labs.set_lab('alice', lab['id'])
    module.labs.set_lab_lead('alice', True)
    sign_in(client, 'alice', 'alice-password')
    body = client.get('/api/admin/overview').get_json()
    assert body['can_manage'] is False
    assert [l['name'] for l in body['labs']] == ['Gardiner Lab']
    assert body['labs'][0]['code'] == lab['registration_code']
    assert [u['username'] for u in body['users']] == ['alice']
    assert client.post(f'/api/admin/labs/{lab["id"]}/code').status_code == 403
    assert client.post('/api/admin/labs', json={'name': 'Mine'}).status_code == 403
    assert client.put('/api/admin/users/boss/lab', json={'lab_id': other['id']}).status_code == 403


def test_the_editors_labs_are_brought_over_once(tmp_path, monkeypatch):
    make_directory(tmp_path / 'moclo.db', [('boss', 'boss-password', True)])
    make_editor_db(tmp_path / 'editor.db')
    module = load(monkeypatch, tmp_path / 'moclo.db', tmp_path / 'editor.db', tmp_path / 'suite.db',
                  DEFAULT_LAB_SOURCE='Gardiner Lab')
    labs = {lab['name']: lab for lab in module.labs.all_labs()}
    assert set(labs) == {'Gardiner Lab', 'Smith Lab'}
    # The code people were already given keeps working; a closed lab stays closed.
    assert labs['Gardiner Lab']['registration_code'] == 'old-code-12'
    assert labs['Smith Lab']['registration_code'] is None
    assert module.labs.membership('alice') == {'username': 'alice', 'lab_id': 'lab-g',
                                               'role': 'lab_lead', 'lab': 'Gardiner Lab'}
    assert module.labs.membership('bob')['lab'] == 'Smith Lab'
    assert module.labs.membership('carol')['lab'] is None

    # A second start changes nothing, even after an administrator removed a lab.
    module.labs.set_lab('bob', 'lab-g')
    module.labs.delete('lab-s')
    module = load(monkeypatch, tmp_path / 'moclo.db', tmp_path / 'editor.db', tmp_path / 'suite.db',
                  DEFAULT_LAB_SOURCE='Gardiner Lab')
    assert [lab['name'] for lab in module.labs.all_labs()] == ['Gardiner Lab']


# ---------------------------------------------------------------------------
# The dashboard: your account, and every account
# ---------------------------------------------------------------------------

def test_the_dashboard_needs_signing_in(portal):
    _, client, _ = portal
    r = client.get('/')
    assert r.status_code == 302 and '/account/login' in r.headers['Location']
    sign_in(client, 'alice', 'alice-password')
    assert client.get('/').status_code == 200
    assert client.get('/admin').headers['Location'].endswith('/account/#labs')


def test_changing_your_own_password_keeps_you_signed_in(portal):
    module, client, _ = portal
    sign_in(client, 'alice', 'alice-password')
    other = module.app.test_client()
    sign_in(other, 'alice', 'alice-password')
    assert client.post('/api/account/password',
                       json={'current': 'wrong', 'new': 'brand-new-pw'}).status_code == 403
    assert client.post('/api/account/password',
                       json={'current': 'alice-password', 'new': 'short'}).status_code == 400
    assert client.post('/api/account/password',
                       json={'current': 'alice-password', 'new': 'brand-new-pw'}).status_code == 200
    assert check(client).headers['X-Suite-User'] == 'alice'
    assert check(other).status_code == 401      # the other session ended
    assert sign_in(module.app.test_client(), 'alice', 'brand-new-pw').status_code == 200


def test_an_administrator_adds_and_removes_accounts(portal):
    module, client, moclo = portal
    lab = gardiner(module)
    sign_in(client, 'boss', 'boss-password')
    r = client.post('/api/admin/users', json={'username': 'erin', 'password': 'erin-password',
                                              'lab_id': lab['id'], 'role': 'lab_lead'})
    assert r.status_code == 201, r.get_json()
    assert module.labs.membership('erin')['role'] == 'lab_lead'
    assert module.directory.find('erin')['is_admin'] is False
    assert sign_in(module.app.test_client(), 'erin', 'erin-password').status_code == 200

    r = client.post('/api/admin/users', json={'username': 'frank', 'password': 'frank-password',
                                              'role': 'admin'})
    assert r.status_code == 201
    assert module.directory.find('frank')['is_admin'] is True
    assert client.post('/api/admin/users', json={'username': 'erin', 'password': 'x' * 8}).status_code == 400
    assert client.post('/api/admin/users', json={'username': 'gina', 'password': 'gina-password',
                                                 'role': 'lab_lead'}).status_code == 400

    assert client.delete('/api/admin/users/erin').status_code == 200
    assert module.directory.find('erin') is None
    assert module.labs.memberships().get('erin') is None
    assert client.delete('/api/admin/users/boss').status_code == 400        # yourself
    assert client.delete('/api/admin/users/nobody').status_code == 404


def test_an_account_that_owns_records_is_kept(portal):
    module, client, moclo = portal
    conn = sqlite3.connect(moclo)
    conn.execute('CREATE TABLE cassettes (id TEXT, owner_id TEXT REFERENCES users(id))')
    conn.execute("INSERT INTO cassettes VALUES ('c1', 'alice')")
    conn.commit()
    conn.close()
    sign_in(client, 'boss', 'boss-password')
    r = client.delete('/api/admin/users/alice')
    assert r.status_code == 400
    assert 'owns' in r.get_json()['error']
    assert module.directory.find('alice') is not None


def test_an_administrator_sets_a_forgotten_password(portal):
    module, client, _ = portal
    alice = module.app.test_client()
    sign_in(alice, 'alice', 'alice-password')
    sign_in(client, 'boss', 'boss-password')
    assert client.put('/api/admin/users/alice/password', json={'password': 'short'}).status_code == 400
    assert client.put('/api/admin/users/alice/password', json={'password': 'reset-pw-123'}).status_code == 200
    assert check(alice).status_code == 401
    assert sign_in(module.app.test_client(), 'alice', 'reset-pw-123').status_code == 200
    assert client.put('/api/admin/users/boss/password', json={'password': 'whatever-1'}).status_code == 400


def test_only_administrators_manage_accounts(portal):
    module, client, _ = portal
    lab = gardiner(module)
    module.labs.set_lab('alice', lab['id'])
    module.labs.set_lab_lead('alice', True)
    sign_in(client, 'alice', 'alice-password')
    assert client.post('/api/admin/users', json={'username': 'x1x', 'password': 'x' * 8}).status_code == 403
    assert client.delete('/api/admin/users/boss').status_code == 403
    assert client.put('/api/admin/users/boss/password', json={'password': 'x' * 8}).status_code == 403


def test_each_sign_in_has_its_own_id_for_the_tools(portal):
    """What a tool keeps until signing out (the editor's tabs) is keyed by this."""
    _, client, _ = portal
    sign_in(client, 'alice', 'alice-password')
    first = check(client).headers['X-Suite-Session']
    assert first and check(client).headers['X-Suite-Session'] == first      # the same while signed in
    client.post('/api/logout')
    assert 'X-Suite-Session' not in check(client, '/health').headers
    sign_in(client, 'alice', 'alice-password')
    assert check(client).headers['X-Suite-Session'] != first               # a new one after signing in again


def test_a_lab_admin_adds_people_to_their_lab_and_takes_them_out(portal):
    module, client, moclo = portal
    lab = gardiner(module)
    other = module.labs.create('Smith Lab', 'boss')
    for name in ('dave', 'erin', 'fred', 'gina', 'hana'):
        module.directory.create(name, f'{name}-password-1', is_admin=False)
    module.labs.set_lab('alice', lab['id'])
    module.labs.set_role('alice', 'lab_admin', lab['id'])
    module.labs.set_lab('dave', lab['id'])
    module.labs.set_lab('erin', lab['id'])
    module.labs.set_role('erin', 'lab_lead', lab['id'])
    module.labs.set_lab('fred', other['id'])
    module.labs.set_lab('hana', lab['id'])
    module.labs.set_role('hana', 'lab_admin', lab['id'])
    # Every other tool reads only whether someone leads a lab: a lab admin does.
    conn = sqlite3.connect(module.labs.db_path())
    assert conn.execute("SELECT role FROM members WHERE username = 'alice'").fetchone()[0] == 'lab_lead'

    sign_in(client, 'alice', 'alice-password')
    assert client.get('/api/session').get_json()['user']['role'] == 'lab_admin'
    body = client.get('/api/admin/overview').get_json()
    assert body['can_manage'] is False and body['can_manage_members'] is True and body['manages'] == [lab['id']]
    assert [l['name'] for l in body['labs']] == ['Gardiner Lab']
    assert {u['username']: u['labs'][0]['role'] for u in body['users']} == \
        {'alice': 'lab_admin', 'dave': 'member', 'erin': 'lab_lead', 'hana': 'lab_admin'}
    assert 'fred' in body['addable'] and 'boss' not in body['addable']

    members = f"/api/lab/{lab['id']}/members"
    # A new account, straight into the lab.
    made = client.post(members, json={'username': 'ivan', 'password': 'ivan-password-1'})
    assert made.status_code == 201 and made.get_json()['created'] is True
    assert module.labs.labs_of('ivan') == [{'lab_id': lab['id'], 'lab': 'Gardiner Lab', 'role': 'member'}]
    assert not module.directory.find('ivan')['is_admin']
    # Someone with no lab, and someone from another lab, who stays in it too; always as a member.
    assert client.post(members, json={'username': 'gina', 'role': 'lab_admin'}).status_code == 201
    assert module.labs.labs_of('gina')[0]['role'] == 'member'
    assert client.post(members, json={'username': 'fred'}).status_code == 201
    assert [m['lab'] for m in module.labs.labs_of('fred')] == ['Smith Lab', 'Gardiner Lab']
    assert client.post(members, json={'username': 'fred'}).status_code == 400          # in it already
    assert client.post(members, json={'username': 'boss'}).status_code == 400
    assert client.post(members, json={'username': 'nobody'}).status_code == 404
    assert client.post(members, json={'username': 'jo', 'password': 'admin123'}).status_code == 400
    # Taking out: of this lab only; members and lab leads, not lab admins, administrators, or oneself.
    assert client.delete(f'{members}/fred').status_code == 200
    assert [m['lab'] for m in module.labs.labs_of('fred')] == ['Smith Lab']
    assert client.delete(f'{members}/dave').status_code == 200
    assert module.labs.labs_of('dave') == [] and module.directory.find('dave') is not None
    assert client.delete(f'{members}/erin').status_code == 200
    assert client.delete(f'{members}/hana').status_code == 403
    assert client.delete(f'{members}/alice').status_code == 400
    assert client.delete(f'{members}/dave').status_code == 400       # not in this lab
    # Only labs they are lab admin of; nothing an administrator alone does.
    assert client.post(f"/api/lab/{other['id']}/members", json={'username': 'gina'}).status_code == 403
    assert client.delete(f"/api/lab/{other['id']}/members/fred").status_code == 403
    assert client.put(f"{members}/gina", json={'role': 'lab_lead'}).status_code == 403
    assert client.put('/api/admin/users/gina/role', json={'role': 'lab_lead'}).status_code == 403
    assert client.delete('/api/admin/users/gina').status_code == 403
    assert client.post(f"/api/admin/labs/{lab['id']}/code").status_code == 403


def test_a_lab_lead_does_not_add_or_remove_people(portal):
    module, client, _ = portal
    lab = gardiner(module)
    module.directory.create('dave', 'dave-password-1', is_admin=False)
    module.labs.set_lab('alice', lab['id'])
    module.labs.set_role('alice', 'lab_lead', lab['id'])
    module.labs.set_lab('dave', lab['id'])
    sign_in(client, 'alice', 'alice-password')
    body = client.get('/api/admin/overview').get_json()
    assert body['can_manage_members'] is False and body['addable'] == []
    assert client.post(f"/api/lab/{lab['id']}/members", json={'username': 'x1', 'password': 'pass-word-1'}).status_code == 403
    assert client.delete(f"/api/lab/{lab['id']}/members/dave").status_code == 403


def test_people_belong_to_several_labs_with_a_role_in_each(portal):
    module, client, _ = portal
    lab = gardiner(module)
    other = module.labs.create('Smith Lab', 'boss')
    third = module.labs.create('Jones Lab', 'boss')
    module.labs.set_lab('alice', lab['id'])                     # registered here
    sign_in(client, 'boss', 'boss-password')
    # An administrator adds her to two more labs, leading one; and sets her role per lab.
    assert client.post(f"/api/lab/{other['id']}/members", json={'username': 'alice', 'role': 'lab_lead'}).status_code == 201
    assert client.post(f"/api/lab/{third['id']}/members", json={'username': 'alice'}).status_code == 201
    assert client.put(f"/api/lab/{third['id']}/members/alice", json={'role': 'lab_admin'}).status_code == 200
    assert {m['lab']: m['role'] for m in module.labs.labs_of('alice')} == \
        {'Gardiner Lab': 'member', 'Smith Lab': 'lab_lead', 'Jones Lab': 'lab_admin'}
    users = {u['username']: u for u in client.get('/api/admin/overview').get_json()['users']}
    assert [m['lab'] for m in users['alice']['labs']] == ['Gardiner Lab', 'Smith Lab', 'Jones Lab']
    assert users['alice']['role'] == 'lab_admin' and users['alice']['lab'] == 'Gardiner Lab'
    assert {lab_['name']: lab_['members'] for lab_ in client.get('/api/admin/overview').get_json()['labs']} == \
        {'Gardiner Lab': 1, 'Jones Lab': 1, 'Smith Lab': 1}
    # Tools that read one lab see her first, with her role there.
    conn = sqlite3.connect(module.labs.db_path())
    assert conn.execute("SELECT lab_id, role FROM members WHERE username = 'alice'").fetchone() == (lab['id'], 'member')
    # As lab admin of Jones Lab only, she manages that lab and no other; she sees the labs she leads.
    client.post('/api/logout')
    sign_in(client, 'alice', 'alice-password')
    body = client.get('/api/admin/overview').get_json()
    assert body['manages'] == [third['id']] and {l['name'] for l in body['labs']} == {'Smith Lab', 'Jones Lab'}
    assert client.post(f"/api/lab/{other['id']}/members", json={'username': 'boss'}).status_code == 403
    assert [m['lab'] for m in client.get('/api/session').get_json()['user']['labs']] == \
        ['Gardiner Lab', 'Smith Lab', 'Jones Lab']
    # Out of her first lab, the next one is her first; a lab with members cannot be deleted.
    client.post('/api/logout')
    sign_in(client, 'boss', 'boss-password')
    assert client.delete(f"/api/admin/labs/{other['id']}").status_code == 400
    assert client.delete(f"/api/lab/{lab['id']}/members/alice").status_code == 200
    assert conn.execute("SELECT lab_id, role FROM members WHERE username = 'alice'").fetchone() == (other['id'], 'lab_lead')


def test_one_lab_each_from_before_becomes_their_first(tmp_path, monkeypatch):
    """A suite database from before several labs: its members table is carried over, once."""
    moclo = tmp_path / 'moclo.db'
    make_directory(moclo, [('alice', 'alice-password', False), ('boss', 'boss-password', True)])
    suite = tmp_path / 'suite.db'
    conn = sqlite3.connect(suite)
    conn.executescript("""
        CREATE TABLE labs (id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE, registration_code TEXT,
                           code_updated_by TEXT, code_updated_at TIMESTAMP, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE members (username TEXT PRIMARY KEY, lab_id TEXT REFERENCES labs(id),
                              role TEXT NOT NULL DEFAULT 'member', joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO settings VALUES ('imported_from_editor', '0'), ('default_lab', 'Gardiner Lab');
        INSERT INTO labs (id, name) VALUES ('lab-g', 'Gardiner Lab');
        INSERT INTO members (username, lab_id, role) VALUES ('alice', 'lab-g', 'lab_lead');
    """)
    conn.commit()
    conn.close()
    module = load(monkeypatch, moclo, tmp_path / 'missing.db', suite)
    assert module.labs.labs_of('alice') == [{'lab_id': 'lab-g', 'lab': 'Gardiner Lab', 'role': 'lab_lead'}]
    # Taken out of it later, she stays out: the carrying over happens once.
    module.labs.remove('alice', 'lab-g')
    module = load(monkeypatch, moclo, tmp_path / 'missing.db', suite)
    assert module.labs.labs_of('alice') == []


def test_an_administrator_makes_someone_lab_admin(portal):
    module, client, _ = portal
    lab = gardiner(module)
    sign_in(client, 'boss', 'boss-password')
    assert 'lab_admin' in client.get('/api/admin/overview').get_json()['roles']
    assert client.put('/api/admin/users/alice/role', json={'role': 'lab_admin'}).status_code == 400   # no lab yet
    client.put('/api/admin/users/alice/lab', json={'lab_id': lab['id']})
    assert client.put('/api/admin/users/alice/role', json={'role': 'lab_admin'}).status_code == 200
    assert module.labs.membership('alice')['role'] == 'lab_admin'
    assert client.put('/api/admin/users/alice/role', json={'role': 'lab_lead'}).status_code == 200
    assert module.labs.membership('alice')['role'] == 'lab_lead'
    made = client.post('/api/admin/users', json={'username': 'kim', 'password': 'kim-password-1',
                                                 'lab_id': lab['id'], 'role': 'lab_admin'})
    assert made.status_code == 201 and module.labs.membership('kim')['role'] == 'lab_admin'
    # An administrator manages any lab's members too.
    assert client.delete(f"/api/lab/{lab['id']}/members/kim").status_code == 200


# ---------------------------------------------------------------------------
# Hosting: guesses, HSTS and the Hosting tab
# ---------------------------------------------------------------------------

def try_password(client, username, password, address):
    return client.post('/api/login', json={'username': username, 'password': password}, headers={'X-Real-IP': address})


def test_too_many_wrong_passwords_stop_that_address_only(portal):
    module, client, _ = portal
    for _ in range(module.GUESSES):
        assert try_password(client, 'Alice', 'nope', '203.0.113.9').status_code == 401
    # Even the right password, from there, waits.
    res = try_password(client, 'alice', 'alice-password', '203.0.113.9')
    assert res.status_code == 429 and int(res.headers['Retry-After']) > 0
    assert 'Try again in 15 minutes' in res.get_json()['error']
    # Alice herself, elsewhere, signs in; and so does anyone else from there.
    assert try_password(client, 'alice', 'alice-password', '198.51.100.1').status_code == 200
    assert try_password(client, 'boss', 'boss-password', '203.0.113.9').status_code == 200


def test_wrong_passwords_are_forgotten_on_success_and_after_the_window(portal, monkeypatch):
    module, client, _ = portal
    for _ in range(module.GUESSES - 1):
        try_password(client, 'alice', 'nope', '203.0.113.9')
    assert try_password(client, 'alice', 'alice-password', '203.0.113.9').status_code == 200
    for _ in range(module.GUESSES - 1):     # counted from nothing again
        assert try_password(client, 'alice', 'nope', '203.0.113.9').status_code == 401
    try_password(client, 'alice', 'nope', '203.0.113.9')
    assert try_password(client, 'alice', 'alice-password', '203.0.113.9').status_code == 429
    later = module.time.time() + module.GUESS_WINDOW + 1
    monkeypatch.setattr(module.time, 'time', lambda: later)
    assert try_password(client, 'alice', 'alice-password', '203.0.113.9').status_code == 200


@pytest.fixture()
def no_proxy(portal, monkeypatch):
    """The certificate check reaches no proxy in tests."""
    monkeypatch.setattr(portal[0], 'served_certificate', lambda host: {'checked_for': host})
    return portal


def test_only_administrators_see_and_change_hosting(no_proxy):
    module, client, _ = no_proxy
    sign_in(client, 'alice', 'alice-password')
    assert client.get('/api/admin/hosting').status_code == 403
    assert client.put('/api/admin/hosting', json={'allow_registration': False}).status_code == 403


def test_hosting_settings_start_from_env_and_are_changed_on_the_dashboard(tmp_path, monkeypatch):
    moclo = tmp_path / 'moclo.db'
    make_directory(moclo, [('boss', 'boss-password', True), ('admin', 'admin123', True)])
    module = load(monkeypatch, moclo, tmp_path / 'missing.db', tmp_path / 'suite.db', DEFAULT_LAB_SOURCE='Gardiner Lab',
                  SUITE_PUBLIC_URL='https://lab.example.org/', ALLOW_REGISTRATION='false')
    monkeypatch.setattr(module, 'served_certificate', lambda host: {'checked_for': host})
    client = module.app.test_client()
    sign_in(client, 'boss', 'boss-password')
    data = client.get('/api/admin/hosting').get_json()
    assert data['settings']['public_url'] == {'value': 'https://lab.example.org', 'from': 'env', 'env': 'SUITE_PUBLIC_URL'}
    assert data['settings']['allow_registration']['value'] is False
    assert data['settings']['require_registration_code'] == {'value': True, 'from': 'default', 'env': 'REQUIRE_REGISTRATION_CODE'}
    assert data['status']['certificate'] == {'checked_for': 'lab.example.org'}
    assert data['status']['admins_on_default_password'] == ['admin']
    assert data['status']['hsts'] is True
    # Changed here, it counts instead of .env's; null goes back to .env's.
    settings = client.put('/api/admin/hosting', json={'public_url': 'Suite.Example.org/lab', 'allow_registration': True,
                                                      'require_registration_code': False}).get_json()['settings']
    assert settings['public_url']['value'] == 'https://suite.example.org/lab' and settings['public_url']['from'] == 'dashboard'
    assert module.labs.registration_open() and not module.labs.code_required()
    client.put('/api/admin/hosting', json={'allow_registration': None, 'public_url': ''})
    assert not module.labs.registration_open() and module.labs.public_url() == ''


def test_hosting_settings_are_checked(no_proxy):
    module, client, _ = no_proxy
    sign_in(client, 'boss', 'boss-password')
    for bad in ({'public_url': 'ftp://x'}, {'public_url': 'https://'}, {'public_url': 'https://a b'},
                {'public_url': 'https://lab.example.org/?x=1'}, {'allow_registration': 'yes'}, {'colour': 'red'}):
        assert client.put('/api/admin/hosting', json=bad).status_code == 400, bad


def test_registration_closed_on_the_dashboard_closes_it(no_proxy):
    module, client, _ = no_proxy
    sign_in(client, 'boss', 'boss-password')
    client.put('/api/admin/hosting', json={'allow_registration': False})
    client.post('/api/logout')
    assert client.get('/api/labs').get_json()['registration_open'] is False
    res = client.post('/api/register', json={'username': 'zed', 'password': 'zed-password-1', 'lab': 'Gardiner Lab',
                                             'code': gardiner(module)['registration_code']})
    assert res.status_code == 403


def test_hsts_only_on_the_public_https_address(no_proxy):
    module, client, _ = no_proxy
    assert 'Strict-Transport-Security' not in client.get('/login').headers
    module.labs.set_hosting('public_url', 'https://lab.example.org')
    assert client.get('/login', headers={'Host': 'lab.example.org'}).headers['Strict-Transport-Security'] == 'max-age=31536000'
    assert 'Strict-Transport-Security' not in client.get('/login', headers={'Host': 'localhost'}).headers
    assert 'Strict-Transport-Security' not in client.get('/api/check', headers={'Host': 'lab.example.org'}).headers
    module.labs.set_hosting('public_url', 'http://lab.example.org')
    assert 'Strict-Transport-Security' not in client.get('/login', headers={'Host': 'lab.example.org'}).headers


def test_a_certificate_is_matched_to_the_host(portal):
    module = portal[0]
    assert module._covers(['lab.example.org'], 'LAB.example.org')
    assert module._covers(['*.example.org'], 'lab.example.org')
    assert not module._covers(['*.example.org'], 'a.lab.example.org')
    assert not module._covers(['localhost'], 'lab.example.org')

