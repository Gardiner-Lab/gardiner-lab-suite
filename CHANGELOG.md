# Changelog

Releases of the Gardiner Lab tool suite. Each one pins versions of the tools
that were tested together; see `docker-compose.yml`.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project uses [semantic versioning](https://semver.org/).

## [Unreleased]

## [2.6.1] - 2026-10-16

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.13.1 |
| Plasmid Editor | 0.4.2 |
| Lab Notebook | 0.9.0 |
| Seed Bank | 0.2.0 |
| Lab Stocks | 0.1.1 |
| Sign-in service | 2.6.1 |
| Backup service | 2.6.1 |

### Fixed
- Copy buttons work over plain http as well as https, in every tool: the Plasmid Editor 0.4.2
  (sequences, selections, cloning products, lab codes), the MoClo Library Tool 1.13.1 (the admin
  page and the guide designer) and Lab Stocks 0.1.1 (primers), as on the dashboard in 2.6.0.

## [2.6.0] - 2026-10-16

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.13.0 |
| Plasmid Editor | 0.4.1 |
| Lab Notebook | 0.9.0 |
| Seed Bank | 0.2.0 |
| Lab Stocks | 0.1.0 |
| Sign-in service | 2.6.0 |
| Backup service | 2.6.0 |

### Added
- **HTTPS.** The suite is served over https on its port, and plain http to it is sent on to https,
  so bookmarks keep working.
  - `install.sh` makes a certificate authority of the lab's own and a certificate for the machine
    (`scripts/make-certs.sh`, `make certs`), and renews the machine's when its names change or it
    nears its end.
  - Each computer trusts the authority once, without administrator rights, from
    `/lab-suite-ca.crt` (no sign-in needed); see docs/HTTPS.md. A university certificate can be
    used instead.
  - Sign-in cookies are secure by default (`SESSION_COOKIE_SECURE=true`).
  - Copy buttons work: browsers allow copying only on secure pages.
- **Lab Stocks** at `/stocks/`, a new tool in the suite: glycerol stocks (`GL-G-0042`) and primers
  (`GL-O-0007`), numbered per lab.
  - Each glycerol stock is linked to its plasmid in the Plasmid Editor.
  - Primers record their sequence, with length, GC and Tm worked out, and can be searched by any
    piece of it.
  - Storage, labels with QR codes, photos and files, and links from the notebook.
  - A lab's stocks are shared within the lab and hidden from other labs.
  - It has its own volume, `stocks-data`. Backups, the backup console and restores include it.

### Changed
- Plasmid Editor 0.4.1: confirming a plasmid by sequencing can make its glycerol stock in Lab
  Stocks, with the lab's next number; a plasmid's stocks show beside its tags; designed primers are
  saved to the lab's primers with one click, and **Lab primers** finds the lab's primers that bind
  a sequence.
- Lab Notebook 0.9.0 (from 0.4.1; see its changelog):
  - links to Lab Stocks with `@`;
  - export to PDF and Word from any level of the tree, with photos, attached PDFs' pages and files;
  - lab leads share notebooks with labs or people, and protocols are their lab's, shared with other
    labs by their authors (existing protocols become their author's lab's);
  - gel photos with numbered wells, numbered photos of plants, and a markup editor for photos.

### Fixed
- The Copy button for a lab's registration code on the dashboard copies over plain http too.

## [2.5.0] - 2026-10-15

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.13.0 |
| Plasmid Editor | 0.3.5 |
| Lab Notebook | 0.4.1 |
| Seed Bank | 0.2.0 |
| Sign-in service | 2.5.0 |
| Backup service | 2.5.0 |

### Changed
- Seed Bank 0.2.0: every code starts with its lab's own code (GL-S-0042), so no two labs' codes are
  ever the same.
  - Each lab numbers from 1.
  - The lab lead or an admin can choose the lab code before the lab's first record.
- Lab Notebook 0.4.1: seed links read the new codes.

## [2.4.1] - 2026-10-15

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.13.0 |
| Plasmid Editor | 0.3.5 |
| Lab Notebook | 0.4.0 |
| Seed Bank | 0.1.0 |
| Sign-in service | 2.4.1 |
| Backup service | 2.4.1 |

### Fixed
- **Backups could copy secrets to the backup drive.** The configuration archive took the whole suite
  folder minus a few names (`.env`, `*.key`, `*.pem`). Anything else went along to the backup drive
  in every nightly archive:
  - a copy of `.env` (`.env.bak`, a renamed env file);
  - the `pre-install-backup/` snapshots, with every account's password hash and the labs'
    registration codes;
  - caches.

  It now takes a list of named files: the compose files, `nginx/`, `landing/`, `scripts/`, `docs/`,
  `.env.example`, `Makefile`, `install.sh`. Secret-looking files are left out even inside those
  folders. A test runs the real script against a folder full of such files.
- **`make check` tested the wrong thing.**
  - Signed out, every tool page is answered by the proxy's sign-in redirect, so the checks of
    `/login`, `/parts` and `/editor/login` passed even with MoClo or the editor down.
  - It also ignored `SUITE_PORT` in `.env`, so a suite on another port was never the one checked.

  It now reads the port from `.env` (as text, never running it), checks the sign-in gate for
  what it is, and checks each tool behind the proxy at its health route. It also compares each
  tool's running version with the version this release pins.

## [2.4.0] - 2026-10-15

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.13.0 |
| Plasmid Editor | 0.3.5 |
| Lab Notebook | 0.4.0 |
| Seed Bank | 0.1.0 |
| Sign-in service | 2.4.0 |
| Backup service | 2.4.0 |

### Added
- **Seed Bank** at `/seeds/`, a new tool in the suite: plant lines, seed lots and plants, with
  lineage traced plant by plant.
  - Each line records the plasmids it carries, from the Plasmid Editor.
  - Segregation tests, storage locations, phenotypes with photos and 3D scans.
  - Labels with QR codes, and links from the notebook.
  - A lab's stocks are shared within the lab and hidden from other labs.
  - It has its own volume, `seeds-data`. Backups, the backup console and restores include it.
  - `SUITE_PUBLIC_URL` (e.g. `http://UU115629:8080`) sets where label QR codes point, so phones
    can reach them.

### Changed
- Lab Notebook 0.4.0: link seed lots, plants and lines from the Seed Bank with `@`.

## [2.3.0] - 2026-10-15

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.13.0 |
| Plasmid Editor | 0.3.5 |
| Lab Notebook | 0.3.0 |
| Sign-in service | 2.3.0 |
| Backup service | 2.3.0 |

### Changed
- Lab Notebook 0.3.0: photos and attachments on pages and protocols.
  - Any kind of file can be attached: Word, PowerPoint, Excel, PDF and more.
  - Photos show in the page, PDFs open in the browser, and Office files open in their programs.
  - The files are kept in the notebook's database, so backups include them. The database, and so
    each backup, grows with the photos attached.

## [2.2.0] - 2026-10-15

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.13.0 |
| Plasmid Editor | 0.3.5 |
| Lab Notebook | 0.2.0 |
| Sign-in service | 2.2.0 |
| Backup service | 2.2.0 |

### Changed
- Lab Notebook 0.2.0: a 🗑 Deleted view to bring deleted pages and protocols back. Owners restore
  their own, protocol editors their protocols, and administrators anything.

## [2.1.1] - 2026-10-15

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.13.0 |
| Plasmid Editor | 0.3.5 |
| Lab Notebook | 0.1.1 |
| Sign-in service | 2.1.1 |
| Backup service | 2.1.1 |

### Fixed
- **Backups failed after installing 2.1.0.** The backup could not read the Lab Notebook's
  database from its read-only mount, because the notebook kept it in SQLite's WAL mode. A failure
  to copy any one database stops the backup, so nothing was backed up. Lab Notebook 0.1.1 uses the
  ordinary journal, as the other tools do, and converts its database when it starts.

## [2.1.0] - 2026-10-15

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.13.0 |
| Plasmid Editor | 0.3.5 |
| Lab Notebook | 0.1.0 |
| Sign-in service | 2.1.0 |
| Backup service | 2.1.0 |

### Added
- **Lab Notebook** at `/notebook/`, a new tool in the suite: everyone's notebook of days and pages,
  a shared protocol library with active tables, MoClo reactions and plasmid links that open in the
  Plasmid Editor. Its design follows Trilium Notes. Lab leads read their lab's notebooks and
  administrators read all of them. It has its own volume, `notebook-data`, and reads the account
  directory, the editor's plasmids and the labs without changing them.
- Backups, the backup console and restores include the notebook's database.
- `/notebook/health` answers without signing in, like the other tools' health checks.

### Changed
- Plasmid Editor 0.3.5: the "✓ Sequenced" and new "Not sequenced" tags open the plasmid on the
  Sequencing page.

## [2.0.4] - 2026-10-15

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.13.0 |
| Plasmid Editor | 0.3.4 |
| Sign-in service | 2.0.4 |
| Backup service | 2.0.4 |

### Changed
- Plasmid Editor 0.3.4: correct a plasmid to its sequencing read, with
  features and translations moving along; every change to a sequence is kept
  in its history with who made it, and any version can be rolled back to; a
  save over a newer version is held back instead of overwriting it.

## [2.0.3] - 2026-10-15

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.13.0 |
| Plasmid Editor | 0.3.3 |
| Sign-in service | 2.0.3 |
| Backup service | 2.0.3 |

### Changed
- Plasmid Editor 0.3.3: the differences in a sequencing alignment can be
  clicked to go to them, with Previous and Next between them; and judging an
  alignment sufficient needs the glycerol stock the clone is kept as.

## [2.0.2] - 2026-10-14

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.13.0 |
| Plasmid Editor | 0.3.2 |
| Sign-in service | 2.0.2 |
| Backup service | 2.0.2 |

### Changed
- Plasmid Editor 0.3.2: select and copy amino acids on a translation, Find's
  selected match is visible, and the Enzymes panel's Choose… button fits.

### Fixed
- The proxy and the sign-in service reported themselves unhealthy in
  `docker ps` although both worked: their health checks asked `localhost`,
  which in Alpine is the IPv6 address first, where neither listens. They ask
  `127.0.0.1` now.

## [2.0.1] - 2026-10-14

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.13.0 |
| Plasmid Editor | 0.3.1 |
| Sign-in service | 2.0.1 |
| Backup service | 2.0.1 |

### Changed
- Plasmid Editor 0.3.1: the sequences open in the editor are kept, as tabs in
  the Open panel, until signing out (unsaved edits included), keyed by the
  suite's id for the sign-in; and the editor's side panels stay in view while
  the sequence scrolls.

## [2.0.0] - 2026-10-14

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.13.0 |
| Plasmid Editor | 0.3.0 |
| Sign-in service | 2.0.0 |
| Backup service | 2.0.0 |

### Added
- **One sign-in for every tool.** Signing in at `/account/login` signs in to
  MoClo, the Plasmid Editor and the backup console at once, and signing out
  signs out of all of them. A new sign-in service (`lab-suite-portal`) owns the
  session; the proxy asks it who is signed in before each request and tells the
  tool. See "One sign-in" in the README.
- **Nothing is visible before signing in or registering**: the landing page
  and every tool send someone who is not signed in to the sign-in page, and
  back afterwards. Only the tools' health checks stay open.
- **One registration page, one set of lab codes, for every tool**, at
  `/account/register`. Every lab's registration code is generated by the suite,
  and a new lab gets one straight away. Who is in which lab and who leads it
  are kept by the suite, and every tool reads them from there.
- **One dashboard for every control**, at `/account/`: your account and
  password, your MoClo parts and saved constructs, and for administrators the
  labs and their codes, every account (add, remove, set a password, lab and
  role), the MoClo library and backups. Tools add their own tabs through a
  `suite-manifest.json`. The landing page shows who is signed in, with a link to
  it.
- `suite.db`, in a new `suite-data` volume, holds the labs and memberships, and
  is in every backup.
- Each sign-in has its own id, passed to the tools as `X-Suite-Session`, for
  what they keep until signing out (the Plasmid Editor's open tabs).

### Changed
- MoClo's, the editor's and the backup console's own sign-in pages, the
  editor's registration page, MoClo's Dashboard and Admin pages, the editor's
  Admin page and the backup console now send people to the suite's sign-in,
  registration and dashboard.
- Accounts are managed only on the dashboard: MoClo's own user management and
  account settings are switched off inside the suite.
- Changing your password no longer signs you out; it signs out your other
  sessions.
- The labs, codes, memberships and lab leads set on the Plasmid Editor's Admin
  page are brought over when the suite first starts, so codes already handed out
  keep working.
- A new installation starts with the administrator `admin` / `admin123` (set
  `ADMIN_PASSWORD` to start with your own). Signing in with `admin123` opens
  only My account, to choose a new password; no tool, page or administration
  opens until it is changed, and it cannot be chosen again.
- The installer no longer makes up a registration code (`REGISTRATION_CODE`);
  it prints the one the suite generated. `REQUIRE_REGISTRATION_CODE=false` lets
  anyone register without one.
- **Everyone is signed out once** when updating to this release, and signs in
  again on the new page with the same username and password.
- The backup console no longer has a sign-in of its own; an administrator who is
  signed in to the suite goes straight in.
- `docker-compose.local.yml` also builds MoClo from a checkout (`MOCLO_SRC`), and
  the installer does so while a pinned MoClo release is not published yet.

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
