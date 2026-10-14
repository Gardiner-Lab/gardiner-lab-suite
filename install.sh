#!/usr/bin/env bash
#
# Install, or update, the Gardiner Lab tool suite.
#
#   ./install.sh                 install, or update an existing installation
#   ./install.sh --port 8080     choose the port (default: the old MoClo's, else 8080)
#   ./install.sh --from-moclo X  take users and data from X: a container, a Docker
#                                volume, or a folder holding moclo.db
#   ./install.sh --fresh         ignore any existing MoClo and start empty
#   ./install.sh --yes           do not ask; accept what was found
#   ./install.sh --rollback      undo an installation that took over a MoClo
#
# Already running the MoClo Library Tool? This finds it and moves its accounts,
# plasmids, parts and backups into the suite. Nothing of the old installation is
# deleted: its container is stopped and renamed, its data is only ever read, and
# a snapshot of that data is saved in ./pre-install-backup first. Every database
# is checked table by table after copying, and if anything fails along the way
# the old MoClo is started again as it was.
#
# Needs Docker with the compose plugin. On Windows, run it from Git Bash or WSL.

set -Eeuo pipefail   # -E: the rollback trap also fires inside functions
cd "$(dirname "$0")"

# Git Bash would otherwise rewrite container paths such as /data into C:/...
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'

PROJECT=gardiner-lab-suite
SUITE_VOLUME="${PROJECT}_moclo-data"
STATE_FILE=.install-state
STAMP="$(date +%Y%m%d-%H%M%S)"

PORT="" FROM="" FRESH=0 YES=0 ROLLBACK=0
while [ $# -gt 0 ]; do
    case "$1" in
        --port)        PORT="${2:?--port needs a number}"; shift 2 ;;
        --from-moclo)  FROM="${2:?--from-moclo needs a container, volume or folder}"; shift 2 ;;
        --fresh)       FRESH=1; shift ;;
        --yes|-y)      YES=1; shift ;;
        --rollback)    ROLLBACK=1; shift ;;
        -h|--help)     sed -n '3,22p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *)             echo "Unknown option: $1 (try --help)" >&2; exit 2 ;;
    esac
done

# --- output ------------------------------------------------------------------
if [ -t 1 ]; then B=$'\033[1m' G=$'\033[32m' Y=$'\033[33m' R=$'\033[31m' N=$'\033[0m'
else B="" G="" Y="" R="" N=""; fi
step() { printf '\n%s==> %s%s\n' "$B" "$*" "$N"; }
info() { printf '    %s\n' "$*"; }
ok()   { printf '    %s✓%s %s\n' "$G" "$N" "$*"; }
warn() { printf '    %s!%s %s\n' "$Y" "$N" "$*"; }
die()  { printf '\n%sError:%s %s\n' "$R" "$N" "$*" >&2; exit 1; }

ask() {   # ask "question" default(y|n) -> 0 for yes
    local answer default="$2"
    if [ "$YES" = 1 ]; then [ "$default" = y ]; return; fi
    if ! [ -r /dev/tty ]; then die "cannot ask \"$1\" without a terminal; rerun with --yes"; fi
    printf '    %s [%s] ' "$1" "$([ "$default" = y ] && echo Y/n || echo y/N)"
    read -r answer < /dev/tty || answer=""
    answer="${answer:-$default}"
    case "$answer" in [Yy]*) return 0 ;; *) return 1 ;; esac
}

random_secret() {
    if command -v openssl >/dev/null 2>&1; then openssl rand -hex 32
    else head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'; fi
}

# A host path as Docker wants it (Windows form under Git Bash).
host_path() {
    if command -v cygpath >/dev/null 2>&1; then cygpath -w "$1"; else (cd "$1" && pwd); fi
}

compose() { docker compose "$@"; }

state() { grep -E "^$1=" "$STATE_FILE" 2>/dev/null | head -1 | cut -d= -f2-; }

force_env() { sed -i.bak "/^$1=/d" .env && rm -f .env.bak; printf '%s=%s\n' "$1" "$2" >> .env; }
drop_env()  { sed -i.bak "/^$1=/d" .env && rm -f .env.bak; }

# Use the published images, which docker-compose.yml pins to versions tested
# together. Any that are not published yet (before a first release) are built
# from source instead, and .env remembers that so every later 'docker compose'
# command does the same; once all are published, that is undone again.
prepare_images() {
    local missing="" image
    drop_env COMPOSE_FILE
    drop_env COMPOSE_PATH_SEPARATOR
    for image in $(docker compose --profile restore config --images 2>/dev/null | sort -u); do
        docker image inspect "$image" >/dev/null 2>&1 && continue
        docker manifest inspect "$image" >/dev/null 2>&1 && continue
        missing="$missing $image"
    done
    if [ -n "$missing" ]; then
        case "$missing" in
            *nginx*) die "could not find$missing; is this server online?" ;;
        esac
        case "$missing" in
            *moclo-library-tool*)
                local moclo_src
                moclo_src="$(grep -E '^MOCLO_SRC=' .env | cut -d= -f2-)"
                moclo_src="${moclo_src:-../moclo-library-tool}"
                [ -f "$moclo_src/Dockerfile" ] || die "the MoClo Library Tool image is not published yet and there is no checkout at $moclo_src to build it from. Clone it there (git clone https://github.com/Gardiner-Lab/moclo-library-tool $moclo_src) and rerun."
                ;;
        esac
        case "$missing" in
            *plasmid-editor*)
                local editor_src
                editor_src="$(grep -E '^EDITOR_SRC=' .env | cut -d= -f2-)"
                editor_src="${editor_src:-../plasmid-editor}"
                [ -f "$editor_src/Dockerfile" ] || die "the Plasmid Editor image is not published yet and there is no checkout at $editor_src to build it from. Clone it there (git clone https://github.com/Gardiner-Lab/plasmid-editor $editor_src) and rerun."
                ;;
        esac
        local sep=":"
        case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) sep=";" ;; esac
        force_env COMPOSE_PATH_SEPARATOR "$sep"
        force_env COMPOSE_FILE "docker-compose.yml${sep}docker-compose.local.yml"
        warn "not published yet, so built here from source:$missing"
    fi
    step "Fetching the programs (this can take a few minutes)"
    compose pull --ignore-pull-failures --quiet 2>/dev/null || true
    compose build --quiet
    ok "ready"
}

# The MoClo image this suite runs, as pinned in docker-compose.yml.
moclo_image() { docker compose config --images 2>/dev/null | grep moclo-library-tool | head -1; }

# --- rollback ----------------------------------------------------------------
restore_old_moclo() {
    local old="$1" original="$2" policy="$3"
    [ -n "$old" ] || return 0
    docker inspect "$old" >/dev/null 2>&1 || { warn "old container $old no longer exists"; return 0; }
    if [ "$old" != "$original" ]; then docker rename "$old" "$original"; fi
    docker update --restart="${policy:-unless-stopped}" "$original" >/dev/null
    docker start "$original" >/dev/null
    ok "the old MoClo ($original) is running again, exactly as before"
}

if [ "$ROLLBACK" = 1 ]; then
    [ -f "$STATE_FILE" ] || die "nothing to roll back: no $STATE_FILE here"
    step "Rolling back to the MoClo Library Tool as it was before the suite"
    warn "Anything changed in the suite since it was installed is not in the old MoClo."
    ask "Stop the suite and start the old MoClo again?" y || exit 1
    compose down
    restore_old_moclo "$(state old_container)" "$(state original_name)" "$(state restart_policy)"
    mv "$STATE_FILE" "$STATE_FILE.rolled-back-$STAMP"
    # Without its .env this folder no longer counts as an installed suite, so
    # running the installer again starts over instead of restarting the suite.
    mv .env ".env.rolled-back-$STAMP"
    info "The suite's data is still in its volumes, should you want it."
    info "To install again from the old MoClo, first remove them (this discards"
    info "anything done in the suite):"
    info "    docker volume rm ${PROJECT}_moclo-data ${PROJECT}_editor-data ${PROJECT}_backup-config"
    exit 0
fi

# --- preflight ---------------------------------------------------------------
step "Checking Docker"
command -v docker >/dev/null 2>&1 || die "Docker is not installed. See https://docs.docker.com/get-docker/"
docker info >/dev/null 2>&1 || die "Docker is installed but not running, or this user may not use it."
docker compose version >/dev/null 2>&1 || die "the Docker compose plugin is missing (docker compose version failed)"
ok "$(docker --version)"

# --- an existing suite: update it ----------------------------------------------
if [ -f .env ] && docker volume inspect "$SUITE_VOLUME" >/dev/null 2>&1; then
    step "The suite is already installed here: updating it"
    info "Data stays in its volumes; only the programs are replaced."
    prepare_images
    compose up -d --remove-orphans
    UPDATED=1
else
    UPDATED=0
fi

if [ "$UPDATED" = 0 ]; then
# --- find an existing MoClo --------------------------------------------------
SRC_KIND="" SRC="" OLD="" OLD_POLICY="" OLD_PORT="" OLD_SECRET=""

describe_container() {
    # The /data mount of a MoClo container (or wherever DATABASE_PATH points).
    local c="$1" dbpath dir mount
    dbpath="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$c" \
              | sed -n 's/^DATABASE_PATH=//p' | head -1)"
    dir="$(dirname "${dbpath:-/data/moclo.db}")"
    mount="$(docker inspect -f "{{range .Mounts}}{{if eq .Destination \"$dir\"}}{{.Type}}|{{.Name}}|{{.Source}}{{end}}{{end}}" "$c")"
    [ -n "$mount" ] || return 1
    case "$mount" in
        volume\|*) SRC_KIND=volume; SRC="$(echo "$mount" | cut -d'|' -f2)" ;;
        bind\|*)   SRC_KIND=bind;   SRC="$(echo "$mount" | cut -d'|' -f3)" ;;
        *)         return 1 ;;
    esac
    OLD="$c"
    OLD_POLICY="$(docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' "$c")"
    OLD_PORT="$(docker inspect -f '{{range $p, $b := .HostConfig.PortBindings}}{{if eq $p "5000/tcp"}}{{(index $b 0).HostPort}}{{end}}{{end}}' "$c")"
    OLD_SECRET="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$c" | sed -n 's/^SECRET_KEY=//p' | head -1)"
}

if [ "$FRESH" = 0 ]; then
    step "Looking for an existing MoClo Library Tool"
    if [ -n "$FROM" ]; then
        if docker inspect --type container "$FROM" >/dev/null 2>&1; then
            describe_container "$FROM" || die "could not find where container $FROM keeps its data"
        elif docker volume inspect "$FROM" >/dev/null 2>&1; then
            SRC_KIND=volume SRC="$FROM"
        elif [ -f "$FROM/moclo.db" ]; then
            SRC_KIND=bind SRC="$(host_path "$FROM")"
        else
            die "$FROM is not a container, a Docker volume, or a folder containing moclo.db"
        fi
    else
        candidates="$(docker ps -a --format '{{.Names}}|{{.Image}}|{{.Label "com.docker.compose.project"}}' \
                      | awk -F'|' -v p="$PROJECT" 'tolower($2) ~ /moclo/ && $3 != p && $1 !~ /-retired-/ {print $1}')"
        count="$(printf '%s' "$candidates" | grep -c . || true)"
        if [ "$count" -gt 1 ]; then
            warn "Found more than one MoClo container:"
            printf '%s\n' "$candidates" | sed 's/^/        /'
            die "choose one with --from-moclo NAME (or --fresh to ignore them)"
        elif [ "$count" = 1 ]; then
            describe_container "$candidates" || die "found MoClo container $candidates but not where it keeps its data; use --from-moclo"
        fi
    fi
    if [ -n "$SRC" ]; then
        ok "found MoClo data: $SRC_KIND $SRC${OLD:+ (container $OLD)}"
    else
        info "none found: this will be a fresh installation"
    fi
fi

# --- settings -----------------------------------------------------------------
[ -n "$PORT" ] || PORT="${OLD_PORT:-8080}"
case "$PORT" in ''|*[!0-9]*) die "--port must be a number" ;; esac

if [ -n "$SRC" ] && docker volume inspect "$SUITE_VOLUME" >/dev/null 2>&1; then
    die "the suite's data volume $SUITE_VOLUME already exists, so MoClo data will not be copied over it. Remove it only if you are sure it holds nothing you need (docker volume rm $SUITE_VOLUME), or run with --fresh."
fi

# The suite's containers have fixed names. Anything else already using one (an
# old MoClo when --fresh was given, say) would make the start fail half-way.
for name in lab-proxy lab-portal moclo-library-tool plasmid-editor lab-backup lab-backup-console; do
    [ "$name" = "$OLD" ] && continue
    owner="$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$name" 2>/dev/null)" || continue
    [ "$owner" = "$PROJECT" ] && continue
    die "a container called $name already exists${owner:+ (from the \"$owner\" project)}. If it is an existing MoClo, run without --fresh to take it over; otherwise stop and rename or remove it first."
done

step "The plan"
info "Install the suite (landing page, MoClo Library Tool, Plasmid Editor, backups)"
info "and serve it at http://$(hostname):$PORT/"
if [ -n "$SRC" ]; then
    info "Take over the existing MoClo:"
    info "  1. save a snapshot of its data in ./pre-install-backup/"
    [ -n "$OLD" ] && info "  2. stop container $OLD and rename it $OLD-retired-$STAMP (not deleted)"
    info "  3. copy its accounts and data into the suite, checking every table"
    info "  4. start the suite; its users sign in with the same usernames and passwords"
    info "If anything goes wrong the old MoClo is started again, untouched."
    info "Afterwards, ./install.sh --rollback goes back to the old MoClo."
fi
ask "Go ahead?" y || { info "Nothing was changed."; exit 1; }

# --- .env ---------------------------------------------------------------------
step "Writing settings to .env"
if [ -f .env ]; then
    cp .env ".env.before-install-$STAMP"
    warn "an existing .env was kept as .env.before-install-$STAMP and is reused"
else
    cp .env.example .env
    CREATED_ENV=1
fi
set_env() {   # set_env KEY VALUE, only where the key is still empty or missing
    local key="$1" value="$2" current
    current="$(grep -E "^$key=" .env | head -1 | cut -d= -f2- || true)"
    [ -n "$current" ] && return 0
    if grep -qE "^$key=" .env; then
        awk -v k="$key" -v v="$value" 'BEGIN{FS=OFS="="} $1==k {print k "=" v; next} {print}' .env > .env.tmp
        mv .env.tmp .env
    else
        printf '%s=%s\n' "$key" "$value" >> .env
    fi
}
set_env SECRET_KEY "$(random_secret)"
# Reusing the old MoClo's key keeps everyone signed in across the move.
set_env MOCLO_SECRET_KEY "${OLD_SECRET:-$(random_secret)}"
force_env SUITE_PORT "$PORT"
# The default backup folder is ./backups next to this file until a network
# drive is chosen in the backup console; see docs/BACKUP.md.
force_env BACKUP_DEST ./backups
mkdir -p backups
chmod 600 .env 2>/dev/null || true
ok "secrets generated; port $PORT"

prepare_images
MOCLO_IMAGE="$(moclo_image)"

# --- take over the old MoClo --------------------------------------------------
undo() {
    printf '\n%sSomething went wrong; putting things back.%s\n' "$R" "$N" >&2
    compose down >/dev/null 2>&1 || true
    if [ "${CREATED_VOLUME:-0}" = 1 ]; then docker volume rm "$SUITE_VOLUME" >/dev/null 2>&1 || true; fi
    restore_old_moclo "${RETIRED:-}" "$OLD" "$OLD_POLICY"
    rm -f "$STATE_FILE"
    if [ "${CREATED_ENV:-0}" = 1 ]; then rm -f .env; fi
}

if [ -n "$SRC" ]; then
    trap undo ERR
    if [ -n "$OLD" ]; then
        step "Stopping the old MoClo (it is kept, not deleted)"
        docker stop "$OLD" >/dev/null
        docker update --restart=no "$OLD" >/dev/null
        RETIRED="$OLD-retired-$STAMP"
        docker rename "$OLD" "$RETIRED"
        {
            echo "old_container=$RETIRED"
            echo "original_name=$OLD"
            echo "restart_policy=$OLD_POLICY"
            echo "installed_at=$STAMP"
        } > "$STATE_FILE"
        ok "stopped and renamed to $RETIRED"
    fi

    step "Copying the MoClo data into the suite"
    docker volume create --label "com.docker.compose.project=$PROJECT" \
        --label com.docker.compose.volume=moclo-data "$SUITE_VOLUME" >/dev/null
    CREATED_VOLUME=1
    mkdir -p pre-install-backup
    # A volume name or a host folder: docker run -v takes either.
    report="$(docker run --rm --user 0 --entrypoint python \
        -v "$SRC:/from:ro" -v "$SUITE_VOLUME:/to" \
        -v "$(host_path scripts):/scripts:ro" -v "$(host_path pre-install-backup):/snapshots" \
        "$MOCLO_IMAGE" /scripts/migrate_moclo_data.py /from /to "/snapshots/moclo-data-$STAMP.tar.gz")" \
        || { echo "$report" >&2; false; }
    summary="$report"
    printf '%s\n' "$summary" | grep -v -E '^(ADMINS|USERS|NAMES)=' | while read -r line; do ok "$line"; done
    MOCLO_ADMINS="$(printf '%s\n' "$summary" | sed -n 's/^ADMINS=//p')"
    MOCLO_USERS="$(printf '%s\n' "$summary" | sed -n 's/^USERS=//p')"
    ok "snapshot saved: pre-install-backup/moclo-data-$STAMP.tar.gz"
fi

# --- an administrator --------------------------------------------------------
# The MoClo tool creates "admin" with a published password whenever no account
# of that name exists. The editor replaces that password with this one as the
# suite starts, so the well-known one never opens the suite. A lab whose admin
# already has its own password keeps it.
set_env ADMIN_USERNAME admin
set_env ADMIN_PASSWORD "$(random_secret | cut -c1-16)"

# --- start ------------------------------------------------------------------
step "Starting the suite"
compose up -d --remove-orphans

fi  # end of fresh installation

step "Waiting for the tools to answer"
PORT="$(grep -E '^SUITE_PORT=' .env | cut -d= -f2-)"; PORT="${PORT:-8080}"
answers() { curl -sf "$1" >/dev/null 2>&1 || wget -qO /dev/null "$1" 2>/dev/null; }
healthy=0
for _ in $(seq 1 60); do
    if answers "http://localhost:$PORT/health" && answers "http://localhost:$PORT/editor/health"; then
        healthy=1; break
    fi
    sleep 2
done
[ "$healthy" = 1 ] || { compose ps; die "the tools did not come up within two minutes; see 'docker compose logs'"; }
ok "MoClo Library Tool and Plasmid Editor are answering"

# Which password the admin account has now: the one in .env, the lab's own,
# or (only if something went wrong) still MoClo's published default.
admin_password="$(grep -E '^ADMIN_PASSWORD=' .env | cut -d= -f2-)"
admin_state="$(docker exec -e PW="$admin_password" plasmid-editor python -c "
import bcrypt, os, sqlite3
row = sqlite3.connect('file:/moclo/moclo.db?mode=ro', uri=True).execute(
    \"SELECT password_hash FROM users WHERE username = 'admin'\").fetchone()
check = lambda pw: bool(pw) and bcrypt.checkpw(pw.encode(), row[0].encode())
print('none' if row is None else 'env' if check(os.environ['PW']) else
      'default' if check('admin123') else 'own')" 2>/dev/null || echo unknown)"
if [ "$admin_state" = default ]; then
    warn "the admin account still has the MoClo tool's published password (admin123)."
    warn "Restart the editor (docker compose restart editor) or change it at once."
fi

if [ "$UPDATED" = 0 ] && [ -n "${SRC:-}" ]; then
    editor_users="$(docker exec plasmid-editor python -c "
import sqlite3; print(sqlite3.connect('/data/plasmid_editor.db').execute('SELECT COUNT(*) FROM users').fetchone()[0])")"
    if [ "$editor_users" -ge "${MOCLO_USERS:-0}" ]; then
        ok "all $MOCLO_USERS MoClo account(s) can sign in to both tools"
    else
        warn "only $editor_users of $MOCLO_USERS MoClo accounts reached the Plasmid Editor; see 'docker compose logs editor'"
    fi
    trap - ERR
fi

step "Done"
info "Open http://$(hostname):$PORT/  (or http://localhost:$PORT/ on this machine)"
if [ "$admin_state" = env ] && [ "$UPDATED" = 0 ]; then
    info ""
    info "${B}Administrator account${N} (it is also in .env):"
    info "    username: admin"
    info "    password: $admin_password"
    info "It works in every tool. Sign in and change it."
fi
if [ -n "${MOCLO_ADMINS:-}" ]; then
    info "Administrators carried over from MoClo: ${MOCLO_ADMINS//,/, }"
fi
if [ "$UPDATED" = 0 ]; then
    # Generated by the suite's sign-in service for the first lab.
    codes="$(docker exec lab-portal python3 -c "
import sqlite3
for name, code in sqlite3.connect('file:/suite/suite.db?mode=ro', uri=True).execute(
        'SELECT name, registration_code FROM labs WHERE registration_code IS NOT NULL ORDER BY name'):
    print(f'{name}: {code}')" 2>/dev/null)"
    info ""
    if [ -n "$codes" ]; then
        info "${B}Registration codes${N} for new members, at http://$(hostname):$PORT/account/register:"
        printf '%s\n' "$codes" | while read -r line; do info "    $line"; done
    fi
    info "Add other labs, each with its own code, choose lab leads and manage"
    info "accounts on the dashboard (/account/)."
fi
if [ "$UPDATED" = 0 ] && [ -n "${OLD:-}" ]; then
    info ""
    info "The old MoClo container is kept, stopped, as ${RETIRED}."
    info "Once you are happy, remove it with:  docker rm ${RETIRED}"
    info "To go back to it instead:            ./install.sh --rollback"
fi
info ""
info "Next: choose where backups go in the backup console (Backups on the landing page)."
