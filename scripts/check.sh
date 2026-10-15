#!/usr/bin/env bash
# Verify that every route in the suite answers through the single port.
set -uo pipefail

BASE="${BASE:-http://localhost:${SUITE_PORT:-8080}}"
fail=0

check() {
  local path="$1" want="$2" label="$3"
  local code
  # As a browser asks for a page, signed out.
  code="$(curl -s -o /dev/null -H 'Accept: text/html' -w '%{http_code}' "${BASE}${path}")"
  if [[ "$code" == "$want" ]]; then
    printf '  \033[32mok\033[0m   %-18s %s (%s)\n' "$path" "$label" "$code"
  else
    printf '  \033[31mFAIL\033[0m %-18s %s (got %s, wanted %s)\n' "$path" "$label" "$code" "$want"
    fail=1
  fi
}

echo "Checking ${BASE}"
check "/"               302 "landing page, to sign in first"
check "/tools.json"     302 "tool registry, to sign in first"
check "/suite-health"   200 "proxy"
check "/account/login"  200 "suite sign-in"
check "/account/health" 200 "sign-in service"
check "/health"         200 "MoClo"
check "/login"          302 "MoClo login, to the suite's"
check "/parts"          302 "MoClo page, to sign in first"
check "/account/register" 200 "registration"
check "/editor/health"  200 "Plasmid Editor"
check "/editor/login"   302 "Plasmid Editor login, to the suite's"
check "/editor"         301 "prefix redirect"
check "/notebook/health" 200 "Lab Notebook"
check "/notebook"       301 "prefix redirect"

if [[ "$fail" == 0 ]]; then
  echo "All routes answered."
else
  echo "Some routes failed; check 'docker compose ps' and 'docker compose logs'." >&2
fi
exit "$fail"
