# shellcheck shell=bash
# shellcheck disable=SC2034,SC2154
# SC2034: PR_* entries are read by scripts/pr.sh, not here.
# SC2154: PY, REPO, API_URL, GATE_* are set by scripts/gates/lib.sh before this file is sourced.
# PR-10 — API DBA: tickets, scripts, gated run, instances
PR_TITLE[10]="API DBA — tickets, scripts, gated run, instances"
PR_BRANCH[10]="feat/api-dba"
PR_BASE[10]="feat/api-core"

gate_10() {
  step "dba: unit tests (unchanged package)" -- bash -c 'cd packages/dba && "$0" -m pytest -q -p no:cacheprovider' "$PY"
  step "api: all service tests (incl. DBA)" -- bash -c 'cd packages/api && "$0" -m pytest -q -p no:cacheprovider tests/test_services.py tests/test_dba_service.py' "$PY"
  step "api: HTTP tests" --needs-py fastapi --needs-py httpx -- \
       bash -c 'cd packages/api && "$0" -m pytest -q -p no:cacheprovider tests/test_http.py' "$PY"

  api_up
  step "live: flotilla tickets listed"        --live -- json_ok /api/v1/tenants/flotilla/tickets '"2001" in [t["id"] for t in d]'
  step "live: runbook served"                 --live -- json_ok /api/v1/tenants/flotilla/tickets/2001 'bool(d["runbook"])'
  step "live: run refused while exec off → 403" --live -- \
       expect_http 403 POST /api/v1/tenants/generic/tickets/1001/scripts/diagnostic/run '{}'
  step "live: instances list"                 --live -- json_ok /api/v1/instances '"flotilla" in [i["slug"] for i in d]'

  # Second server with execution enabled: destructive scripts must still need the exact confirm.
  api_down; api_up OB_API_DBA_EXEC=1
  step "live(exec on): fix without confirm → 428" --live -- \
       expect_http 428 POST /api/v1/tenants/generic/tickets/1001/scripts/fix/run '{}'
  step "live(exec on): wrong confirm → 428" --live -- \
       expect_http 428 POST /api/v1/tenants/generic/tickets/1001/scripts/fix/run '{}' 'X-Onboarded-Confirm: 1001/rollback'
  # DB steps use generic:1001 — `just db-init` seeds ob_generic with the demo schema it targets.
  # (flotilla:2001 needs the Flotilla app's schema loaded into ob_flotilla; see instances.md.)
  if ! pg_up; then
    _skip "db: generic 1001 diagnostic (live)"  "Postgres not on :${OB_DB_PORT:-55432} — just db-init"
    _skip "db: generic 1001 dryrun in sandbox" "Postgres not on :${OB_DB_PORT:-55432} — just db-init"
  elif [ -z "${OB_DB_USER:-}${PGUSER:-}" ]; then
    _skip "db: generic 1001 diagnostic (live)"  "no DB user — export OB_DB_PORT=55432 OB_DB_USER=ob_dba (+ ob_instance.py pgpass)"
    _skip "db: generic 1001 dryrun in sandbox" "no DB user — export OB_DB_PORT=55432 OB_DB_USER=ob_dba (+ ob_instance.py pgpass)"
  else
    step "db: generic 1001 diagnostic (live)" --live --needs-py psycopg -- json_ok \
         /api/v1/tenants/generic/tickets/1001/scripts/diagnostic/run \
         'd["ok"] and any(r["rows"] for r in d["results"])' POST '{"sandbox":false}'
    step "db: generic 1001 dryrun in sandbox" --live --needs-py psycopg -- json_ok \
         /api/v1/tenants/generic/tickets/1001/scripts/dryrun/run \
         'd["ok"] and d["mode"] == "sandbox" and "__sbx_" in d["target"]' POST '{"sandbox":true}'
  fi
  api_down
}

smoke_10() {
  cat <<'EOF2'
- just db-init; export OB_DB_PORT=55432 OB_DB_USER=ob_dba; python3 packages/core/scripts/ob_instance.py pgpass
- OB_API_DBA_EXEC=1 just api
- POST /api/v1/tenants/generic/tickets/1001/scripts/dryrun/run {"sandbox":true} → ok, target shows an __sbx_ clone; clone gone afterwards (\l in psql)
- Same for fix with header X-Onboarded-Confirm: 1001/fix → ok; P-1002 in ob_generic still has no current version (live DB untouched)
- Stop Postgres, retry → 503 "Cannot reach the database" (not a 500)
EOF2
}
