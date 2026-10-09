# Gardiner Lab Tools

One Docker stack that runs the lab's software behind a single port, with a
landing page that lists the tools:

| Path | Tool | Repository |
| --- | --- | --- |
| `/` | Landing page | this repository |
| `/` (everything else) | [MoClo Library Tool](https://github.com/Gardiner-Lab/moclo-library-tool) | its own |
| `/editor/` | [Plasmid Editor](https://github.com/Gardiner-Lab/plasmid-editor) | its own |

Each tool keeps its own published image and updates independently — nothing is
copied into this repository. The two share a data volume so a plasmid edited in
the Plasmid Editor is updated in the MoClo tool as well.

## Running it

```bash
SECRET_KEY=$(openssl rand -hex 32) \
MOCLO_SECRET_KEY=$(openssl rand -hex 32) \
  docker compose up -d
```

Then open `http://your-server:8080`. Change the port with `SUITE_PORT`.

Put the settings in a `.env` file next to `docker-compose.yml` instead of the
command line if you prefer; see `.env.example`.

### Before images are published

To run the editor from a working copy rather than its published image:

```bash
SECRET_KEY=dev MOCLO_SECRET_KEY=dev \
  docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build
```

`EDITOR_SRC` points at the checkout (default `../plasmid-editor`).

### Updating

```bash
docker compose pull && docker compose up -d
```

Each image moves independently, so updating one tool does not touch the other.
Data lives in the `moclo-data` and `editor-data` volumes and survives updates.

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
location /editor/   -> Plasmid Editor   (URL_PREFIX=/editor)
location /          -> MoClo            (catch-all)
```

The landing page is served as static files by the proxy that is routing anyway,
rather than by a web framework. A fourth Python process to serve one HTML page
would cost about 40 MiB for nothing.

Measured idle memory for the whole stack is roughly **127 MiB**: MoClo 52,
Plasmid Editor 57, nginx 18.

### Session cookies

Both tools are Flask applications on one hostname, so they would otherwise both
set a cookie named `session` at path `/` and overwrite each other's login. The
editor uses its own cookie name, scoped to its prefix, so the two logins
coexist. Any further Flask tool added here must do the same.

## Adding a tool

Three steps, no rebuild of the landing page:

1. **A service** in `docker-compose.yml` — do not publish a host port, just
   `expose` it, so the proxy is the only way in.
2. **A location block** in `nginx/default.conf`, copied from the `/editor/` one,
   placed *above* the catch-all. Give the tool its prefix through its own
   configuration so it writes correct links.
3. **An entry** in `landing/tools.json`:

```json
{
  "id": "primers",
  "name": "Primer database",
  "icon": "🧪",
  "colour": "#a855f7",
  "href": "/primers/",
  "summary": "What it is for, in a sentence.",
  "points": ["A highlight", "Another"],
  "health": "/primers/health"
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
| `SUITE_PORT` | `8080` | Host port for the whole suite. |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | `admin` / — | Creates the editor's first admin. |
| `ALLOW_REGISTRATION` | `true` | Set `false` to close editor self-registration. |
| `DEFAULT_LAB_SOURCE` | — | Pre-filled lab name on contributed parts. |
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

```bash
make backup-init     # once, with the network drive mounted
make backup-check    # is it working?
make restore         # put the latest backup back
```

Full setup, monitoring and restore instructions are in
[docs/BACKUP.md](docs/BACKUP.md). The backup container reports itself
`unhealthy` in `docker ps` if a run fails or none has succeeded in 36 hours, and
can POST to a webhook on failure.
