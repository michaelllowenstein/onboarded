# shellcheck shell=bash
# shellcheck disable=SC2034,SC2154
# SC2034: PR_* entries are read by scripts/pr.sh, not here.
# SC2154: PY, REPO, API_URL, GATE_* are set by scripts/gates/lib.sh before this file is sourced.
# PR-14 — MVP dev stack: Docker, nginx, compose, just/make recipes
PR_TITLE[14]="MVP dev stack — Docker, compose, just/make recipes"
PR_BRANCH[14]="feat/mvp-devstack"
PR_BASE[14]="feat/portal-api"

_compose_e2e() {
  docker compose up --build -d || return 1
  local i ok=1
  for i in $(seq 1 60); do curl -sf http://127.0.0.1:4200/health >/dev/null && { ok=0; break; }; sleep 2; done
  [ $ok = 0 ] && curl -sf http://127.0.0.1:4200/ | grep -q '<ob-root' && curl -sf http://127.0.0.1:4200/api/v1/tenants | grep -q flotilla
  local rc=$?
  docker compose logs --tail 30
  docker compose down
  return $rc
}

_no_tokens() {
  local files=()
  mapfile -t files < <(git ls-files | grep -vE '^docs/|\.md$')
  no_match 'NX_CLOUD_(CI_)?(ACCESS_)?TOKEN=[A-Za-z0-9]' "${files[@]}"
}

gate_14() {
  step ".env not tracked"                    -- not_tracked .env
  step ".env ignored"                        -- git check-ignore -q .env
  step "no secrets in tracked files"         -- _no_tokens
  step "compose files parse"                 -- "$PY" -c 'import yaml;[yaml.safe_load(open(f)) for f in ("docker-compose.yml","docker-compose.override.yml")]'
  step "make: MVP targets defined"           -- bash -c 'for t in api admin portal mvp-test mvp-up mvp-down; do make -n "$t" >/dev/null 2>&1 || { echo "make $t"; exit 1; }; done'
  step "just: MVP recipes defined" --needs just -- bash -c 'for r in mvp-install api admin portal mvp-test mvp-up; do just --show "$r" >/dev/null || exit 1; done'
  step "full MVP test suite (make mvp-test)" -- make -s mvp-test
  step "docker compose config"  --needs docker -- docker compose config -q
  if has docker && docker info >/dev/null 2>&1; then
    step "compose e2e: portal :4200 → api" --slow -- _compose_e2e
  else
    _skip "compose e2e: portal :4200 → api" "docker daemon not running"
  fi
}

smoke_14() {
  cat <<'EOF2'
- Fresh clone → just mvp-install → just mvp-test green (README quick start works verbatim)
- just mvp-up → http://localhost:4200 loads, API dot green; just mvp-down cleans up
- Nx Cloud token rotated (F8); old one revoked
- Walk the MVP acceptance checklist in docs/roadmap/MVP_ROADMAP.md §4
EOF2
}
