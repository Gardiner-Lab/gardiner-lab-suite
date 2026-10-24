#!/usr/bin/env bash
# The demo: a teaching chair group, its two labs and accounts, and example work
# in every module (demo/README.md). Run from anywhere, on the server, with the
# suite running:
#
#   demo/demo.sh load     make the accounts and labs (if need be) and fill them
#   demo/demo.sh reset    remove the demo's data, then fill it again (before a class)
#   demo/demo.sh wipe     remove the demo's data, and leave it empty
#
#   DEMO_PASSWORD=...        the accounts' password (default trellis-demo)
#   DEMO_SHOW_ON_LOGIN=1     offer the demo login on the sign-in page
#   SUITE_URL=https://...    where the suite is (default: this server's, from .env)
set -euo pipefail

cd "$(dirname "$0")/.."
here="demo"
action="${1:-}"

python=python3
command -v python3 >/dev/null 2>&1 || python=python

if [ -z "${SUITE_URL:-}" ]; then
    public=$(grep -E '^SUITE_PUBLIC_URL=' .env 2>/dev/null | tail -1 | cut -d= -f2- || true)
    port=$(grep -E '^HTTPS_PORT=' .env 2>/dev/null | tail -1 | cut -d= -f2- || true)
    SUITE_URL="${public:-https://localhost:${port:-8080}}"
fi
insecure=()
case "$SUITE_URL" in https://localhost*|https://127.0.0.1*) insecure=(--insecure) ;; esac

accounts() {
    echo "Accounts and labs:"
    out=$(docker compose exec -T -e DEMO_PASSWORD="${DEMO_PASSWORD:-}" -e DEMO_SHOW_ON_LOGIN="${DEMO_SHOW_ON_LOGIN:-}" \
        portal python - < "$here/accounts.py")
    echo "$out" | grep -v '^WHO '
    WHO=$(echo "$out" | grep '^WHO ' | cut -c5-)
}

wipe() {
    echo "Removing the demo's data:"
    for module in seeds:seeds stocks:stocks notebook:notebook booking:booking editor:editor moclo:moclo; do
        docker compose exec -T "${module%%:*}" python - "${module#*:}" "$WHO" < "$here/wipe.py"
    done
}

load() {
    "$python" "$here/load.py" --url "$SUITE_URL" ${DEMO_PASSWORD:+--password "$DEMO_PASSWORD"} "${insecure[@]}"
}

case "$action" in
    load) accounts; load ;;
    reset) accounts; wipe; load ;;
    wipe) accounts; wipe ;;
    *) sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
