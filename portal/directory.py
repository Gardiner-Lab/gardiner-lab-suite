"""
The suite's account directory: who can sign in, and who is an administrator.

It is the MoClo Library Tool's ``users`` table, as it was before the suite had
a sign-in of its own; the Plasmid Editor's table is the fallback, for a stack
without MoClo. This module is the only place the sign-in service touches it.
"""

import os
import re
import sqlite3
import uuid
from pathlib import Path
from typing import List, Optional

import bcrypt

USERNAME_RE = re.compile(r'^[A-Za-z0-9._-]{3,32}$')
MIN_PASSWORD_LENGTH = 8


def moclo_db() -> Path:
    return Path(os.environ.get('MOCLO_DB', '/moclo/moclo.db'))


def editor_db() -> Path:
    return Path(os.environ.get('EDITOR_DB', '/data/plasmid_editor.db'))


def _connect(db: Path, write: bool = False) -> Optional[sqlite3.Connection]:
    if not db.exists():
        return None
    try:
        if write:
            conn = sqlite3.connect(db, timeout=10)
            conn.execute('PRAGMA busy_timeout = 10000')
        else:
            conn = sqlite3.connect(f'file:{db}?mode=ro', uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute('SELECT 1 FROM users LIMIT 1')
        return conn
    except sqlite3.Error:
        return None


def _account(row) -> dict:
    account = dict(row)
    # Older MoClo releases have no is_admin column.
    account['is_admin'] = bool(account.get('is_admin'))
    return account


def _lookup(db: Path, username: str) -> Optional[dict]:
    conn = _connect(db)
    if conn is None:
        return None
    try:
        row = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    return _account(row) if row else None


def find(username: str) -> Optional[dict]:
    """An account by username: the directory first, the editor's own table second."""
    username = (username or '').strip()
    if not username:
        return None
    return _lookup(moclo_db(), username) or _lookup(editor_db(), username)


def all_accounts() -> List[dict]:
    """Everyone who can sign in, from the directory (or the fallback)."""
    for db in (moclo_db(), editor_db()):
        conn = _connect(db)
        if conn is None:
            continue
        try:
            return [_account(r) for r in conn.execute('SELECT * FROM users ORDER BY username')
                    if r['username'] != 'system']
        except sqlite3.Error:
            return []
        finally:
            conn.close()
    return []


def check_password(account: dict, password: str) -> bool:
    try:
        return bcrypt.checkpw((password or '').encode(), account['password_hash'].encode())
    except (ValueError, TypeError, KeyError):
        return False


def anyone() -> bool:
    """Has anyone an account yet? The very first one needs no registration code."""
    return bool(all_accounts())


def create(username: str, password: str, is_admin: bool = False) -> dict:
    """
    Add an account to the directory. The very first account of an empty
    installation becomes an administrator, since nobody else could make one.
    """
    username = (username or '').strip()
    if not USERNAME_RE.match(username):
        raise ValueError('A username is 3 to 32 letters, digits, dots, dashes or underscores')
    _validate_password(password)
    # A name only the editor knows still belongs to someone.
    if find(username) is not None:
        raise ValueError('That username is already taken')
    conn = _connect(moclo_db(), write=True) or _connect(editor_db(), write=True)
    if conn is None:
        raise ValueError('The account directory cannot be reached; try again in a minute')
    try:
        with conn:
            first = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0
            values = {'id': str(uuid.uuid4()), 'username': username,
                      'password_hash': bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
                      'is_admin': 1 if first or is_admin else 0}
            # Only the columns this directory has, so an older MoClo schema works.
            existing = {r['name'] for r in conn.execute('PRAGMA table_info(users)')}
            columns = [c for c in values if c in existing]
            conn.execute(f'INSERT INTO users ({", ".join(columns)}) '
                         f'VALUES ({", ".join("?" for _ in columns)})',
                         [values[c] for c in columns])
    except sqlite3.IntegrityError as exc:
        raise ValueError('That username is already taken') from exc
    except sqlite3.Error as exc:
        raise ValueError('The account directory could not be updated; try again') from exc
    finally:
        conn.close()
    return find(username)


def set_admin(username: str, is_admin: bool) -> None:
    """Administrator status lives in the directory, so every tool sees the change."""
    conn = _connect(moclo_db(), write=True) or _connect(editor_db(), write=True)
    if conn is None:
        raise ValueError('The account directory cannot be reached; try again in a minute')
    try:
        if 'is_admin' not in {r['name'] for r in conn.execute('PRAGMA table_info(users)')}:
            raise ValueError('This MoClo version has no administrators to change')
        with conn:
            if not is_admin:
                admins = conn.execute('SELECT COUNT(*) FROM users WHERE is_admin').fetchone()[0]
                current = conn.execute('SELECT is_admin FROM users WHERE username = ?',
                                       (username,)).fetchone()
                if current and current['is_admin'] and admins <= 1:
                    raise ValueError('This is the only administrator; make someone else one first')
            conn.execute('UPDATE users SET is_admin = ? WHERE username = ?',
                         (1 if is_admin else 0, username))
    except sqlite3.Error as exc:
        raise ValueError('The account directory could not be updated; try again') from exc
    finally:
        conn.close()


def _validate_password(password: str) -> str:
    if len(password or '') < MIN_PASSWORD_LENGTH:
        raise ValueError(f'The password must be at least {MIN_PASSWORD_LENGTH} characters')
    return password


def set_password(username: str, password: str) -> dict:
    """A new password. Every session signed in with the old one ends."""
    _validate_password(password)
    conn = _connect(moclo_db(), write=True) or _connect(editor_db(), write=True)
    if conn is None:
        raise ValueError('The account directory cannot be reached; try again in a minute')
    try:
        with conn:
            done = conn.execute('UPDATE users SET password_hash = ? WHERE username = ?',
                                (bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
                                 username)).rowcount
    except sqlite3.Error as exc:
        raise ValueError('The account directory could not be updated; try again') from exc
    finally:
        conn.close()
    if not done:
        raise LookupError('No such account')
    return find(username)


def delete(username: str) -> None:
    """
    Remove an account from the directory. As in MoClo's own admin page, an
    account that still owns parts or cassettes there cannot be removed.
    """
    conn = _connect(moclo_db(), write=True) or _connect(editor_db(), write=True)
    if conn is None:
        raise ValueError('The account directory cannot be reached; try again in a minute')
    try:
        conn.execute('PRAGMA foreign_keys = ON')
        with conn:
            row = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
            if row is None:
                raise LookupError('No such account')
            if _account(row)['is_admin'] and conn.execute(
                    'SELECT COUNT(*) FROM users WHERE is_admin').fetchone()[0] <= 1:
                raise ValueError('This is the only administrator; make someone else one first')
            conn.execute('DELETE FROM users WHERE username = ?', (username,))
    except sqlite3.IntegrityError as exc:
        raise ValueError(f'{username} still owns records in the MoClo library; '
                         'remove or reassign them first') from exc
    except sqlite3.Error as exc:
        raise ValueError('The account directory could not be updated; try again') from exc
    finally:
        conn.close()
