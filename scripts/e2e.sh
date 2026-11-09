#!/usr/bin/env bash
# Fresh-clone end-to-end verification for local-ai-inference-stack.
#
# Clones the repo into a temp dir (default: your origin remote, override with
# E2E_REPO=/path/or/url), runs setup.sh, brings the whole stack up under
# compose project `test-rl` with every host port remapped +1000 (so it never
# clashes with a running production stack), then exercises the documented
# SiYuan API-token flow and verifies every service.
#
# Env overrides:
#   E2E_REPO      clone source (default: this repo's `origin` remote URL)
#   E2E_BRANCH    branch to clone (default: master)
#   E2E_PROJECT   compose project name (default: test-rl)
#   E2E_DIR       work dir for the clone (default: /tmp/llama-stack-e2e)
#
# Logs to /tmp/llama-stack-e2e.log. Exit 0 = PASS (stack torn down).
# On FAIL the stack is left up for inspection.
set -uo pipefail

REPO=${E2E_REPO:-$(git remote get-url origin 2>/dev/null || pwd)}
BRANCH=${E2E_BRANCH:-master}
LOG=/tmp/llama-stack-e2e.log
T=${E2E_DIR:-/tmp/llama-stack-e2e}
P=${E2E_PROJECT:-test-rl}
PASS=
HEALTH_BODY="$T/health-body.json"

exec > >(tee -a "$LOG") 2>&1

pass() { echo "PASS: $*"; }
failx() { echo "FAIL: $*"; exit 1; }

rm_rf_rootproof() {
  rm -rf "$1" 2>/dev/null || docker run --rm -v "$1:/data" alpine sh -c 'rm -rf /data && exit 0'
}

cleanup() {
  if [ -n "$PASS" ]; then
    echo "=== teardown (test passed) ==="
    if [ -f "$T/compose-test.yml" ]; then
      env -u SIYUAN_TOKEN docker compose -p "$P" -f "$T/compose-test.yml" down -v --remove-orphans 2>&1 | tail -3 || true
    fi
    rm_rf_rootproof "$T"
  else
    echo "TEST FAILED — leaving project '$P' up for inspection:"
    echo "  docker compose -p $P -f $T/compose-test.yml ps"
  fi
}
trap cleanup EXIT

echo "=== $(date -Is) START ==="
rm_rf_rootproof "$T"
git clone --quiet --branch "$BRANCH" --single-branch "$REPO" "$T"
cd "$T"
echo "cloned: $REPO @ $BRANCH — $(git rev-parse --short HEAD) ($(git log -1 --format=%s))"

echo "=== setup.sh ==="
bash setup.sh || failx "setup.sh exited non-zero"
AUTH=$(sed -n 's/^SIYUAN_ACCESS_AUTH_CODE=//p' .env | head -1)
[ ${#AUTH} -eq 20 ] || failx "auth code not generated (len=${#AUTH})"
pass "setup.sh + 20-char SIYUAN_ACCESS_AUTH_CODE"

echo "=== remap host ports +1000 ==="
sed -E 's/^([[:space:]]*)- "([0-9]{2,5}):([0-9]+)"/\1- "1\2:\3"/' docker-compose.yml > compose-test.yml
grep -E '^[[:space:]]+- "1[0-9]+:' compose-test.yml || failx "port remap produced nothing"

echo "=== compose up -d --build (project $P) ==="
# env -u keeps a host SIYUAN_TOKEN from shadowing the .env the test is exercising
env -u SIYUAN_TOKEN docker compose -p "$P" -f compose-test.yml up -d --build 2>&1 | tail -25 || failx "compose up failed"

echo "=== wait for siyuan first boot (workspace/conf.json api token, <=5 min) ==="
tok=""
for i in $(seq 1 60); do
  tok=$(python3 -c 'import json;print(json.load(open("workspace/conf/conf.json"))["api"]["token"])' 2>/dev/null || true)
  [ -n "$tok" ] && break
  sleep 5
done
[ -n "$tok" ] || failx "siyuan api token never appeared in workspace/conf.json"
pass "siyuan booted, api token present (${tok:0:4}...)"

echo "=== documented token flow: set SIYUAN_TOKEN, recreate companion ==="
sed -i "s/^SIYUAN_TOKEN=.*/SIYUAN_TOKEN=$tok/" .env
env -u SIYUAN_TOKEN docker compose -p "$P" -f compose-test.yml up -d --force-recreate siyuan-ai-companion | tail -3 || failx "companion recreate failed"

echo "=== wait for companion /health 200 (first boot indexes the empty workspace, <=15 min) ==="
ok=""
for i in $(seq 1 45); do
  code=$(curl -s -o "$HEALTH_BODY" -w '%{http_code}' http://localhost:18001/health || true)
  if [ "$code" = "200" ]; then ok=1; break; fi
  # bail early if the companion container itself is restarting
  rc=$(docker inspect -f '{{.RestartCount}}' "$P-siyuan-ai-companion-1" 2>/dev/null || echo "gone")
  [ "$rc" != "0" ] && { echo "companion restarted (count=$rc) — dump logs:"; docker logs --tail 40 "$P-siyuan-ai-companion-1" 2>&1; failx "companion crashed"; }
  sleep 20
done
[ -n "$ok" ] || failx "companion /health never returned 200 (last: $(cat "$HEALTH_BODY" 2>/dev/null))"
pass "companion /health: $(cat "$HEALTH_BODY")"

echo "=== final service verification ==="
env -u SIYUAN_TOKEN docker compose -p "$P" -f compose-test.yml ps | sed 's/\t/ /g'

c=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:16806/api/system/version)
[ "$c" = "401" ] && pass "siyuan 401 without token" || echo "NOTE: siyuan /api/system/version -> $c"
c=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Token $tok" http://localhost:16806/api/system/version)
[ "$c" = "200" ] && pass "siyuan 200 with token" || failx "siyuan with token -> $c"
h=$(curl -s http://localhost:16333/healthz)
echo "$h" | grep -q 'healthz check passed' && pass "qdrant /healthz: $h" || failx "qdrant healthz: $h"
h=$(curl -s http://localhost:18088/health)
[ "$h" = "OK" ] && pass "llama-swap /health: $h" || echo "NOTE: llama-swap /health: $h"

echo "=== companion state ==="
docker inspect -f 'RestartCount={{.RestartCount}} Health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$P-siyuan-ai-companion-1"

PASS=1
echo "=== $(date -Is) TEST PASSED ==="