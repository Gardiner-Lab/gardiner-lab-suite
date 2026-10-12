# Changelog

Releases of the Gardiner Lab tool suite. Each one pins versions of the tools
that were tested together; see `docker-compose.yml`.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project uses [semantic versioning](https://semver.org/).

## [Unreleased]

## [1.0.0] - 2026-10-12

First release.

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.12.0 |
| Plasmid Editor | 0.2.1 |
| Backup service | 1.0.0 |

### Added
- One stack behind one port: a landing page, the MoClo Library Tool at `/`, the
  Plasmid Editor at `/editor/`, and a backup console at `/backup/`, with a
  "Lab tools" link back to the landing page in each tool.
- `install.sh`: one command to install or update. It takes over an existing MoClo
  Library Tool with its users and data (snapshot first, every table checked,
  automatic rollback on failure, `--rollback` afterwards), and replaces MoClo's
  published default admin password.
- One account for every tool, and one registration page for the suite: people
  choose their lab and give that lab's registration code. Labs, codes and the lab
  lead role are managed on the Plasmid Editor's Admin page.
- Nightly verified backups with daily, weekly and monthly retention, to a folder
  or straight to a network drive (SMB), with a console to run, download, upload,
  verify and restore them.

### Fixed
- Redirects from the proxy kept port 80 instead of the suite's port.
- Every backup archive contained all earlier ones, by way of the suite's own
  `backups/` folder in the configuration snapshot.
