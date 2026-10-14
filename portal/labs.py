"""
The labs that use the suite, their registration codes, and who is in which.

Kept here, in the sign-in service's own database (suite.db), so that one
registration page and one set of codes serve every tool. Each tool reads who
is in which lab from here; none keeps a copy of its own.

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

ROLES = ('admin', 'lab_lead', 'member')
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
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


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
            'SELECT labs.*, (SELECT COUNT(*) FROM members WHERE lab_id = labs.id) AS members '
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

def memberships() -> Dict[str, dict]:
    """username -> {'lab_id', 'lab', 'role'} for everyone in a lab or leading one."""
    with connect() as conn:
        return {r['username']: dict(r) for r in conn.execute(
            'SELECT members.username, members.lab_id, members.role, labs.name AS lab '
            'FROM members LEFT JOIN labs ON labs.id = members.lab_id')}


def membership(username: str) -> dict:
    return memberships().get(username) or {'lab_id': None, 'lab': None, 'role': 'member'}


def set_lab(username: str, lab_id: str) -> None:
    if get(lab_id) is None:
        raise ValueError('Choose one of the labs')
    with connect() as conn:
        conn.execute('INSERT INTO members (username, lab_id) VALUES (?, ?) '
                     'ON CONFLICT(username) DO UPDATE SET lab_id = excluded.lab_id',
                     (username, lab_id))


def set_lab_lead(username: str, lead: bool) -> None:
    if lead and not membership(username)['lab_id']:
        raise ValueError(f'{username} has no lab yet; give them one first')
    with connect() as conn:
        conn.execute('INSERT INTO members (username, role) VALUES (?, ?) '
                     'ON CONFLICT(username) DO UPDATE SET role = excluded.role',
                     (username, 'lab_lead' if lead else 'member'))


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
    return len(labs)


def prepare(editor_db: Path) -> None:
    """
    At start-up: the schema; and the first time, the editor's labs and a lab
    for DEFAULT_LAB_SOURCE with a generated code, if there is none of that name.
    """
    db_path().parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA)
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
    """A removed account leaves its lab."""
    with connect() as conn:
        conn.execute('DELETE FROM members WHERE username = ?', (username,))
