"""
backup.sh, run for real against a stand-in suite folder: the configuration
archive holds what is needed to rebuild the stack, and no secrets.

It needs sh, sqlite3, tar and jq, as the backup container has; elsewhere it is
skipped.

    python -m pytest backup/test_backup_script.py
"""

import io
import os
import shutil
import sqlite3
import subprocess
import tarfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent / 'backup.sh'
NEEDED = ('sh', 'sqlite3', 'tar', 'jq')

pytestmark = pytest.mark.skipif(any(shutil.which(t) is None for t in NEEDED) or os.name == 'nt',
                                reason=f'needs {", ".join(NEEDED)} (as in the backup container)')


def _write(path: Path, text: str = 'x') -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_the_configuration_archive_carries_no_secrets(tmp_path):
    suite = tmp_path / 'suite'
    # What a rebuild needs.
    for name in ('docker-compose.yml', '.env.example', 'Makefile', 'install.sh', 'README.md',
                 'nginx/default.conf', 'landing/index.html', 'landing/tools.json', 'scripts/check.sh', 'docs/BACKUP.md'):
        _write(suite / name)
    # What must never leave the folder.
    secrets = {
        '.env': 'SECRET_KEY=s3cret',
        '.env.bak': 'SECRET_KEY=s3cret',
        '.env.local': 'SECRET_KEY=s3cret',
        'production.env': 'SECRET_KEY=s3cret',
        'nginx/server.key': 'PRIVATE KEY',
        'nginx/server.pem': 'PRIVATE KEY',
        'pre-install-backup/moclo-data-20261015.tar.gz': 'password hashes',
        'backups/lab-suite-2026-10-14_020000.tar.gz': 'an older archive',
        'portal/test_portal.py': 'code, not configuration',
        '.pytest_cache/v/cache/nodeids': '[]',
        'notes/admin-password.txt': 'admin123',
    }
    for name, text in secrets.items():
        _write(suite / name, text)

    dest, staging, store = tmp_path / 'dest', tmp_path / 'staging', tmp_path / 'store'
    dest.mkdir()
    store.mkdir()
    (dest / '.backup-target').write_text('')
    db = tmp_path / 'moclo.db'
    sqlite3.connect(db).execute('CREATE TABLE t (x)').connection.commit()
    env = {**os.environ, 'BACKUP_DEST': str(dest), 'BACKUP_STAGING': str(staging), 'CONFIG_STORE': str(store),
           'CONFIG_DIR': str(suite), 'MOCLO_DB': str(db), 'PARTS_DB': str(tmp_path / 'none1.db'),
           'EDITOR_DB': str(tmp_path / 'none2.db'), 'SUITE_DB': str(tmp_path / 'none3.db'),
           'NOTEBOOK_DB': str(tmp_path / 'none4.db'), 'SEEDS_DB': str(tmp_path / 'none5.db'),
           'MOCLO_DIR': str(tmp_path / 'nodir1'), 'EDITOR_DIR': str(tmp_path / 'nodir2'), 'NOTIFY_URL': ''}
    run = subprocess.run(['sh', str(SCRIPT)], env=env, capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stdout + run.stderr

    [archive] = list(dest.glob('lab-suite-*.tar.gz'))
    with tarfile.open(archive) as outer:
        inner = next(m for m in outer.getmembers() if m.name.endswith('files/config.tar.gz'))
        with tarfile.open(fileobj=io.BytesIO(outer.extractfile(inner).read())) as config:
            names = {m.name.removeprefix('./') for m in config.getmembers() if m.isfile()}
            contents = b''.join(config.extractfile(m).read() for m in config.getmembers() if m.isfile())
    assert {'docker-compose.yml', '.env.example', 'nginx/default.conf', 'landing/tools.json',
            'scripts/check.sh', 'docs/BACKUP.md', 'install.sh'} <= names
    for secret in secrets:
        assert secret not in names, f'{secret} was copied to the backup drive'
    assert b's3cret' not in contents and b'PRIVATE KEY' not in contents and b'admin123' not in contents
