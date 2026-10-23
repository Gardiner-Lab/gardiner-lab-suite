"""
Sign-in, registration and labs for the whole Gardiner Lab suite.

One sign-in page, one session, every tool. The proxy asks this service who is
signed in before every request to a tool (nginx ``auth_request`` on
``/api/check``), and passes the answer on as an ``X-Suite-User`` header. Each
tool, started with ``SUITE_AUTH=proxy``, takes that header as the person's
identity instead of keeping a sign-in of its own, so signing in or out here
signs in or out of all of them at once.

New members register here too: they choose their lab and give that lab's
registration code, which this service generates (``labs.py``). Which lab
someone is in, and who leads each lab, is kept here for every tool to read.

And it serves the suite's one dashboard, at the root of its prefix: your
account, the labs, every account, and a tab for each tool's own controls,
which each tool lists in its suite-manifest.json (see pages/dashboard.html).

Three things shape the design:

* **The account directory stays where it is.** The MoClo tool's ``users``
  table is the suite's directory (``directory.py``). This service adds
  accounts to it and changes who is an administrator, and nothing else.

* **The session is a signed cookie**, so this service keeps no session state
  and a restart signs nobody out. Every check still looks the account up, so a
  deleted account or a changed password ends its sessions at the next request.

* **Nothing is visible before signing in.** The check refuses anonymous
  visitors everywhere except this service's own pages (sign in, register) and
  the tools' health checks, so the landing page and every tool, present or
  added later, are behind the one sign-in. A refused page visit is sent to the
  sign-in page and comes back afterwards; a refused API call gets a 401.
"""

import hashlib
import os
import time
import uuid
from datetime import timedelta
from functools import wraps
from pathlib import Path
from urllib.parse import quote, urlsplit

from flask import Flask, jsonify, make_response, redirect, request, send_file, session

import directory
import labs

APP_VERSION = '2.9.9'

# The first administrator's password on a new installation (MoClo creates
# 'admin' with it). It is published, so it may be used once only: whoever
# signs in with it is asked to choose a new password, and until they do the
# only thing open to them is that (see must_change below).
MOCLO_DEFAULT_PASSWORD = 'admin123'

# Where people land after signing in, when the page they came from is unknown.
HOME = os.environ.get('SUITE_HOME_URL', '/')
# Where the proxy mounts this service. It strips the prefix before passing a
# request on, so redirects have to put it back.
PREFIX = '/' + os.environ.get('URL_PREFIX', '/account').strip('/')
PAGES = Path(__file__).parent / 'pages'

app = Flask(__name__, static_folder=None)
app.config.update(
    SECRET_KEY=os.environ.get('SECRET_KEY') or os.urandom(32).hex(),
    # Path "/" because the proxy's check needs it on every tool's requests. The
    # name is the suite's own, so it never collides with a tool's cookie.
    SESSION_COOKIE_NAME='lab_suite_session',
    SESSION_COOKIE_PATH='/',
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(days=int(os.environ.get('SESSION_DAYS', '14'))),
)
if os.environ.get('SESSION_COOKIE_SECURE', '').lower() in ('1', 'true', 'yes'):
    app.config['SESSION_COOKIE_SECURE'] = True

labs.prepare(directory.editor_db())


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def password_stamp(password_hash: str) -> str:
    """
    A short fingerprint of the stored hash, kept in the session. Changing the
    password changes it, which ends every session made with the old one.
    """
    return hashlib.sha256((password_hash or '').encode()).hexdigest()[:16]


def must_change() -> bool:
    """Signed in with the published default password, and not yet chosen a new one."""
    return bool(session.get('must_change'))


def signed_in_account():
    """The account behind the current session, or None (clearing a stale one)."""
    username = session.get('username')
    if not username:
        return None
    account = directory.find(username)
    if account is None or session.get('stamp') != password_stamp(account['password_hash']):
        session.clear()
        return None
    return account


def start_session(account) -> None:
    session.clear()
    session['username'] = account['username']
    session['stamp'] = password_stamp(account['password_hash'])
    # This sign-in's own id, passed to the tools (X-Suite-Session) for what
    # they keep until signing out, such as the editor's open tabs.
    session['sid'] = uuid.uuid4().hex
    session.permanent = True


def safe_next(target: str) -> str:
    """
    Where to go after signing in: back to the page someone was opening, if it
    is a page of one of the tools; otherwise, and never to another host, the
    lab tools' landing page. Not to this service's own pages, the dashboard
    included: signing in starts at the landing page.
    """
    target = (target or '').strip()
    parts = urlsplit(target)
    if (not target.startswith('/') or target.startswith('//') or '\\' in target
            or parts.scheme or parts.netloc):
        return HOME
    if parts.path == PREFIX or parts.path.startswith(PREFIX + '/'):
        return HOME
    return target


def json_body() -> dict:
    """
    JSON only, for everything that changes something: a cross-site form cannot
    send it without the browser asking first, which is this service's
    protection against requests forged by someone else's page.
    """
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def role_of(account) -> str:
    """
    'admin', or their highest role in any of their labs: 'lab_admin',
    'lab_lead' or 'member'. What the dashboard shows them; in each lab, their
    role there is what counts (labs.role_in).
    """
    if account['is_admin']:
        return 'admin'
    return max((m['role'] for m in labs.labs_of(account['username'])), key=labs.RANK.get, default='member')


def managed_labs(account, role, at_least='lab_lead') -> set:
    """The labs this person runs: every lab for an admin; those they lead (or, with 'lab_admin', admin)."""
    if role == 'admin':
        return {lab['id'] for lab in labs.all_labs()}
    return {m['lab_id'] for m in labs.labs_of(account['username'])
            if labs.RANK[m['role']] >= labs.RANK[at_least]}


# ---------------------------------------------------------------------------
# The proxy's question: who is this?
# ---------------------------------------------------------------------------

# What anyone may reach without signing in, besides this service itself: the
# tools' health checks, for monitoring. They say "healthy" and nothing more.
PUBLIC_PATHS = frozenset({'/health', '/editor/health', '/notebook/health', '/seeds/health', '/stocks/health', '/backup/health'})


def requested_path() -> str:
    """The path of the request the proxy is asking about, without its query."""
    return urlsplit(request.headers.get('X-Original-URI', '')).path


@app.route('/api/check')
def check():
    """
    Called by nginx before every request it passes on. 200 for someone signed
    in, with their username in a header the proxy copies onto the request; 200
    without one for a public path; 401 otherwise, which the proxy turns into
    the sign-in page (see /api/signin).
    """
    account = signed_in_account()
    # Signed in with the default password: nothing opens until it is changed.
    if account is not None and must_change():
        account = None
    if account is None and requested_path() not in PUBLIC_PATHS:
        response = make_response('', 401)
    else:
        response = make_response('', 200)
        if account is not None:
            response.headers['X-Suite-User'] = account['username']
            # Only a sign-in that has an id (any made since ids were added): this
            # answer goes to the proxy, not the browser, so one made up here
            # would not be kept.
            if session.get('sid'):
                response.headers['X-Suite-Session'] = session['sid']
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.route('/api/signin', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'])
def signin_first():
    """
    What the proxy answers instead, when the check refused: a page visit goes to
    the sign-in page and comes back to that page afterwards; anything else (a
    script's API call) gets a 401 it can act on.
    """
    target = request.headers.get('X-Original-URI', '') or '/'
    login = f'{PREFIX}/login?next={quote(safe_next(target), safe="/")}'
    if signed_in_account() is not None and must_change():
        login = f'{PREFIX}/#account'          # choose a new password first
    if request.method == 'GET' and 'text/html' in request.headers.get('Accept', ''):
        response = redirect(login)
    else:
        response = make_response(jsonify({'error': 'Sign in first', 'login_url': login}), 401)
    response.headers['Cache-Control'] = 'no-store'
    return response


# ---------------------------------------------------------------------------
# Signing in and out
# ---------------------------------------------------------------------------

@app.route('/api/session')
def session_status():
    account = signed_in_account()
    user = None
    if account is not None:
        mine = labs.labs_of(account['username'])
        user = {'username': account['username'], 'is_admin': account['is_admin'],
                'role': role_of(account), 'lab': mine[0]['lab'] if mine else None,
                'labs': [{'lab': m['lab'], 'role': m['role']} for m in mine], 'must_change': must_change()}
    return jsonify({'authenticated': account is not None, 'user': user,
                    'registration_open': labs.registration_open(), 'version': APP_VERSION})


@app.route('/login', methods=['GET'])
def login_page():
    if signed_in_account() is not None:
        return redirect(safe_next(request.args.get('next', '')))
    return send_file(PAGES / 'login.html', max_age=0)


@app.route('/login', methods=['POST'])
@app.route('/api/login', methods=['POST'])
def login():
    data = json_body()
    if data is None:
        return jsonify({'error': 'Send the username and password as JSON'}), 400
    password = str(data.get('password') or '')
    account = directory.find(str(data.get('username') or ''))
    if account is None or not directory.check_password(account, password):
        time.sleep(1)       # blunt the obvious guessing attack
        return jsonify({'error': 'Wrong username or password'}), 401
    start_session(account)
    if password == MOCLO_DEFAULT_PASSWORD:
        # The published default: let them in only to choose a new password.
        session['must_change'] = True
        return jsonify({'authenticated': True, 'username': account['username'], 'must_change': True,
                        'next': f'{PREFIX}/#account'})
    return jsonify({'authenticated': True, 'username': account['username'],
                    'next': safe_next(str(data.get('next') or ''))})


@app.route('/logout', methods=['GET', 'POST'])
@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    if request.method == 'GET':
        return redirect(f'{PREFIX}/login')
    return jsonify({'ok': True})


# ---------------------------------------------------------------------------
# Registering
# ---------------------------------------------------------------------------

@app.route('/register', methods=['GET'])
def register_page():
    if signed_in_account() is not None:
        return redirect(safe_next(request.args.get('next', '')))
    return send_file(PAGES / 'register.html', max_age=0)


@app.route('/api/labs')
def lab_choices():
    """The labs someone can join, for the registration form; never their codes."""
    first = not directory.anyone()
    return jsonify({
        'labs': [{'id': lab['id'], 'name': lab['name'], 'open': bool(lab['registration_code'])}
                 for lab in labs.all_labs()],
        'registration_open': labs.registration_open(),
        # The first account of an empty installation names its own lab.
        'code_required': labs.code_required() and not first,
        'default_lab': labs.default_lab_name(),
    })


@app.route('/api/register', methods=['POST'])
def register():
    if not labs.registration_open():
        return jsonify({'error': 'Registration is closed on this server'}), 403
    data = json_body()
    if data is None:
        return jsonify({'error': 'Send the form as JSON'}), 400
    username = str(data.get('username') or '').strip()
    try:
        lab = labs.check(str(data.get('lab') or ''), str(data.get('code') or ''),
                         directory.anyone())
        account = directory.create(username, str(data.get('password') or ''))
    except PermissionError as exc:
        time.sleep(1)       # blunt guessing of codes
        return jsonify({'error': str(exc)}), 403
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    labs.set_lab(account['username'], lab['id'])
    start_session(account)
    return jsonify({'authenticated': True, 'username': account['username'], 'lab': lab['name'],
                    'next': safe_next(str(data.get('next') or ''))}), 201


# ---------------------------------------------------------------------------
# Labs, codes and roles
# ---------------------------------------------------------------------------
#
# Administrators manage everything. Lab leads see their own lab, its members
# and its code (to hand out). Lab admins can also add people to their own lab
# (a new account, or one in no lab yet) and take people out of it. Only an
# administrator can create labs, generate or close codes, delete accounts, or
# change anyone's role.

def require_lab_admin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        account = signed_in_account()
        if account is None:
            return jsonify({'error': 'Sign in first'}), 401
        if must_change():
            return jsonify({'error': 'Choose a new password first, under My account'}), 403
        role = role_of(account)
        if role not in ('admin', 'lab_admin', 'lab_lead'):
            return jsonify({'error': 'Only administrators and lab leads can manage labs'}), 403
        return fn(account, role, *args, **kwargs)
    return wrapper


def require_admin(fn):
    @wraps(fn)
    @require_lab_admin
    def wrapper(account, role, *args, **kwargs):
        if role != 'admin':
            return jsonify({'error': 'Only an administrator can do that'}), 403
        return fn(account, *args, **kwargs)
    return wrapper


@app.route('/')
def dashboard_page():
    if signed_in_account() is None:
        return redirect(f'{PREFIX}/login?next={PREFIX}/')
    return send_file(PAGES / 'dashboard.html', max_age=0)


@app.route('/admin')
def admin_page():
    """The Labs page that came before the dashboard: now one of its tabs."""
    return redirect(f'{PREFIX}/#labs')


@app.route('/api/account/password', methods=['POST'])
def change_password():
    """Your own password. You stay signed in; every other session ends."""
    account = signed_in_account()
    if account is None:
        return jsonify({'error': 'Sign in first'}), 401
    data = json_body() or {}
    if not directory.check_password(account, str(data.get('current') or '')):
        time.sleep(1)
        return jsonify({'error': 'Your current password is not right'}), 403
    new = str(data.get('new') or '')
    if new == MOCLO_DEFAULT_PASSWORD:
        return jsonify({'error': 'That is the published default password; choose one of your own'}), 400
    try:
        start_session(directory.set_password(account['username'], new))
    except (ValueError, LookupError) as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'ok': True})


def _lab_row(lab: dict) -> dict:
    return {'id': lab['id'], 'name': lab['name'], 'members': lab['members'],
            'code': lab['registration_code'], 'code_updated_by': lab['code_updated_by'],
            'code_updated_at': lab['code_updated_at'],
            'chair_group_id': lab.get('chair_group_id'), 'chair_group': lab.get('chair_group')}


@app.route('/api/admin/overview')
@require_lab_admin
def overview(account, role):
    """
    What this person may see: everything for an admin; for a lab lead or lab
    admin, the labs they lead, their members, and each member's role there.
    """
    led = managed_labs(account, role)
    run = managed_labs(account, role, 'lab_admin')
    everyone = labs.all_lab_members()
    people = []
    for person in directory.all_accounts():
        theirs = everyone.get(person['username'], [])
        shown = theirs if role == 'admin' else [m for m in theirs if m['lab_id'] in led]
        if role != 'admin' and not shown:
            continue
        first = theirs[0] if theirs else {}
        people.append({'username': person['username'], 'created_at': person.get('created_at'),
                       'is_admin': bool(person['is_admin']),
                       'role': 'admin' if person['is_admin'] else
                       max((m['role'] for m in theirs), key=labs.RANK.get, default='member'),
                       # Their first lab, as one-lab views show it.
                       'lab_id': first.get('lab_id'), 'lab': first.get('lab'),
                       'labs': [{'lab_id': m['lab_id'], 'lab': m['lab'], 'role': m['role']} for m in shown]})
    return jsonify({
        'me': {'username': account['username'], 'role': role},
        'can_manage': role == 'admin',
        # Adds people to these labs and takes them out (administrators: any lab).
        'can_manage_members': bool(run),
        'manages': sorted(run),
        'codes_required': labs.code_required(),
        'labs': [_lab_row(lab) for lab in labs.all_labs() if role == 'admin' or lab['id'] in led],
        # Chair groups, chosen by administrators: all of them for an administrator, else those of their labs.
        'chair_groups': [g for g in labs.chair_groups() if role == 'admin' or any(
            lab['chair_group_id'] == g['id'] for lab in labs.all_labs() if lab['id'] in led)],
        'users': people,
        # Accounts a lab admin may add to their labs: anyone but administrators.
        'addable': sorted(p['username'] for p in directory.all_accounts() if not p['is_admin']) if run else [],
        'roles': list(labs.ROLES),
        'lab_roles': ['member', 'lab_lead', 'lab_admin'],
    })


@app.route('/api/admin/labs', methods=['POST'])
@require_admin
def create_lab(account):
    data = json_body() or {}
    try:
        lab = labs.create(str(data.get('name') or ''), account['username'])
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'lab': _lab_row(lab)}), 201


def _lab_or_404(lab_id):
    lab = labs.get(lab_id)
    return lab, (None if lab else (jsonify({'error': 'No such lab'}), 404))


@app.route('/api/admin/labs/<lab_id>', methods=['PATCH'])
@require_admin
def rename_lab(account, lab_id):
    lab, missing = _lab_or_404(lab_id)
    if missing:
        return missing
    try:
        labs.rename(lab_id, str((json_body() or {}).get('name') or ''))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'lab': _lab_row(labs.get(lab_id))})


@app.route('/api/admin/labs/<lab_id>', methods=['DELETE'])
@require_admin
def delete_lab(account, lab_id):
    lab, missing = _lab_or_404(lab_id)
    if missing:
        return missing
    try:
        labs.delete(lab_id)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'ok': True})


@app.route('/api/admin/labs/<lab_id>/chair-group', methods=['PUT'])
@require_admin
def set_lab_chair_group(account, lab_id):
    """Puts a lab in a chair group, or in none (chair_group_id empty)."""
    lab, missing = _lab_or_404(lab_id)
    if missing:
        return missing
    try:
        labs.set_chair_group(lab_id, str((json_body() or {}).get('chair_group_id') or '') or None)
    except LookupError as exc:
        return jsonify({'error': str(exc)}), 404
    return jsonify({'lab': _lab_row(labs.get(lab_id))})


@app.route('/api/admin/chair-groups', methods=['POST'])
@require_admin
def create_chair_group(account):
    try:
        group = labs.create_chair_group(str((json_body() or {}).get('name') or ''), account['username'])
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'chair_group': group}), 201


@app.route('/api/admin/chair-groups/<group_id>', methods=['PATCH'])
@require_admin
def rename_chair_group(account, group_id):
    try:
        labs.rename_chair_group(group_id, str((json_body() or {}).get('name') or ''))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except LookupError as exc:
        return jsonify({'error': str(exc)}), 404
    return jsonify({'ok': True})


@app.route('/api/admin/chair-groups/<group_id>', methods=['DELETE'])
@require_admin
def delete_chair_group(account, group_id):
    try:
        labs.delete_chair_group(group_id)
    except LookupError as exc:
        return jsonify({'error': str(exc)}), 404
    return jsonify({'ok': True})


@app.route('/api/admin/labs/<lab_id>/code', methods=['POST'])
@require_admin
def new_lab_code(account, lab_id):
    """A freshly generated code; the old one stops working at once."""
    lab, missing = _lab_or_404(lab_id)
    if missing:
        return missing
    labs.new_code(lab_id, account['username'])
    return jsonify({'lab': _lab_row(labs.get(lab_id))})


@app.route('/api/admin/labs/<lab_id>/code', methods=['DELETE'])
@require_admin
def close_lab(account, lab_id):
    """No code: the lab takes nobody new until it is given one again."""
    lab, missing = _lab_or_404(lab_id)
    if missing:
        return missing
    labs.close(lab_id, account['username'])
    return jsonify({'lab': _lab_row(labs.get(lab_id))})


def _target_or_404(username):
    target = directory.find(username)
    return target, (None if target else (jsonify({'error': 'No such account'}), 404))


@app.route('/api/admin/users', methods=['POST'])
@require_admin
def create_user(account):
    """An account made by an administrator: no registration code needed."""
    data = json_body() or {}
    role = data.get('role') or 'member'
    if role not in labs.ROLES:
        return jsonify({'error': 'Choose administrator, lab admin, lab lead or member'}), 400
    lab_id = str(data.get('lab_id') or '')
    if lab_id and labs.get(lab_id) is None:
        return jsonify({'error': 'Choose one of the labs'}), 400
    if role in ('lab_admin', 'lab_lead') and not lab_id:
        return jsonify({'error': 'A lab lead or lab admin needs a lab'}), 400
    try:
        created = directory.create(str(data.get('username') or ''), str(data.get('password') or ''),
                                   is_admin=role == 'admin')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    if lab_id:
        labs.set_lab(created['username'], lab_id)
    if role in ('lab_admin', 'lab_lead'):
        labs.set_role(created['username'], role, lab_id)
    return jsonify({'ok': True, 'username': created['username']}), 201


@app.route('/api/admin/users/<username>', methods=['DELETE'])
@require_admin
def delete_user(account, username):
    target, missing = _target_or_404(username)
    if missing:
        return missing
    if target['username'] == account['username']:
        return jsonify({'error': 'You cannot remove your own account'}), 400
    try:
        directory.delete(target['username'])
    except LookupError as exc:
        return jsonify({'error': str(exc)}), 404
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    labs.forget(target['username'])
    return jsonify({'ok': True})


@app.route('/api/admin/users/<username>/password', methods=['PUT'])
@require_admin
def set_user_password(account, username):
    """Set someone's password, when they have forgotten theirs. Their sessions end."""
    target, missing = _target_or_404(username)
    if missing:
        return missing
    if target['username'] == account['username']:
        return jsonify({'error': 'Change your own password under My account'}), 400
    password = str((json_body() or {}).get('password') or '')
    if password == MOCLO_DEFAULT_PASSWORD:
        return jsonify({'error': 'Choose another password'}), 400
    try:
        directory.set_password(target['username'], password)
    except (ValueError, LookupError) as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'ok': True})


@app.route('/api/admin/users/<username>/lab', methods=['PUT'])
@require_admin
def set_user_lab(account, username):
    target, missing = _target_or_404(username)
    if missing:
        return missing
    try:
        labs.set_lab(target['username'], str((json_body() or {}).get('lab_id') or ''))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'ok': True})


@app.route('/api/admin/users/<username>/role', methods=['PUT'])
@require_admin
def set_user_role(account, username):
    target, missing = _target_or_404(username)
    if missing:
        return missing
    role = (json_body() or {}).get('role')
    if role not in labs.ROLES:
        return jsonify({'error': 'Choose administrator, lab admin, lab lead or member'}), 400
    if target['username'] == account['username']:
        return jsonify({'error': 'You cannot change your own role'}), 400
    try:
        if role in ('lab_admin', 'lab_lead'):
            labs.set_role(target['username'], role)
        directory.set_admin(target['username'], role == 'admin')
        if role not in ('lab_admin', 'lab_lead') and labs.labs_of(target['username']):
            labs.set_role(target['username'], 'member')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'ok': True})


@app.route('/api/admin/users/<username>/admin', methods=['PUT'])
@require_admin
def set_user_admin(account, username):
    """Make someone an administrator, or not; their labs and roles in them stay."""
    target, missing = _target_or_404(username)
    if missing:
        return missing
    if target['username'] == account['username']:
        return jsonify({'error': 'You cannot change your own role'}), 400
    try:
        directory.set_admin(target['username'], bool((json_body() or {}).get('admin')))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'ok': True})


# ---------------------------------------------------------------------------
# A lab's members, for its lab admin (and administrators)
# ---------------------------------------------------------------------------

def _may_manage_members(account, role, lab_id):
    """An administrator, any lab; a lab admin, their own lab only."""
    if labs.get(lab_id) is None:
        return jsonify({'error': 'No such lab'}), 404
    if role == 'admin' or labs.role_in(account['username'], lab_id) == 'lab_admin':
        return None
    return jsonify({'error': 'Only an administrator, or the lab\'s own lab admin, can change who is in it'}), 403


@app.route('/api/lab/<lab_id>/members', methods=['POST'])
@require_lab_admin
def add_member(account, role, lab_id):
    """
    Add someone to a lab: a new account (username and password), or an
    existing one (username alone), which keeps its other labs. With 'role',
    an administrator also says their role there; a lab admin adds members.
    """
    refused = _may_manage_members(account, role, lab_id)
    if refused:
        return refused
    data = json_body() or {}
    username = str(data.get('username') or '').strip()
    password = str(data.get('password') or '')
    lab_role = str(data.get('role') or 'member') if role == 'admin' else 'member'
    if lab_role not in labs.RANK:
        return jsonify({'error': 'Choose lab admin, lab lead or member'}), 400
    if password:
        if password == MOCLO_DEFAULT_PASSWORD:
            return jsonify({'error': 'Choose another password'}), 400
        try:
            created = directory.create(username, password, is_admin=False)
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
        labs.add(created['username'], lab_id, lab_role)
        return jsonify({'ok': True, 'username': created['username'], 'created': True}), 201
    target = directory.find(username)
    if target is None:
        return jsonify({'error': 'No such account: give a password as well to make a new one'}), 404
    if target['is_admin'] and role != 'admin':
        return jsonify({'error': 'Only an administrator adds an administrator to a lab'}), 400
    if labs.role_in(target['username'], lab_id) is not None:
        return jsonify({'error': f"{target['username']} is in this lab already"}), 400
    labs.add(target['username'], lab_id, lab_role)
    return jsonify({'ok': True, 'username': target['username'], 'created': False}), 201


@app.route('/api/lab/<lab_id>/members/<username>', methods=['PUT'])
@require_admin
def set_member_role(account, lab_id, username):
    """An administrator sets someone's role in one of their labs."""
    target, missing = _target_or_404(username)
    if missing:
        return missing
    try:
        labs.set_role(target['username'], str((json_body() or {}).get('role') or ''), lab_id)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'ok': True})


@app.route('/api/lab/<lab_id>/members/<username>', methods=['DELETE'])
@require_lab_admin
def remove_member(account, role, lab_id, username):
    """
    Take someone out of a lab. Their account, their own work and their other
    labs stay; they no longer see this lab's records. A lab admin takes out
    members and lab leads, not administrators, other lab admins, or themselves.
    """
    refused = _may_manage_members(account, role, lab_id)
    if refused:
        return refused
    target, missing = _target_or_404(username)
    if missing:
        return missing
    there = labs.role_in(target['username'], lab_id)
    if there is None:
        return jsonify({'error': f"{target['username']} is not in this lab"}), 400
    if target['username'] == account['username'] and role != 'admin':
        return jsonify({'error': 'You cannot take yourself out of the lab'}), 400
    if role != 'admin' and (target['is_admin'] or there == 'lab_admin'):
        return jsonify({'error': 'Only an administrator can take an administrator or a lab admin out of a lab'}), 403
    labs.remove(target['username'], lab_id)
    return jsonify({'ok': True})


# ---------------------------------------------------------------------------
# The rest
# ---------------------------------------------------------------------------

@app.route('/style.css')
def stylesheet():
    return send_file(PAGES / 'style.css', max_age=0)


@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'version': APP_VERSION,
                    'directory': directory.moclo_db().exists() or directory.editor_db().exists()})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003)
