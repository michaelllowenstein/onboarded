# shellcheck shell=bash
# PR-00 — MVP roadmap + PR workflow (docs, gate framework)
PR_TITLE[00]="MVP roadmap + PR workflow gates"
PR_BRANCH[00]="docs/mvp-roadmap"
PR_BASE[00]="master"

_docs_links_resolve() {  # every repo path in backticks that looks like a file must exist (or be planned)
  local missing=0 p
  for p in $(grep -ohE '`(packages|docs|scripts|deploy|instances)/[A-Za-z0-9_./-]+\.(md|py|ts|json|sh|yml)`' \
             docs/roadmap/MVP_ROADMAP.md docs/roadmap/PR_WORKFLOW.md | tr -d '`' | sort -u); do
    case $p in *NN*|*'<'*) continue ;; esac            # placeholders like pr-NN.sh
    [ -e "$p" ] || { grep -qF "$p" scripts/gates/planned-paths.txt 2>/dev/null || { echo "missing: $p"; missing=1; }; }
  done
  return $missing
}

gate_00() {
  step "roadmap + workflow docs present" -- test -s docs/roadmap/MVP_ROADMAP.md -a -s docs/roadmap/PR_WORKFLOW.md
  step "doc paths resolve" -- _docs_links_resolve
  step "gate scripts parse (bash -n)" -- bash -c 'for f in scripts/pr.sh scripts/gates/*.sh; do bash -n "$f" || exit 1; done'
  step "shellcheck gate scripts" --needs shellcheck -- shellcheck -x -S warning scripts/pr.sh scripts/gates/*.sh
  step ".gates/ is ignored" -- git check-ignore -q .gates/x.pass
}

smoke_00() {
  cat <<'EOF2'
- Read docs/roadmap/MVP_ROADMAP.md §2 Findings; rotate the Nx Cloud token now (F8)
- scripts/pr.sh list   shows every PR you have applied, with gate status
- scripts/pr.sh flow 09   prints a sensible routine
EOF2
}
