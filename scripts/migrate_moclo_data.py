"""
Copy an existing MoClo Library Tool's data into the suite, and prove it arrived.

Run by install.sh inside a throwaway container, with the old data mounted
read-only at SOURCE and the suite's empty data volume at TARGET:

    python migrate_moclo_data.py SOURCE TARGET [SNAPSHOT.tar.gz]

The source is never written to. The old MoClo is stopped before this runs, and
its files are first copied raw to a scratch folder (with any -wal journal), so
that SQLite can bring the copy up to date there rather than touching the
original. Each database is then written to TARGET with SQLite's backup API and
checked: integrity, and the row count of every table against the source.

Everything else in SOURCE (MoClo's own backups, uploads) is copied as is. The
result is owned by uid 1000, the user both applications run as. A tar.gz of the
copied data is written to SNAPSHOT if given, as a safety copy outside Docker.

Prints a readable summary, then ADMINS=, USERS= and NAMES= lines for the
installer; exits non-zero with an ERROR: line on any mismatch, leaving TARGET
for the caller to discard.
"""

import os
import shutil
import sqlite3
import sys
import tarfile
import tempfile
from pathlib import Path

APP_UID = APP_GID = 1000
JOURNALS = ('-wal', '-shm', '-journal')


def fail(message: str) -> None:
    print(f'ERROR: {message}')
    sys.exit(1)


def table_counts(conn: sqlite3.Connection) -> dict:
    names = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    return {n: conn.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0] for n in names}


def accounts(conn: sqlite3.Connection) -> dict:
    """How many accounts, and how many administrators, the MoClo database holds."""
    try:
        columns = {r[1] for r in conn.execute('PRAGMA table_info(users)')}
    except sqlite3.Error:
        return {'users': 0, 'admins': 0, 'admin_names': [], 'usernames': []}
    if not columns:
        return {'users': 0, 'admins': 0, 'admin_names': [], 'usernames': []}
    names = [r[0] for r in conn.execute('SELECT username FROM users ORDER BY username')]
    admins = []
    if 'is_admin' in columns:
        admins = [r[0] for r in conn.execute(
            'SELECT username FROM users WHERE is_admin ORDER BY username')]
    return {'users': len(names), 'admins': len(admins), 'admin_names': admins,
            'usernames': names}


def main(argv) -> None:
    if len(argv) < 2:
        fail(__doc__.strip().splitlines()[0])
    source, target = Path(argv[0]), Path(argv[1])
    snapshot = Path(argv[2]) if len(argv) > 2 else None

    if not source.is_dir():
        fail(f'{source} is not a folder')
    databases = sorted(p for p in source.iterdir() if p.is_file() and p.suffix == '.db')
    if not any(p.name == 'moclo.db' for p in databases):
        fail(f'no moclo.db in {source}: this does not look like MoClo data')
    if (target / 'moclo.db').exists():
        fail(f'{target} already holds a moclo.db; refusing to overwrite it')
    target.mkdir(parents=True, exist_ok=True)

    report = {'ok': True, 'databases': {}, 'files': 0}
    with tempfile.TemporaryDirectory() as scratch:
        scratch = Path(scratch)
        for db in databases:
            # A raw copy, journal included, so the original is only ever read.
            for suffix in ('',) + JOURNALS:
                part = Path(str(db) + suffix)
                if part.exists():
                    shutil.copy2(part, scratch / part.name)
            src = sqlite3.connect(scratch / db.name)
            before = table_counts(src)
            out = sqlite3.connect(target / db.name)
            src.backup(out)
            out.close()

            check = sqlite3.connect(target / db.name)
            integrity = check.execute('PRAGMA integrity_check').fetchone()[0]
            after = table_counts(check)
            entry = {'tables': len(after), 'rows': sum(after.values()), 'integrity': integrity}
            if db.name == 'moclo.db':
                report['accounts'] = accounts(check)
            check.close()
            src.close()
            if integrity != 'ok':
                fail(f'{db.name} failed its integrity check after copying: {integrity}')
            if before != after:
                differ = sorted(t for t in set(before) | set(after) if before.get(t) != after.get(t))
                fail(f'{db.name}: row counts differ after copying in {", ".join(differ)}')
            report['databases'][db.name] = entry

    # Everything else: MoClo's own backups, uploads and the like.
    for item in source.rglob('*'):
        rel = item.relative_to(source)
        if item.is_dir():
            (target / rel).mkdir(parents=True, exist_ok=True)
            continue
        if len(rel.parts) == 1 and (item.suffix == '.db' or item.name.endswith(JOURNALS)):
            continue
        (target / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target / rel)
        report['files'] += 1

    for root, dirs, files in os.walk(target):
        for name in dirs + files:
            os.chown(os.path.join(root, name), APP_UID, APP_GID)
    os.chown(target, APP_UID, APP_GID)

    if snapshot is not None:
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(snapshot, 'w:gz') as tar:
            tar.add(target, arcname='moclo-data')
        report['snapshot'] = snapshot.name

    for name, entry in report['databases'].items():
        print(f"{name}: {entry['tables']} tables, {entry['rows']} rows, integrity {entry['integrity']}")
    found = report.get('accounts', {})
    print(f"accounts: {found.get('users', 0)}, administrators: {found.get('admins', 0)}")
    print(f"other files: {report['files']}")
    print('ADMINS=' + ','.join(found.get('admin_names', [])))
    print('USERS=' + str(found.get('users', 0)))
    print('NAMES=' + ','.join(found.get('usernames', [])))


if __name__ == '__main__':
    main(sys.argv[1:])
