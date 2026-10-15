# Gardiner Lab Tools

One Docker stack that runs the lab's software behind a single port, with a
landing page that lists the tools:

| Path | Tool | Repository |
| --- | --- | --- |
| `/` | Landing page | this repository |
| `/account/` | Sign-in, registration and labs for every tool | this repository |
| `/` (everything else) | [MoClo Library Tool](https://github.com/Gardiner-Lab/moclo-library-tool) | its own |
| `/editor/` | [Plasmid Editor](https://github.com/Gardiner-Lab/plasmid-editor) | its own |
| `/notebook/` | [Lab Notebook](https://github.com/Gardiner-Lab/lab-notebook) | its own |

Each tool keeps its own published image and updates independently — nothing is
copied into this repository. The two share a data volume so a plasmid edited in
the Plasmid Editor is updated in the MoClo tool as well.

## Installing

You need Docker with the compose plugin. On the server:

```bash
git clone https://github.com/Gardiner-Lab/gardiner-lab-suite.git
cd gardiner-lab-suite
./install.sh
```

No git? Download `gardiner-lab-suite-<version>.tar.gz` from the
[latest release](https://github.com/Gardiner-Lab/gardiner-lab-suite/releases/latest),
unpack it, and run `./install.sh` inside.

It shows what it is about to do, asks once, and finishes with the address to
open and, on a new installation, an administrator password. Running it again
later updates the suite in place. On Windows, run it from Git Bash or WSL.

### Already running the MoClo Library Tool?

Run the same `./install.sh` on the machine where MoClo runs. It finds the
MoClo container and moves its users and data into the suite:

1. It saves a snapshot of MoClo's data in `pre-install-backup/`.
2. It stops the MoClo container and renames it `moclo-library-tool-retired-…`.
   It is **not deleted**, and its data is only ever read.
3. It copies the accounts, plasmids, parts and MoClo's own backups into the
   suite, then checks every table: integrity, and the same number of rows as
   before.
4. It starts the suite on **the port MoClo used**, so bookmarks keep working,
   and with MoClo's secret key, so nobody is even signed out. Everyone signs in
   to both tools with their usual username and password.

If any step fails, the old MoClo is started again exactly as it was. Once the
suite is running, `./install.sh --rollback` still goes back to the old MoClo
(anything done in the suite since is not carried back). When you are happy,
remove the old container with the `docker rm` command the installer prints.

A new installation starts with the administrator `admin` / `admin123`, as
MoClo does. Because that password is published and one sign-in opens every
tool (the backup console included), signing in with it opens only *My account*,
to choose a new password; nothing else opens until that is done. The same goes
for a MoClo taken over whose `admin` still has it. Set `ADMIN_PASSWORD` in
`.env` before installing to start with your own password instead.

| Option | Use |
| --- | --- |
| `--from-moclo NAME` | Which MoClo to take over, if there are several: a container, a Docker volume, or a folder holding `moclo.db` (for MoClo run without Docker) |
| `--port N` | Serve the suite on another port |
| `--fresh` | Ignore any existing MoClo and start empty |
| `--yes` | Do not ask |
| `--rollback` | Go back to the MoClo that was taken over |

If an image a release needs has not been published (only while developing),
the installer builds it from source, the editor from a checkout at
`../plasmid-editor`, and says so.

### By hand

`install.sh` only automates this. Without it:

```bash
cp .env.example .env      # fill in SECRET_KEY, MOCLO_SECRET_KEY, ADMIN_PASSWORD
docker compose up -d
```

Then open `http://your-server:8080`. Change the port with `SUITE_PORT`.

### Building from source

To run the editor and the backup service from source rather than their
published images, for testing a change:

```bash
SECRET_KEY=dev MOCLO_SECRET_KEY=dev \
  docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build
```

`EDITOR_SRC` points at the checkout (default `../plasmid-editor`).

### Updating

```bash
git pull
./install.sh
```

Each release of this repository pins versions of MoClo, the Plasmid Editor and
the backup service that were tested together (see `CHANGELOG.md`), so an update
always moves to a known-good combination; nothing changes until you update.
Data lives in the `moclo-data` and `editor-data` volumes and survives updates.

To try a newer release of one tool before the suite catches up, set
`MOCLO_VERSION` or `EDITOR_VERSION` in `.env` and run `./install.sh` again.

## Releasing

Three repositories, under the Gardiner-Lab organisation on GitHub:

| Repository | Publishes |
| --- | --- |
| [moclo-library-tool](https://github.com/Gardiner-Lab/moclo-library-tool) | `ghcr.io/gardiner-lab/moclo-library-tool` |
| [plasmid-editor](https://github.com/Gardiner-Lab/plasmid-editor) | `ghcr.io/gardiner-lab/plasmid-editor` |
| gardiner-lab-suite (this one) | `ghcr.io/gardiner-lab/lab-suite-backup`, and the release people install |

Each tool releases on its own: pushing a `vX.Y.Z` tag in its repository tests it
and publishes its image. People get it through a suite release:

1. Update the pinned version in `docker-compose.yml` (`MOCLO_VERSION`,
   `EDITOR_VERSION`), and `SUITE_VERSION` to the new suite version.
2. Test the combination (`./install.sh` on a test machine), add a section to
   `CHANGELOG.md`, commit.
3. `git tag v1.0.1 && git push origin main v1.0.1`. The release workflow checks
   the versions, publishes the backup image, and creates the GitHub release.

## How the routing works

The MoClo Library Tool writes absolute links (`href="/parts"`,
`fetch('/api/backbones')`). Serving it under a sub-path such as `/moclo/` would
break those links unless the proxy rewrote its HTML and JavaScript, which is
fragile and would need rechecking after every MoClo release.

So MoClo keeps the whole root namespace and is left completely untouched. Every
other tool is carved out under its own prefix and is told what that prefix is,
so it generates its own links correctly:

```nginx
location = /        -> landing page (static)
location /account/  -> sign-in, registration and labs
location /editor/   -> Plasmid Editor   (URL_PREFIX=/editor)
location /notebook/ -> Lab Notebook     (URL_PREFIX=/notebook)
location /          -> MoClo            (catch-all)
```

The landing page is served as static files by the proxy that is routing anyway,
rather than by a web framework. A fourth Python process to serve one HTML page
would cost about 40 MiB for nothing.

Measured idle memory for the stack is roughly **166 MiB**: MoClo 58,
Plasmid Editor 61, sign-in service 30, nginx 17.

### One sign-in

People sign in once, at `/account/login`, and are signed in to every tool. The
sign-in service (`portal/`) owns the only session. Before every request to a
tool, nginx asks it who is signed in (`auth_request`) and passes the answer on
as an `X-Suite-User` header; the header is always set by the proxy, so a
browser cannot supply its own. Each tool runs with `SUITE_AUTH=proxy` and takes
that header as the person's identity instead of signing anyone in itself, so
signing out at `/account/logout` signs out of everything.

**Nothing is visible before signing in.** The landing page and every tool,
including any added later, are behind the sign-in: someone not signed in who
opens any of them is sent to the sign-in page (with a link to register) and
returns to that page afterwards, and a script calling a tool's API gets a 401.
Only the sign-in and registration pages and the tools' `/health` checks are
open, the last for monitoring. The sign-in service keeps that list
(`PUBLIC_PATHS` in `portal/portal.py`). If the sign-in service is down,
everything behind it answers 500 rather than let anyone in.

Accounts still live in MoClo's `users` table, the suite's directory. The
service adds accounts to it at registration and changes who is an
administrator, and nothing else. A deleted account, or a changed password, ends
that person's sessions at their next request (changing your own password signs
you out too: sign in again with the new one).

### Registration and labs

New members register at `/account/register`: they choose their lab, give that
lab's registration code, and are signed in to every tool. Every lab has its own
code, generated by the suite: the first lab (`DEFAULT_LAB_SOURCE`) gets one on
installation, and every lab added later gets one at once. The installer prints
the first.

On the dashboard's **Labs** tab, administrators add, rename and remove labs,
give a lab a new code (the old one stops working at once) or close it to new
members. Lab leads see their own lab, its code to hand out, and its members.

All of this is kept in `suite.db` (the `suite-data` volume), which the tools
read: the Plasmid Editor takes each person's lab and lab-lead role from it.
Administrator status stays in the account directory, where MoClo reads it too.

### The dashboard

Every control for every tool is on one dashboard, at `/account/` (linked from
the landing page and from each tool's navigation). Each tool's own Dashboard
and Admin pages, and the backup console, send people there.

| Tab | Who sees it | From |
| --- | --- | --- |
| My account: lab, role, change password | everyone | the suite |
| My parts, Saved constructs | everyone | MoClo |
| Labs: codes, and a lead's own members | administrators, lab leads | the suite |
| Accounts: add, remove, set a password, lab and role | administrators | the suite |
| MoClo library: parts, cassettes, backbones, plasmids | administrators | MoClo |
| Backups | administrators | the backup console |

The suite's own tabs are built in. A tool adds tabs by listing them in a
`suite-manifest.json`, named by its entry in `landing/tools.json` (`"manifest"`):

```json
{ "tabs": [ { "id": "moclo-library", "title": "MoClo library", "icon": "🧬",
              "section": "admin", "roles": ["admin"],
              "src": "/admin?embed=1&tab=parts" } ] }
```

`section` is `me` or `admin`; `roles` (admin, lab_lead, member) limits who sees
the tab, and absent means everyone. The tab shows the tool's page at `src`
inside the dashboard, so `?embed=1` should leave out the tool's own navigation.
Hiding a tab is for tidiness: each tool still checks who may do what.

Accounts are managed only here. Inside the suite, MoClo's own user management
and account settings are switched off, so an account cannot be renamed in one
tool and lost in the others.

### Session cookies

The sign-in service's cookie is `lab_suite_session`. Besides it, both tools are
Flask applications on one hostname, so they would otherwise both
set a cookie named `session` at path `/` and overwrite each other's login. The
editor uses its own cookie name, scoped to its prefix, so the two logins
coexist. Any further Flask tool added here must do the same.

## Adding a tool

Three steps, no rebuild of the landing page:

1. **A service** in `docker-compose.yml` — do not publish a host port, just
   `expose` it, so the proxy is the only way in.
2. **A location block** in `nginx/default.conf`, copied from the `/editor/` one,
   placed *above* the catch-all. Give the tool its prefix through its own
   configuration so it writes correct links. Every request through it already
   carries the signed-in user in `X-Suite-User` (empty when nobody is); the tool
   should take that as its identity, and send people to `/account/login?next=…`
   to sign in, rather than keep a sign-in of its own.
3. **An entry** in `landing/tools.json`, with `"manifest"` if it adds tabs to
   the dashboard (see "The dashboard" above):

```json
{
  "id": "primers",
  "name": "Primer database",
  "icon": "🧪",
  "colour": "#a855f7",
  "href": "/primers/",
  "summary": "What it is for, in a sentence.",
  "points": ["A highlight", "Another"],
  "health": "/primers/health",
  "manifest": "/primers/suite-manifest.json"
}
```

`tools.json` is read by the browser at load time, so `docker compose restart proxy`
is enough to pick up a change — and the `health` endpoint drives the live
running/unavailable dot on each card.

Anything listed under `planned` is shown as a greyed-out card, which is a
convenient way to signal what is coming.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `SECRET_KEY` | — | **Required.** Signs Plasmid Editor sessions. |
| `MOCLO_SECRET_KEY` | — | **Required.** Signs MoClo sessions. Use a different value. |
| `SUITE_SECRET_KEY` | `SECRET_KEY` | Signs the suite's sign-in, which every tool trusts. |
| `SUITE_PORT` | `8080` | Host port for the whole suite. |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | `admin` / — | The first administrator's password. Empty: `admin123`, which must be changed at the first sign-in. |
| `ALLOW_REGISTRATION` | `true` | Set `false` to close registration. |
| `REQUIRE_REGISTRATION_CODE` | `true` | Set `false` to let anyone register without a lab's code. |
| `DEFAULT_LAB_SOURCE` | — | The first lab, created with its own code on a new installation. |
| `SESSION_COOKIE_SECURE` | `false` | Set `true` once TLS terminates in front of this stack. |

## HTTPS

This stack serves plain HTTP on one port, which is appropriate behind an
existing institutional proxy or on a trusted network. To terminate TLS here
instead, put Caddy or nginx with certificates in front of `SUITE_PORT`, and set
`SESSION_COOKIE_SECURE=true`.

## Backups

The stack backs itself up to a network drive every night: all three databases
via SQLite's online backup, plus the stack's configuration, verified and
checksummed, with daily/weekly/monthly retention.

Most of it is done from the **backup console**, reachable from the landing page
or at `/backup/`: choose where backups go, run one now, download or upload an
archive, and restore. Only administrators get in.

To back up to a Windows file server or NAS, choose **Network drive** there and
give the share's path, a username and a password. The share is reached directly
over SMB, so nothing needs mounting on the server and nothing is kept inside
Docker.

Moving to a new machine is download-then-upload: take a backup, download the
archive, install the stack elsewhere, upload it in that console and restore.

```bash
make backup-init     # once, for a drive mounted on the server (not needed for a network drive set in the console)
make backup-check    # is it working?
make restore         # put the latest backup back
```

Full setup, monitoring and restore instructions are in
[docs/BACKUP.md](docs/BACKUP.md). The backup container reports itself
`unhealthy` in `docker ps` if a run fails or none has succeeded in 36 hours, and
can POST to a webhook on failure.
