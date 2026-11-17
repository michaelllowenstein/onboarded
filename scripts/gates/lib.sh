# shellcheck shell=bash
# ─────────────────────────────────────────────────────────────────────────────
# scripts/gates/lib.sh — shared helpers for the per-PR gates (sourced by scripts/pr.sh)
#
#   step "name" [--slow] [--needs CMD]... [--needs-py MOD]... [--live] -- command args...
#       Runs one check, records PASS / FAIL / SKIP, prints a one-line verdict and,
#       on failure, the last 40 lines of output. Never aborts the gate early.
#
#   --slow       skipped with --fast (portal builds, docker)
#   --needs X    skipped when command X is missing   (FAIL instead with --strict)
#   --needs-py M skipped when python module M is missing (FAIL with --strict)
#   --live       needs the live API started by api_up (skipped if it could not start)
#
# Environment the gates may read: REPO, PY, GATE_FAST, GATE_STRICT, GATE_VERBOSE, API_URL
# ─────────────────────────────────────────────────────────────────────────────

REPO=${REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}
if [ -x "$REPO/.venv/bin/python" ]; then PY=${PY:-$REPO/.venv/bin/python}; else PY=${PY:-python3}; fi
export PYTHONPATH="$REPO/packages/api/src:$REPO/packages/dba/src:$REPO/packages/admin-cli/src${PYTHONPATH:+:$PYTHONPATH}"
GATE_FAST=${GATE_FAST:-0}; GATE_STRICT=${GATE_STRICT:-0}; GATE_VERBOSE=${GATE_VERBOSE:-0}
GATE_LOG_DIR=${GATE_LOG_DIR:-$REPO/.gates/logs}
mkdir -p "$GATE_LOG_DIR"

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  C_OK=$'\033[32m'; C_BAD=$'\033[31m'; C_SKIP=$'\033[33m'; C_DIM=$'\033[2m'; C_B=$'\033[1m'; C_0=$'\033[0m'
else C_OK=; C_BAD=; C_SKIP=; C_DIM=; C_B=; C_0=; fi

GATE_PASS=0; GATE_FAIL=0; GATE_SKIP=0; GATE_FAILED_STEPS=()
_GATE_PREFIX=""

section() { _GATE_PREFIX="$1"; printf '\n%s── %s ──%s\n' "$C_B" "$1" "$C_0"; }

has() { command -v "$1" >/dev/null 2>&1; }
has_py() { "$PY" -c "import $1" >/dev/null 2>&1; }

_skip() {  # _skip name reason
  if [ "$GATE_STRICT" = 1 ] && [ "${2#--fast}" = "$2" ]; then
    GATE_FAIL=$((GATE_FAIL + 1)); GATE_FAILED_STEPS+=("$_GATE_PREFIX: $1 (strict: $2)")
    printf '  %s✖ FAIL%s  %s %s(strict — %s)%s\n' "$C_BAD" "$C_0" "$1" "$C_DIM" "$2" "$C_0"
  else
    GATE_SKIP=$((GATE_SKIP + 1))
    printf '  %s○ SKIP%s  %s %s(%s)%s\n' "$C_SKIP" "$C_0" "$1" "$C_DIM" "$2" "$C_0"
  fi
}

step() {
  local name=$1; shift
  local slow=0 live=0 missing=""
  while [ $# -gt 0 ] && [ "$1" != "--" ]; do
    case $1 in
      --slow) slow=1 ;;
      --live) live=1 ;;
      --needs) has "$2" || missing="${missing:+$missing, }$2"; shift ;;
      --needs-py) has_py "$2" || missing="${missing:+$missing, }python:$2"; shift ;;
      *) echo "step: unknown option $1" >&2; return 2 ;;
    esac
    shift
  done
  [ "${1:-}" = "--" ] && shift
  if [ "$slow" = 1 ] && [ "$GATE_FAST" = 1 ]; then _skip "$name" "--fast"; return 0; fi
  if [ -n "$missing" ]; then _skip "$name" "missing $missing"; return 0; fi
  if [ "$live" = 1 ] && [ -z "${API_URL:-}" ]; then _skip "$name" "$API_SKIP_REASON"; return 0; fi

  local log; log="$GATE_LOG_DIR/$(printf '%s_%s' "$_GATE_PREFIX" "$name" | tr -c 'A-Za-z0-9_.-' '_').log"
  local t0=$SECONDS
  if (cd "$REPO" && "$@") >"$log" 2>&1; then
    GATE_PASS=$((GATE_PASS + 1))
    printf '  %s✔ PASS%s  %s %s(%ss)%s\n' "$C_OK" "$C_0" "$name" "$C_DIM" "$((SECONDS - t0))" "$C_0"
    [ "$GATE_VERBOSE" = 1 ] && sed 's/^/        /' "$log"
  else
    GATE_FAIL=$((GATE_FAIL + 1)); GATE_FAILED_STEPS+=("$_GATE_PREFIX: $name")
    printf '  %s✖ FAIL%s  %s %s(%ss · log: %s)%s\n' "$C_BAD" "$C_0" "$name" "$C_DIM" "$((SECONDS - t0))" "${log#"$REPO"/}" "$C_0"
    tail -n 40 "$log" | sed 's/^/        /'
  fi
  return 0
}

# ── assertion helpers (use as step commands) ────────────────────────────────

# expect_exit CODE cmd...   — passes when cmd exits with exactly CODE
expect_exit() {
  local want=$1; shift
  "$@"; local got=$?
  [ "$got" = "$want" ] || { echo "expected exit $want, got $got: $*"; return 1; }
}

# file_absent_in_git PATH  — passes when PATH is not tracked
not_tracked() { [ -z "$(git ls-files -- "$1")" ] || { echo "$1 is tracked by git"; return 1; }; }

# no_match REGEX PATH...    — passes when grep finds nothing
no_match() {
  local re=$1; shift
  if grep -rnE "$re" "$@"; then echo "↑ forbidden pattern: $re"; return 1; fi
}

# snapshots_fresh — regenerate TS snapshots; fail if git sees a change
snapshots_fresh() {
  "$PY" packages/core/scripts/generate_adapters.py --all --ts-only >/dev/null &&
    git diff --exit-code --stat -- packages/shared/src/lib/tenants ||
    { echo "TS snapshots are stale — run: python3 packages/core/scripts/generate_adapters.py --all --ts-only && commit"; return 1; }
}

# tsc_shared — strict typecheck of shared types + snapshots (workspace tsc, else global).
# Uses a throwaway tsconfig: TS 6 refuses file arguments when a tsconfig.json is present.
tsc_shared() {
  local tsc cfg="$GATE_LOG_DIR/tsconfig.shared.json"
  if [ -x node_modules/.bin/tsc ]; then tsc=node_modules/.bin/tsc; else tsc=$(command -v tsc); fi
  cat > "$cfg" <<JSON
{ "compilerOptions": { "noEmit": true, "strict": true, "skipLibCheck": true, "target": "ES2022",
    "module": "ES2022", "moduleResolution": "bundler", "types": [] },
  "files": ["$REPO/packages/shared/src/index.ts"],
  "include": ["$REPO/packages/shared/src/lib/tenants/*.ts"] }
JSON
  "$tsc" -p "$cfg"
}

# http GET|POST PATH [JSON] [HEADER...] — prints "STATUS BODY"; uses curl
http() {
  local m=$1 p=$2 body=${3:-}; shift 3 2>/dev/null || shift $#
  local args=(-sS -o /tmp/ob_gate_body -w '%{http_code}' -X "$m" "$API_URL$p")
  [ -n "$body" ] && args+=(-H 'Content-Type: application/json' -d "$body")
  for h in "$@"; do args+=(-H "$h"); done
  local code; code=$(curl "${args[@]}") || return 1
  printf '%s %s\n' "$code" "$(cat /tmp/ob_gate_body)"
}

# expect_http STATUS METHOD PATH [JSON] [HEADER...] [-- JQ-free substring]
expect_http() {
  local want=$1; shift
  local out; out=$(http "$@") || { echo "request failed: $*"; return 1; }
  echo "$out" | head -c 600; echo
  [ "${out%% *}" = "$want" ] || { echo "expected HTTP $want"; return 1; }
}

# json_ok PATH PYEXPR [METHOD [BODY [HEADER]]] — call $API_URL$PATH, parse the JSON body as `d`,
# pass when PYEXPR is truthy. Robust to whitespace/key order, unlike grep.
#   json_ok /health 'd["status"] == "ok" and "flotilla" in d["tenants"]'
json_ok() {
  local path=$1 expr=$2 method=${3:-GET} body=${4:-} hdr=${5:-}
  local args=(-sS -X "$method" "$API_URL$path")
  [ -n "$body" ] && args+=(-H 'Content-Type: application/json' -d "$body")
  [ -n "$hdr" ] && args+=(-H "$hdr")
  curl "${args[@]}" | "$PY" -c '
import json, sys
raw = sys.stdin.read()
print(raw[:500])
try:
    d = json.loads(raw)
except ValueError:
    sys.exit("not JSON")
sys.exit(0 if eval(sys.argv[1], {}, {"d": d}) else "assertion false: " + sys.argv[1])' "$expr"
}

# ── live API (started once per gate run when fastapi + uvicorn are installed) ──
# GATE_API_URL=http://host:port uses an API you already run instead of starting one;
# steps that need a differently configured server (api_up ENV=…) then skip.
API_PID=""; API_SKIP_REASON="live API not running"
api_up() {  # api_up [ENV=VAL...]
  [ -n "$API_PID" ] && return 0
  if [ -n "${GATE_API_URL:-}" ]; then
    if [ $# -eq 0 ]; then API_URL=$GATE_API_URL; export API_URL
    else API_URL=""; API_SKIP_REASON="needs a server started with $*; GATE_API_URL is fixed"; fi
    return 0
  fi
  has_py fastapi && has_py uvicorn || { API_URL=""; API_SKIP_REASON="fastapi/uvicorn not installed — just mvp-install"; return 0; }
  has curl || { API_URL=""; API_SKIP_REASON="curl not installed"; return 0; }
  local port; port=$("$PY" -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1])')
  (cd "$REPO" && env OB_API_HOST=127.0.0.1 OB_API_PORT="$port" "$@" "$PY" -m onboarded_api \
     >"$GATE_LOG_DIR/api-server.log" 2>&1) &
  API_PID=$!
  local i; for i in $(seq 1 50); do
    curl -sf "http://127.0.0.1:$port/health" >/dev/null 2>&1 && { API_URL="http://127.0.0.1:$port"; export API_URL; return 0; }
    sleep 0.2
  done
  echo "  (API failed to start — see .gates/logs/api-server.log)"; api_down; API_SKIP_REASON="API failed to start (.gates/logs/api-server.log)"
}
api_down() {
  [ -n "$API_PID" ] && { kill "$API_PID" 2>/dev/null; wait "$API_PID" 2>/dev/null; }
  API_PID=""; API_URL=""; API_SKIP_REASON="live API not running"
}
trap api_down EXIT

# Postgres reachable on the local dev port? (gates that touch a real DB skip otherwise)
pg_up() {
  local port=${OB_DB_PORT:-55432}
  "$PY" - "$port" <<'PYEOF' >/dev/null 2>&1
import socket, sys
s = socket.socket(); s.settimeout(0.5)
sys.exit(0 if s.connect_ex(("127.0.0.1", int(sys.argv[1]))) == 0 else 1)
PYEOF
}

# admin CLI shorthand
ob_admin() { "$PY" -m onboarded_admin "$@"; }
