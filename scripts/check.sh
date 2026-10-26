#!/usr/bin/env bash
# Verify the suite through its single port: the proxy, the sign-in in front of
# every tool, and each tool behind it, running the version this release pins.
#
#   ./scripts/check.sh              the suite installed here (SUITE_PORT from .env)
#   BASE=https://host:8080 ./scripts/check.sh  another one
#
# Over https, trusting the lab's certificate authority (certs/lab-suite-ca.crt),
# so the certificate is checked too: it must be valid for the name used here.
#
# Signed out, the proxy answers every tool page itself, by sending the visitor
# to sign in, so a page's redirect says nothing about the tool behind it. Each
# tool is therefore checked at its health route, the one address that reaches
# it without signing in, and its answer must be its own.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# A value from .env, read as text: the file is never run.
env_value() {
  [[ -f "$ROOT/.env" ]] || return 0
  sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" "$ROOT/.env" | tail -1 | tr -d "\r\"'"
}

SUITE_PORT="${SUITE_PORT:-$(env_value SUITE_PORT)}"
BASE="${BASE:-https://localhost:${SUITE_PORT:-8080}}"
fail=0

# Every request trusts the lab's authority, or, with a university certificate
# (certs/.provided), the computer's own trusted ones.
CA="$ROOT/certs/lab-suite-ca.crt"
curl() {
  if [[ -f "$CA" && ! -f "$ROOT/certs/.provided" ]]; then command curl --cacert "$CA" "$@"; else command curl "$@"; fi
}

ok()  { printf '  \033[32mok\033[0m   %-18s %s\n' "$1" "$2"; }
bad() { printf '  \033[31mFAIL\033[0m %-18s %s\n' "$1" "$2"; fail=1; }

# The version a component should be: an override in .env (MOCLO_VERSION and
# the like), else the pin in docker-compose.yml.
pinned() {
  local var="$1" image="$2" v
  v="${!var:-$(env_value "$var")}"
  [[ -n "$v" ]] || v="$(sed -n "s|.*/${image}:\${${var}:-\([^}]*\)}.*|\1|p" "$ROOT/docker-compose.yml" | head -1)"
  echo "$v"
}

# A route that must answer with this status code, as a browser asks for a page.
route() {
  local path="$1" want="$2" label="$3" code
  code="$(curl -s -o /dev/null -H 'Accept: text/html' -w '%{http_code}' "${BASE}${path}")"
  if [[ "$code" == "$want" ]]; then ok "$path" "$label ($code)"; else bad "$path" "$label (got $code, wanted $want)"; fi
}

# A page behind the sign-in: signed out, the proxy must send it to sign in.
gated() {
  local path="$1" label="$2" answer code where
  answer="$(curl -s -o /dev/null -H 'Accept: text/html' -w '%{http_code} %{redirect_url}' "${BASE}${path}")"
  code="${answer%% *}"; where="${answer#* }"
  if [[ "$code" == 302 && "$where" == *"/account/login?next="* ]]; then
    ok "$path" "$label: sends a signed-out visitor to sign in"
  else
    bad "$path" "$label: wanted a redirect to /account/login, got $code ${where:-}"
  fi
}

# A tool, reached through the proxy at its health route: healthy, and the
# version pinned, when the tool reports one.
tool() {
  local path="$1" label="$2" var="${3:-}" image="${4:-}" body want got
  body="$(curl -s -H 'Accept: application/json' "${BASE}${path}")"
  if [[ "$body" != *'"status":"healthy"'* && "$body" != *'"status": "healthy"'* ]]; then
    bad "$path" "$label is not answering healthy: ${body:-no answer}"
    return
  fi
  if [[ -z "$var" ]]; then ok "$path" "$label: healthy"; return; fi
  want="$(pinned "$var" "$image")"
  got="$(sed -n 's/.*"version": *"\([^"]*\)".*/\1/p' <<<"$body")"
  if [[ -z "$want" || "$got" == "$want" ]]; then
    ok "$path" "$label: healthy, version ${got:-?}"
  else
    bad "$path" "$label: running version ${got:-?}, but this release pins $want (pull and restart it: ./install.sh)"
  fi
}

echo "Checking ${BASE}"
echo "The proxy and the sign-in:"
code="$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/suite-health")"
if [[ "$code" == 200 ]]; then ok "https" "the certificate is trusted for ${BASE#https://}"
else bad "https" "no trusted https answer ($code): see docs/HTTPS.md, or run ./scripts/make-certs.sh"; fi
answer="$(command curl -s -o /dev/null -w '%{http_code} %{redirect_url}' "${BASE/https:/http:}/parts")"
if [[ "${answer%% *}" == 301 && "${answer#* }" == https://* ]]; then ok "http" "plain http goes on to https"
else bad "http" "plain http should be sent to https (got $answer)"; fi
route "/lab-suite-ca.crt"  200 "the lab's certificate, to trust, before signing in"
route "/suite-health"     200 "proxy"
route "/account/login"    200 "sign-in page"
route "/account/register" 200 "registration page"
gated "/"                 "landing page"
gated "/tools.json"       "tool list"
gated "/parts"            "MoClo pages"
gated "/editor/editor"    "Plasmid Editor pages"
gated "/notebook/"        "Lab Notebook pages"
gated "/seeds/"           "Seed Bank pages"
gated "/stocks/"          "Lab Stocks pages"
gated "/booking/"         "Booking pages"
route "/editor"           301 "/editor goes to /editor/"
route "/notebook"         301 "/notebook goes to /notebook/"
route "/seeds"            301 "/seeds goes to /seeds/"
route "/stocks"           301 "/stocks goes to /stocks/"
route "/booking"          301 "/booking goes to /booking/"

echo "Each tool, behind the proxy:"
tool "/account/health"  "sign-in service"   SUITE_VERSION    lab-suite-portal
tool "/health"          "MoClo Library Tool"
tool "/editor/health"   "Plasmid Editor"    EDITOR_VERSION   plasmid-editor
tool "/notebook/health" "Lab Notebook"      NOTEBOOK_VERSION lab-notebook
tool "/seeds/health"    "Seed Bank"         SEEDS_VERSION    seed-bank
tool "/stocks/health"   "Lab Stocks"        STOCKS_VERSION   lab-stocks
tool "/booking/health"  "Booking"           BOOKING_VERSION  lab-booking
tool "/backup/health"   "backup console"    SUITE_VERSION    lab-suite-backup

# The file converter has no route through the proxy: where this runs on the
# server itself, Docker says how it is.
if [[ "$BASE" == https://localhost* ]] && command -v docker >/dev/null 2>&1; then
  echo "Inside the server:"
  state="$(docker inspect -f '{{.State.Health.Status}}' lab-converter 2>/dev/null)"
  if [[ "$state" == healthy ]]; then ok "converter" "file converter: healthy"
  else bad "converter" "file converter: ${state:-not running}"; fi
fi

if [[ "$fail" == 0 ]]; then
  echo "All routes answered."
else
  echo "Some checks failed; see 'docker compose ps' and 'docker compose logs <service>'." >&2
fi
exit "$fail"
