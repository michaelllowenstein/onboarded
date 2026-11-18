# shellcheck shell=bash
# shellcheck disable=SC2034,SC2154
# SC2034: PR_* entries are read by scripts/pr.sh, not here.
# SC2154: PY, REPO, API_URL, GATE_* are set by scripts/gates/lib.sh before this file is sourced.
# PR-13 — portal live features over the API
PR_TITLE[13]="Portal live features — scan, DBA tickets, instances, API status"
PR_BRANCH[13]="feat/portal-api"
PR_BASE[13]="fix/portal-build"

PORTAL=packages/portal/src

gate_13() {
  step "one HTTP entry point (no HttpClient outside core/)" -- bash -c \
       '! grep -rln "inject(HttpClient)" '"$PORTAL"'/app --include=*.ts | grep -v "/core/services/"'
  step "no hard-coded API host in portal" -- no_match 'localhost:8000|127\.0\.0\.1:8000' "$PORTAL"
  step "interceptor registered in app config" -- grep -q 'withInterceptors(\[apiInterceptor\])' "$PORTAL/app/config.ts"
  step "proxy targets the API port" -- grep -q '"target": "http://localhost:8000"' packages/portal/proxy.conf.json
  step "confirm header name matches API" -- bash -c \
       'grep -q "X-Onboarded-Confirm" '"$PORTAL"'/app/core/services/api.ts && grep -q "X-Onboarded-Confirm" packages/api/src/onboarded_api/services/dba_service.py'
  step "API contract types exported from shared" -- bash -c \
       'for t in ScanReport RunResult TicketDetail InstanceSummary Health ProblemDetails; do grep -q "export interface $t" packages/shared/src/lib/types/tenant.types.ts || { echo "missing $t"; exit 1; }; done'
  if [ -d node_modules/@angular/build ]; then
    step "build flotilla (production)" --slow -- npx nx build @onboarded/portal --configuration=flotilla,production --skip-nx-cache
  else
    _skip "portal build" "run npm install (or just mvp-install)"
  fi
  api_up
  step "live: endpoints the portal calls answer" --live -- bash -c \
       'for p in /health /api/v1/tenants/generic/tickets /api/v1/instances; do curl -sf -o /dev/null "$API_URL$p" || { echo "FAIL $p"; exit 1; }; done'
  api_down
}

smoke_13() {
  cat <<'EOF2'
- just api + just portal: sidebar dot green "API ok"; stop the API, click the dot → red "offline"
- Live scan: paste packages/cli/tests/fixtures/scan_fixtures/ViolationService.cs as ViolationService.cs → critical findings with fix hints
- DBA tickets: select 1001 (generic build) / 2001 (-c flotilla), view runbook and each script's SQL
- Without OB_API_DBA_EXEC: run panel replaced by "Execution is disabled" message
- With OB_API_DBA_EXEC=1 + just db-init (generic build): 1001 dryrun in sandbox shows result rows; "fix" stays disabled until you type 1001/fix
- Instances: active instance marked ▶ (after `obi use flotilla`)
EOF2
}
