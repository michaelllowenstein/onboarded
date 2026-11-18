# shellcheck shell=bash
# shellcheck disable=SC2034,SC2154
# SC2034: PR_* entries are read by scripts/pr.sh, not here.
# SC2154: PY, REPO, API_URL, GATE_* are set by scripts/gates/lib.sh before this file is sourced.
# PR-12 — portal builds; all build-time features
PR_TITLE[12]="Portal builds — config fixes, per-tenant builds, build-time pages"
PR_BRANCH[12]="fix/portal-build"
PR_BASE[12]="feat/admin-cli"

PORTAL=packages/portal/src

_routes_have_features() {  # every lazy route import points at an existing feature folder
  local bad=0 d
  for d in $(grep -oE "import\('./features/[a-z-]+'\)" "$PORTAL/app/routes.ts" | sed -E "s/.*features\/([a-z-]+).*/\1/"); do
    [ -f "$PORTAL/app/features/$d/index.ts" ] && [ -f "$PORTAL/app/features/$d/index.html" ] || { echo "missing feature: $d"; bad=1; }
  done
  return $bad
}

_nx_build() { npx nx build @onboarded/portal --configuration="$1" --skip-nx-cache; }

gate_12() {
  step "TS snapshots fresh" -- snapshots_fresh
  step "project.json file paths exist" -- "$PY" - <<'PYEOF'
import json, sys, pathlib
pj = json.load(open("packages/portal/project.json"))
b = pj["targets"]["build"]
paths = [b["options"]["browser"], b["options"]["tsConfig"], *b["options"]["styles"]]
for cfg in b["configurations"].values():
    for r in cfg.get("fileReplacements", []):
        paths += [r["replace"], r["with"]]
missing = [p for p in paths if not pathlib.Path(p).exists()]
print("\n".join(f"missing: {p}" for p in missing) or f"{len(paths)} paths ok")
sys.exit(1 if missing else 0)
PYEOF
  step "every route has a feature folder" -- _routes_have_features
  step "no legacy template syntax (*ngIf/*ngFor)" -- no_match '\*ng(If|For)' "$PORTAL/app"
  step "no redundant standalone: true" -- no_match 'standalone: *true' "$PORTAL/app"
  step "no snake_case domain access in portal" -- no_match '\.(scan_rules|brand_name|see_also|fix_hint)\b' "$PORTAL"
  if [ -d node_modules/@angular/build ]; then
    step "build generic (production)" --slow -- _nx_build production
    step "build msi"                  --slow -- _nx_build msi,production
    step "build flotilla"             --slow -- _nx_build flotilla,production
    step "unit tests"                 --slow -- npx nx test @onboarded/portal --watch=false
  else
    _skip "portal builds + unit tests" "run npm install (or just mvp-install)"
  fi
}

smoke_12() {
  cat <<'EOF2'
- npx nx serve @onboarded/portal -c flotilla → sidebar says Equinor Flotilla, nav labels use Flotilla terminology
- -c generic → Queues and Portals are hidden (tenant defines none); no console errors
- Operations search "mission" filters; expanding a card shows tables + code path where defined
- Scan rules: severity/category filters combine; Glossary "see also" tags re-search
EOF2
}
