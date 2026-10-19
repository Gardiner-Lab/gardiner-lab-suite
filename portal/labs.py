"""
The labs that use the suite, their registration codes, and who is in which.

Kept here, in the sign-in service's own database (suite.db), so that one
registration page and one set of codes serve every tool. Each tool reads who
is in which lab from here; none keeps a copy of its own.

Someone may belong to several labs, with a role in each: member, lab lead, or
lab admin (a lab lead who also adds people to the lab and takes them out). They
join their first lab by registering; administrators and the lab's lab admins
add them to more (lab_members). The older members table keeps each person's
first lab and their role there, for tools that read only one.

Every lab has its own registration code, which this service generates: someone
joining picks their lab and gives that lab's code. A lab without a code takes
nobody new. The very first account of an empty installation needs no code,
since there is no administrator yet to hand one out.

Codes are stored readable rather than hashed, because administrators and lab
leads need to see them to hand them out. They are a gate against strangers,
not passwords: everyone who registers still chooses their own.
"""

import hmac
import os
import secrets
import sqlite3
import uuid
from pathlib import Path
from typing import Dict, List, Optional

# A lab admin is a lab lead who also adds people to the lab and takes them out.
# Stored as a lab lead with members.lab_admin set, so every tool, which reads
# only whether someone leads a lab, gives a lab admin all a lab lead has.
ROLES = ('admin', 'lab_admin', 'lab_lead', 'member')
MAX_NAME_LENGTH = 100
# Words that read well aloud, for a code that is easy to pass on.
_WORDS = ('amber', 'basil', 'cedar', 'delta', 'ember', 'fern', 'garnet', 'hazel', 'iris',
          'juniper', 'kelp', 'lotus', 'maple', 'nectar', 'olive', 'petal', 'quartz', 'reed',
          'sage', 'thyme', 'umber', 'violet', 'willow', 'yarrow', 'zinnia', 'clover',
          'birch', 'moss', 'poppy', 'tulip', 'orchid', 'lilac')

SCHEMA = """
CREATE TABLE IF NOT EXISTS labs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    registration_code TEXT,
    code_updated_by TEXT,
    code_updated_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- Who is in which lab, and who leads it. By username, the directory's key.
-- Administrators are the directory's own (MoClo's users.is_admin).
CREATE TABLE IF NOT EXISTS members (
    username TEXT PRIMARY KEY,
    lab_id TEXT REFERENCES labs(id),
    role TEXT NOT NULL DEFAULT 'member',
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- Everyone's labs, with their role in each: 'member' or 'lab_lead', and
-- lab_admin for a lab lead who also adds people to the lab and takes them out.
CREATE TABLE IF NOT EXISTS lab_members (
    username TEXT NOT NULL,
    lab_id TEXT NOT NULL REFERENCES labs(id),
    role TEXT NOT NULL DEFAULT 'member',
    lab_admin INTEGER NOT NULL DEFAULT 0,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (username, lab_id)
);
-- Added columns are put into older databases by prepare() (see _ADDED).
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


# Columns added to members after the first release: (name, declaration).
_ADDED = [
    # A lab lead who may also add people to the lab and take them out of it.
    ('lab_admin', 'INTEGER NOT NULL DEFAULT 0'),
]


def db_path() -> Path:
    return Path(os.environ.get('SUITE_DB', '/suite/suite.db'))


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def _clean(text: str) -> str:
    return ' '.join((text or '').split())


def normalise(code: str) -> str:
    """Codes are read out and typed by hand: case and surrounding space do not count."""
    return _clean(code).lower()


def code_required() -> bool:
    """REQUIRE_REGISTRATION_CODE=false turns codes off entirely."""
    return os.environ.get('REQUIRE_REGISTRATION_CODE', 'true').lower() not in ('0', 'false', 'no')


def registration_open() -> bool:
    return os.environ.get('ALLOW_REGISTRATION', 'true').lower() not in ('0', 'false', 'no')


def default_lab_name() -> str:
    return _clean(os.environ.get('DEFAULT_LAB_SOURCE', ''))


# ---------------------------------------------------------------------------
# Labs
# ---------------------------------------------------------------------------

def all_labs() -> List[dict]:
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            'SELECT labs.*, (SELECT COUNT(*) FROM lab_members WHERE lab_id = labs.id) AS members '
            'FROM labs ORDER BY name COLLATE NOCASE')]


def get(lab_id: str) -> Optional[dict]:
    return next((lab for lab in all_labs() if lab['id'] == lab_id), None)


def by_name(name: str) -> Optional[dict]:
    name = _clean(name).casefold()
    return next((lab for lab in all_labs() if lab['name'].casefold() == name), None)


def generate_code() -> str:
    """Three words and a number, e.g. "maple-orchid-reed-42", unused by any lab."""
    taken = {normalise(lab['registration_code']) for lab in all_labs() if lab['registration_code']}
    while True:
        code = '-'.join([secrets.choice(_WORDS) for _ in range(3)]
                        + [str(secrets.randbelow(90) + 10)])
        if code not in taken:
            return code


def create(name: str, by: str) -> dict:
    """A new lab, with a code of its own so it can take members at once."""
    name = _clean(name)
    if not name:
        raise ValueError('Give the lab a name')
    if len(name) > MAX_NAME_LENGTH:
        raise ValueError(f'A lab name must be at most {MAX_NAME_LENGTH} characters')
    if by_name(name):
        raise ValueError(f'There is already a lab called "{name}"')
    lab_id = str(uuid.uuid4())
    with connect() as conn:
        conn.execute('INSERT INTO labs (id, name) VALUES (?, ?)', (lab_id, name))
    new_code(lab_id, by)
    return get(lab_id)


def ensure(name: str, by: str) -> Optional[dict]:
    """The lab of that name, created if need be; None for an empty name."""
    return by_name(name) or (create(name, by) if _clean(name) else None)


def rename(lab_id: str, name: str) -> None:
    name = _clean(name)
    if not name:
        raise ValueError('Give the lab a name')
    if len(name) > MAX_NAME_LENGTH:
        raise ValueError(f'A lab name must be at most {MAX_NAME_LENGTH} characters')
    other = by_name(name)
    if other and other['id'] != lab_id:
        raise ValueError(f'There is already a lab called "{name}"')
    with connect() as conn:
        conn.execute('UPDATE labs SET name = ? WHERE id = ?', (name, lab_id))


def delete(lab_id: str) -> None:
    """Only a lab nobody belongs to; members are never left without one."""
    lab = get(lab_id)
    if lab is None:
        raise LookupError('No such lab')
    if lab['members']:
        raise ValueError(f'"{lab["name"]}" still has members; move them to another lab first')
    with connect() as conn:
        conn.execute('DELETE FROM labs WHERE id = ?', (lab_id,))


def _set_code(lab_id: str, code: Optional[str], by: str) -> None:
    with connect() as conn:
        conn.execute('UPDATE labs SET registration_code = ?, code_updated_by = ?, '
                     'code_updated_at = CURRENT_TIMESTAMP WHERE id = ?', (code, by, lab_id))


def new_code(lab_id: str, by: str) -> str:
    """A fresh code for this lab. The old one stops working at once."""
    code = generate_code()
    _set_code(lab_id, code, by)
    return code


def close(lab_id: str, by: str) -> None:
    """Remove the lab's code, so nobody new can join it."""
    _set_code(lab_id, None, by)


def check(lab_ref: str, code: str, anyone_registered: bool) -> dict:
    """
    The lab this person may join, or ValueError (unknown or missing lab) or
    PermissionError (closed lab, wrong code) saying why not.
    """
    lab = get(lab_ref) or by_name(lab_ref)
    if not code_required() or not anyone_registered:
        # No codes in use, or the very first account: any lab name will do,
        # and it becomes a lab an administrator can manage.
        if lab is None:
            if not _clean(lab_ref):
                raise ValueError('Choose the lab you work in')
            lab = create(lab_ref, 'registration')
        return lab
    if lab is None:
        raise ValueError('Choose your lab from the list')
    if not lab['registration_code']:
        raise PermissionError(f'{lab["name"]} is not taking new members: it has no registration '
                              'code. Ask an administrator.')
    if not hmac.compare_digest(normalise(code).encode(),
                               normalise(lab['registration_code']).encode()):
        raise PermissionError(f'That is not the registration code for {lab["name"]}. '
                              'Ask your lab lead or an administrator for it.')
    return lab


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------

RANK = {'member': 0, 'lab_lead': 1, 'lab_admin': 2}


def _role(row) -> str:
    return 'lab_admin' if row['role'] == 'lab_lead' and row['lab_admin'] else row['role']


def all_lab_members() -> Dict[str, List[dict]]:
    """username -> their labs, first joined first: [{'lab_id', 'lab', 'role'}]."""
    with connect() as conn:
        rows = conn.execute(
            'SELECT lab_members.username, lab_members.lab_id, lab_members.role, lab_members.lab_admin, '
            'labs.name AS lab FROM lab_members JOIN labs ON labs.id = lab_members.lab_id '
            'ORDER BY lab_members.joined_at, lab_members.rowid').fetchall()
    out: Dict[str, List[dict]] = {}
    for r in rows:
        out.setdefault(r['username'], []).append({'lab_id': r['lab_id'], 'lab': r['lab'], 'role': _role(r)})
    return out


def labs_of(username: str) -> List[dict]:
    return all_lab_members().get(username, [])


def role_in(username: str, lab_id: str) -> Optional[str]:
    """Their role in this lab, or None when they are not in it."""
    return next((m['role'] for m in labs_of(username) if m['lab_id'] == lab_id), None)


def memberships() -> Dict[str, dict]:
    """
    username -> {'username', 'lab_id', 'lab', 'role'}: everyone's first lab and
    their role there, as the members table keeps it for tools reading one lab.
    """
    return {u: {'username': u, **ms[0]} for u, ms in all_lab_members().items()}


def membership(username: str) -> dict:
    return memberships().get(username) or {'lab_id': None, 'lab': None, 'role': 'member'}


def _sync(conn, username: str) -> None:
    """The members table: this person's first lab and their role there, or nothing."""
    first = conn.execute('SELECT * FROM lab_members WHERE username = ? ORDER BY joined_at, rowid LIMIT 1',
                         (username,)).fetchone()
    if first is None:
        conn.execute('DELETE FROM members WHERE username = ?', (username,))
        return
    conn.execute('INSERT INTO members (username, lab_id, role, lab_admin) VALUES (?, ?, ?, ?) '
                 'ON CONFLICT(username) DO UPDATE SET lab_id = excluded.lab_id, role = excluded.role, '
                 'lab_admin = excluded.lab_admin', (username, first['lab_id'], first['role'], first['lab_admin']))


def add(username: str, lab_id: str, role: str = 'member') -> None:
    """Add someone to a lab (another of theirs), with a role there. Already in it: the role changes."""
    if get(lab_id) is None:
        raise ValueError('Choose one of the labs')
    if role not in RANK:
        raise ValueError('Choose lab admin, lab lead or member')
    with connect() as conn:
        conn.execute('INSERT INTO lab_members (username, lab_id, role, lab_admin) VALUES (?, ?, ?, ?) '
                     'ON CONFLICT(username, lab_id) DO UPDATE SET role = excluded.role, lab_admin = excluded.lab_admin',
                     (username, lab_id, 'member' if role == 'member' else 'lab_lead', 1 if role == 'lab_admin' else 0))
        _sync(conn, username)


def remove(username: str, lab_id: str) -> None:
    """Take someone out of one of their labs. Their account, and their other labs, stay."""
    with connect() as conn:
        conn.execute('DELETE FROM lab_members WHERE username = ? AND lab_id = ?', (username, lab_id))
        _sync(conn, username)


def set_lab(username: str, lab_id: str) -> None:
    """Someone's only lab: on registering, or an administrator moving them, out of any others."""
    if get(lab_id) is None:
        raise ValueError('Choose one of the labs')
    with connect() as conn:
        conn.execute('DELETE FROM lab_members WHERE username = ? AND lab_id != ?', (username, lab_id))
        conn.execute('INSERT OR IGNORE INTO lab_members (username, lab_id) VALUES (?, ?)', (username, lab_id))
        _sync(conn, username)


def set_role(username: str, role: str, lab_id: Optional[str] = None) -> None:
    """
    Someone's role in one of their labs ('lab_admin', 'lab_lead' or 'member');
    without lab_id, in every lab they are in (as the one-lab Accounts tab did).
    """
    if role not in RANK:
        raise ValueError('Choose lab admin, lab lead or member')
    labs = [m['lab_id'] for m in labs_of(username)]
    if lab_id is not None and lab_id not in labs:
        raise ValueError(f'{username} is not in that lab')
    if role != 'member' and not labs:
        raise ValueError(f'{username} has no lab yet; give them one first')
    with connect() as conn:
        conn.execute('UPDATE lab_members SET role = ?, lab_admin = ? WHERE username = ?'
                     + (' AND lab_id = ?' if lab_id else ''),
                     ('member' if role == 'member' else 'lab_lead', 1 if role == 'lab_admin' else 0, username,
                      *([lab_id] if lab_id else [])))
        _sync(conn, username)


def set_lab_lead(username: str, lead: bool) -> None:
    set_role(username, 'lab_lead' if lead else 'member')


def leave_lab(username: str, lab_id: Optional[str] = None) -> None:
    """Out of one lab (or, without lab_id, all of them). The account stays."""
    with connect() as conn:
        conn.execute('DELETE FROM lab_members WHERE username = ?' + (' AND lab_id = ?' if lab_id else ''),
                     (username, *([lab_id] if lab_id else [])))
        _sync(conn, username)


# ---------------------------------------------------------------------------
# Start-up
# ---------------------------------------------------------------------------

def _setting(conn, key: str) -> Optional[str]:
    row = conn.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
    return row['value'] if row else None


def _import_from_editor(conn: sqlite3.Connection, editor_db: Path) -> int:
    """
    Labs, codes, memberships and lab leads were the Plasmid Editor's before
    the suite had a registration of its own. Bring them over, once, so nothing
    has to be set up again. Returns how many labs were imported.
    """
    if not editor_db.exists():
        return 0
    try:
        src = sqlite3.connect(f'file:{editor_db}?mode=ro', uri=True, timeout=5)
        src.row_factory = sqlite3.Row
        try:
            tables = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            labs = [dict(r) for r in src.execute('SELECT * FROM labs')] if 'labs' in tables else []
            columns = {r['name'] for r in src.execute('PRAGMA table_info(users)')}
            users = [dict(r) for r in src.execute('SELECT * FROM users')] if 'lab_source' in columns else []
        finally:
            src.close()
    except sqlite3.Error:
        return 0

    for lab in labs:
        conn.execute('INSERT OR IGNORE INTO labs (id, name, registration_code, code_updated_by, '
                     'code_updated_at, created_at) VALUES (?, ?, ?, ?, ?, ?)',
                     (lab['id'], _clean(lab['name']), lab.get('registration_code'),
                      lab.get('code_updated_by'), lab.get('code_updated_at'),
                      lab.get('created_at')))
    ids = {r['name'].casefold(): r['id'] for r in conn.execute('SELECT id, name FROM labs')}
    for user in users:
        lab_id = ids.get(_clean(user.get('lab_source') or '').casefold())
        lead = user.get('role') == 'lab_lead' and lab_id
        if lab_id or lead:
            conn.execute('INSERT OR IGNORE INTO members (username, lab_id, role) VALUES (?, ?, ?)',
                         (user['username'], lab_id, 'lab_lead' if lead else 'member'))
            if lab_id:
                conn.execute('INSERT OR IGNORE INTO lab_members (username, lab_id, role) VALUES (?, ?, ?)',
                             (user['username'], lab_id, 'lab_lead' if lead else 'member'))
    return len(labs)


def prepare(editor_db: Path) -> None:
    """
    At start-up: the schema; and the first time, the editor's labs and a lab
    for DEFAULT_LAB_SOURCE with a generated code, if there is none of that name.
    """
    db_path().parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA)
        columns = {r['name'] for r in conn.execute('PRAGMA table_info(members)')}
        for name, decl in _ADDED:
            if name not in columns:
                conn.execute(f'ALTER TABLE members ADD COLUMN {name} {decl}')
        # Once: everyone's one lab, from before people could be in several, becomes their first.
        if _setting(conn, 'lab_members_from_members') is None:
            conn.execute('INSERT OR IGNORE INTO lab_members (username, lab_id, role, lab_admin, joined_at) '
                         'SELECT username, lab_id, role, lab_admin, joined_at FROM members '
                         'WHERE lab_id IS NOT NULL AND lab_id IN (SELECT id FROM labs)')
            conn.execute("INSERT INTO settings (key, value) VALUES ('lab_members_from_members', '1')")
        if _setting(conn, 'imported_from_editor') is None:
            count = _import_from_editor(conn, editor_db)
            conn.execute("INSERT INTO settings (key, value) VALUES ('imported_from_editor', ?)",
                         (str(count),))
        first_start = _setting(conn, 'default_lab') is None
        if first_start:
            conn.execute("INSERT INTO settings (key, value) VALUES ('default_lab', ?)",
                         (default_lab_name(),))
    # Once only, so a lab an administrator removed does not come back.
    if first_start and default_lab_name() and by_name(default_lab_name()) is None:
        create(default_lab_name(), 'installer')


def forget(username: str) -> None:
    """A removed account leaves its labs."""
    with connect() as conn:
        conn.execute('DELETE FROM lab_members WHERE username = ?', (username,))
        conn.execute('DELETE FROM members WHERE username = ?', (username,))
