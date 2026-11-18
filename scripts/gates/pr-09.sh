# shellcheck shell=bash
# shellcheck disable=SC2034,SC2154
# SC2034: PR_* entries are read by scripts/pr.sh, not here.
# SC2154: PY, REPO, API_URL, GATE_* are set by scripts/gates/lib.sh before this file is sourced.
# PR-09 — API core: domain view, generator TS output, FastAPI domain + scan endpoints
PR_ID="09"
PR_TITLE[$PR_ID]="API core — tenant domain, where, scan; shared camelCase view"
PR_BRANCH[$PR_ID]="feat/api-core"
PR_BASE[$PR_ID]="docs/mvp-roadmap"

gate_09() {
  step "domain.json valid (all tenants)" -- "$PY" packages/core/scripts/validate_domain.py --all
  step "TS snapshots fresh (generator == committed)" -- snapshots_fresh
  step "shared types + snapshots typecheck (strict)" --needs tsc -- tsc_shared
  step "api: service tests" -- bash -c 'cd packages/api && "$0" -m pytest -q -p no:cacheprovider tests/test_services.py' "$PY"
  step "api: HTTP tests" --needs-py fastapi --needs-py httpx -- \
       bash -c 'cd packages/api && "$0" -m pytest -q -p no:cacheprovider tests/test_http.py' "$PY"

  api_up
  step "live: /health ok, 3 tenants"       --live -- json_ok /health \
       'd["status"] == "ok" and {"generic", "msi", "flotilla"} <= set(d["tenants"])'
  step "live: /docs (OpenAPI UI) served"   --live -- curl -sf -o /dev/null "$API_URL/docs"
  step "live: domain is camelCase"         --live -- json_ok /api/v1/tenants/generic/domain \
       '"scanRules" in d and "scan_rules" not in d and d["queues"] == {}'
  step "live: unknown tenant → 404 problem" --live -- expect_http 404 GET /api/v1/tenants/nope
  step "live: where msi/bind → operation"  --live -- json_ok /api/v1/tenants/msi/where/bind 'd["operation"]["id"] == "bind"'
  step "live: inline scan finds secret"    --live -- json_ok /api/v1/tenants/generic/scan \
       'd["exitCode"] == 1 and d["findings"][0]["ruleId"] == "hardcoded_secret"' POST \
       '{"content":{"filename":"a.cs","text":"var password = \"hunter22\";"}}'
  step "live: scan outside roots → 403"    --live -- expect_http 403 POST /api/v1/tenants/generic/scan '{"paths":["/etc"]}'
}

smoke_09() {
  cat <<'EOF2'
- just api   (or: scripts/pr.sh gate 09 -v) — open http://127.0.0.1:8000/docs, try GET /api/v1/tenants
- Edit a label in packages/core/tenants/generic/domain/domain.json, POST /api/v1/admin/reload, see it change; revert
- Break that domain.json (stray comma), reload → /health shows "degraded" with the reason; revert
EOF2
}
