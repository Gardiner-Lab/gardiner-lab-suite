#!/usr/bin/env bash
# Verify that every route in the suite answers through the single port.
set -uo pipefail

BASE="${BASE:-http://localhost:${SUITE_PORT:-8080}}"
fail=0

check() {
  local path="$1" want="$2" label="$3"
  local code
  code="$(curl -s -o /dev/null -w '%{http_code}' "${BASE}${path}")"
  if [[ "$code" == "$want" ]]; then
    printf '  \033[32mok\033[0m   %-18s %s (%s)\n' "$path" "$label" "$code"
  else
    printf '  \033[31mFAIL\033[0m %-18s %s (got %s, wanted %s)\n' "$path" "$label" "$code" "$want"
    fail=1
  fi
}

echo "Checking ${BASE}"
check "/"               200 "landing page"
check "/tools.json"     200 "tool registry"
check "/suite-health"   200 "proxy"
check "/health"         200 "MoClo"
check "/login"          200 "MoClo login"
check "/editor/health"  200 "Plasmid Editor"
check "/editor/login"   200 "Plasmid Editor login"
check "/editor"         301 "prefix redirect"

if [[ "$fail" == 0 ]]; then
  echo "All routes answered."
else
  echo "Some routes failed; check 'docker compose ps' and 'docker compose logs'." >&2
fi
exit "$fail"
