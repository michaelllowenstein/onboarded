# shellcheck shell=bash
# shellcheck disable=SC2034,SC2154
# SC2034: PR_* entries are read by scripts/pr.sh, not here.
# SC2154: PY, REPO, API_URL, GATE_* are set by scripts/gates/lib.sh before this file is sourced.
# PR-11 — ob-admin CLI (API + --local backends)
PR_TITLE[11]="ob-admin — admin CLI with API and local backends"
PR_BRANCH[11]="feat/admin-cli"
PR_BASE[11]="feat/api-dba"

# Scan the fixtures from a temp copy: in the repo they sit under tests/ and fixtures/,
# which the tenant rules (correctly) exclude.
_fixtures() {
  FX=$(mktemp -d "${TMPDIR:-/tmp}/ob-gate-fx.XXXXXX")
  cp "$REPO"/packages/cli/tests/fixtures/scan_fixtures/* "$FX"/
}

# same command through both backends must print identical JSON
_parity() {
  local a b
  a=$(ob_admin --local --json "$@") || true
  b=$(ob_admin --api "$API_URL" --json "$@") || true
  [ "$a" = "$b" ] || { diff <(echo "$a") <(echo "$b") | head -40; return 1; }
}

gate_11() {
  _fixtures
  step "admin-cli: tests" -- bash -c 'cd packages/admin-cli && "$0" -m pytest -q -p no:cacheprovider' "$PY"
  step "--help renders"                  -- ob_admin --help
  step "local: health → 0"               -- expect_exit 0 ob_admin --local health
  step "local: where msi bind → 0"       -- expect_exit 0 ob_admin --local -t msi where bind
  step "local: where zzzz → 4"           -- expect_exit 4 ob_admin --local where zzzz
  step "local: unknown tenant → 4"       -- expect_exit 4 ob_admin --local -t nope ops
  step "local: scan violation → 1"       -- expect_exit 1 ob_admin --local scan "$FX/ViolationService.cs"
  step "local: scan clean → 0"           -- expect_exit 0 ob_admin --local scan "$FX/PolicyService.clean.cs"
  step "local: unknown rule → 5"         -- expect_exit 5 ob_admin --local scan "$FX" -r nope
  step "local: run fix w/o --yes → 7"    -- expect_exit 7 ob_admin --local -t generic run 1001 fix
  step "API down + --api → 6"            -- expect_exit 6 ob_admin --api http://127.0.0.1:9 health

  api_up OB_API_SCAN_ROOTS="$FX"
  step "parity: tenants"                 --live -- _parity tenants
  step "parity: msi where bind"          --live -- _parity -t msi where bind
  step "parity: flotilla tickets"        --live -- _parity -t flotilla tickets
  step "parity: msi status 13"           --live -- _parity -t msi status 13
  step "api: scan violation → 1"         --live -- expect_exit 1 ob_admin --api "$API_URL" scan "$FX/ViolationService.cs"
  step "api: run on exec-off server → 7" --live -- expect_exit 7 ob_admin --api "$API_URL" -t generic run 1001 diagnostic
  api_down
  rm -rf "$FX"
}

smoke_11() {
  cat <<'EOF2'
- ob-admin (or: just admin) tenants / -t msi where bind / -t flotilla ticket 2001 — output readable in your terminal
- NO_COLOR=1 ob-admin rules — no escape codes; piping to a file has no colour either
- With the API stopped, plain `ob-admin tenants` falls back to local (OB_ADMIN_VERBOSE=1 shows [local …])
EOF2
}
