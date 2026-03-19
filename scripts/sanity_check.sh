#!/usr/bin/env bash
# sanity_check.sh — quick connection test against the local dev API
# Usage: bash scripts/sanity_check.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/.env.local"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE not found — run from repo root" >&2
  exit 1
fi

# shellcheck source=/dev/null
source "$ENV_FILE"

pass=0; fail=0

check() {
  local label="$1" result="$2"
  if [[ "$result" == "ok" ]]; then
    echo "  ✓  $label"
    ((pass++))
  else
    echo "  ✗  $label — $result"
    ((fail++))
  fi
}

echo ""
echo "  Sanity check → $API"
echo "  ─────────────────────────────────"

# 1. Health — API reachable
STATUS=$(python3 -c "
import urllib.request, sys
try:
    urllib.request.urlopen('$API/docs', timeout=5)
    print('ok')
except Exception as e:
    print(str(e))
")
check "API reachable ($API)" "$STATUS"

# 2. Login
TOKEN=$(python3 -c "
import urllib.request, urllib.parse, json, sys
data = urllib.parse.urlencode({'username': '$ADMIN_USER', 'password': '$ADMIN_PASS'}).encode()
req = urllib.request.Request('$API/auth/login', data=data, method='POST')
try:
    resp = urllib.request.urlopen(req, timeout=5)
    body = json.loads(resp.read())
    print(body.get('access_token', ''))
except Exception as e:
    print('')
")

if [[ -n "$TOKEN" ]]; then
  check "Login as $ADMIN_USER" "ok"
else
  check "Login as $ADMIN_USER" "no token returned"
  echo ""
  echo "  $pass passed, $fail failed"
  exit 1
fi

# 3. GET /watchlist
STATUS=$(python3 -c "
import urllib.request, json, sys
req = urllib.request.Request('$API/watchlist', headers={'Authorization': 'Bearer $TOKEN'})
try:
    resp = urllib.request.urlopen(req, timeout=5)
    json.loads(resp.read())
    print('ok')
except Exception as e:
    print(str(e))
")
check "GET /watchlist" "$STATUS"

# 4. GET /trades/
STATUS=$(python3 -c "
import urllib.request, json, sys
req = urllib.request.Request('$API/trades/', headers={'Authorization': 'Bearer $TOKEN'})
try:
    resp = urllib.request.urlopen(req, timeout=5)
    json.loads(resp.read())
    print('ok')
except Exception as e:
    print(str(e))
")
check "GET /trades/" "$STATUS"

# 5. GET /strategies/settings
STATUS=$(python3 -c "
import urllib.request, json, sys
req = urllib.request.Request('$API/strategies/settings', headers={'Authorization': 'Bearer $TOKEN'})
try:
    resp = urllib.request.urlopen(req, timeout=5)
    json.loads(resp.read())
    print('ok')
except Exception as e:
    print(str(e))
")
check "GET /strategies/settings" "$STATUS"

echo "  ─────────────────────────────────"
if [[ $fail -eq 0 ]]; then
  echo "  $pass/$((pass+fail)) passed ✓"
else
  echo "  $pass passed, $fail failed ✗"
  exit 1
fi
echo ""
