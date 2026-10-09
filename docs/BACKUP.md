# Backups

The stack backs itself up to a network drive every night. This document covers
setting that up, checking it is working, and restoring.

The short version:

```bash
make backup-init     # once, with the network drive mounted
make backup-check    # is it working?
make restore         # put the latest backup back
```

## What is backed up

| Item | How |
| --- | --- |
| `moclo.db` — MoClo plasmids, cassettes, backbones, users | SQLite online backup |
| `parts.db` — the shared MoClo parts library | SQLite online backup |
| `plasmid_editor.db` — sequences, sequencing reads, verifications | SQLite online backup |
| Anything else in either volume | tar |
| The stack's configuration (compose, nginx, landing page) | tar, **secrets excluded** |

Databases are copied with SQLite's **online backup**, so the applications keep
running and the copy is never caught mid-write. Copying a live `.db` file with
`cp` cannot promise that; this does.

**`.env` is deliberately not backed up.** It holds `SECRET_KEY` and
`MOCLO_SECRET_KEY`, and a backup drive is usually more widely readable than the
server. Losing those keys costs everyone a fresh login, nothing more — keep
them in your password manager. To include it anyway, drop the `--exclude='.env'`
from `backup/backup.sh`.

## Setting up the network drive

Mount the share on the **host** first, so it survives reboots. For a Windows or
NAS share over SMB, in `/etc/fstab`:

```
//nas.example.org/labbackup  /mnt/labbackup  cifs  credentials=/root/.smbcreds,uid=0,gid=0,_netdev,nofail  0  0
```

For NFS:

```
nas.example.org:/export/labbackup  /mnt/labbackup  nfs  _netdev,nofail  0  0
```

`_netdev` and `nofail` matter: they stop the server hanging at boot when the
NAS is unreachable.

Then point the stack at it and mark it, once:

```bash
echo 'BACKUP_DEST=/mnt/labbackup/lab-suite' >> .env
mkdir -p /mnt/labbackup/lab-suite
docker compose up -d
make backup-init
make backup            # prove it works now, rather than finding out at 02:30
```

### Why the marker file

`make backup-init` writes a `.backup-target` file into the destination, and the
backup **refuses to run without it**.

This guards against the most common silent failure: the network drive fails to
mount, so `/mnt/labbackup` is just an empty directory on the local disk. Without
the marker, backups would quietly write there, fill the server's disk, and look
perfectly healthy until the day you needed them.

## Checking it is working

```bash
make backup-check     # destination, free space, last run
make backup-list      # archives held, newest first
make backup-logs      # follow the container
```

The backup container also reports its own health, so a broken backup shows up in
`docker ps` as `unhealthy` rather than being discovered when it is needed. It
turns unhealthy if the last run failed, or if no backup has succeeded in 36
hours.

For a push notification on failure, set a webhook URL (Slack, Teams, ntfy,
anything that accepts a JSON POST):

```bash
NOTIFY_URL=https://hooks.example.org/...     # in .env
NOTIFY_ON_SUCCESS=1                          # optional, also tell me when it works
```

## Schedule and retention

Defaults, all settable in `.env`:

| Variable | Default | Meaning |
| --- | --- | --- |
| `BACKUP_HOUR` / `BACKUP_MINUTE` | `2` / `30` | Daily run time |
| `TZ` | `Europe/Amsterdam` | Timezone for that time |
| `KEEP_DAILY` | `14` | Keep every backup for this many runs |
| `KEEP_WEEKLY` | `8` | Then one per week |
| `KEEP_MONTHLY` | `12` | Then one per month |

With the defaults you can go back a fortnight day by day, two months week by
week, and a year month by month — roughly 34 archives. These are small: a lab
with a few hundred plasmids produces archives of a few hundred kB.

## Restoring

**Look before you leap.** Inspect an archive without changing anything:

```bash
make backup-list
make restore-check ARCHIVE=lab-suite-2026-10-09_023000.tar.gz
```

That verifies the checksum, unpacks it, and runs an integrity check on every
database inside.

To restore:

```bash
make restore                                              # the latest archive
make restore ARCHIVE=lab-suite-2026-10-02_023000.tar.gz   # a specific one
```

This stops the two applications, replaces the databases, and starts them again.
Nothing is overwritten blindly:

- the archive's checksum is verified first, and a mismatched archive is refused;
- every database is integrity-checked *before* anything live is touched;
- the databases being replaced are kept beside the new ones as
  `*.db.before-restore`.

Once you are satisfied, remove the `.before-restore` copies to reclaim the
space:

```bash
docker compose exec editor sh -c 'rm -f /data/*.before-restore /moclo/*.before-restore'
```

### Restoring onto a new server

1. Install Docker, clone this repository, create `.env` with fresh
   `SECRET_KEY` and `MOCLO_SECRET_KEY` values.
2. Mount the backup drive and copy an archive to it, or set `BACKUP_DEST` to it.
3. `docker compose up -d` to create the volumes, then `make restore`.

The configuration inside the archive is not restored automatically — the
repository is the source of truth for that. It is included so a rebuild needs no
guesswork about how the stack was wired.

## Testing a restore

A backup nobody has restored is a guess. Twice a year, something like:

```bash
make backup                 # fresh archive
make restore-check          # verify it unpacks and passes integrity checks
```

and, when you can take a few minutes of downtime, a real `make restore`
followed by opening both tools to confirm the data is there. This has been
exercised end to end: a sequence added after a backup was correctly gone after
restoring it, with the rest of the library intact.

## How it is put together

```
backup/
  Dockerfile      alpine + sqlite3 + busybox cron, no Docker socket needed
  entrypoint.sh   schedule | now | check | init | healthcheck | restore
  backup.sh       the nightly job
  restore.sh      --list, --inspect, --dry-run, restore
```

The backup service mounts both data volumes **read-only** — it can never damage
live data. Restoring needs write access, so it runs as a separate `restore`
service behind a compose profile, which never starts with the stack.

Each run writes to a `.part` file, verifies the archive can be read back in
full, renames it into place, writes a `.sha256` beside it, and verifies that
too. A transfer cut short by the network therefore cannot leave something that
looks like a usable backup.
