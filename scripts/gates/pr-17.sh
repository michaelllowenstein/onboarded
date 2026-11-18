# shellcheck shell=bash
# shellcheck disable=SC2034,SC2154
# SC2034: PR_* entries are read by scripts/pr.sh, not here.
# SC2154: PY, REPO, API_URL, GATE_* are set by scripts/gates/lib.sh before this file is sourced.
# PR-17 — fix the findings of the first real `lint-shell.sh --all` run (+ pinned ruff rules)
PR_TITLE[17]="Lint findings — ShellCheck/zsh -n repo-wide clean, ruff rules pinned, 2 bug fixes"
PR_BRANCH[17]="fix/lint-findings"
PR_BASE[17]="chore/python-entrypoints"

GEN_DB=packages/core/generated/generic/nav_maps_db.zsh

_ruff() {  # workspace ruff: venv module first, then a ruff binary on PATH
  if has_py ruff; then "$PY" -m ruff "$@"; else ruff "$@"; fi
}

_generic_db_form() {  # only `NAME+=( "key" "value" )` entries; none of the two broken forms
  no_match '^[A-Z_]+=\(\s*\[' "$GEN_DB" || return 1             # NAME=( [k]=v )   zsh -n / old zsh
  no_match '^\s+\[[a-z_0-9]+\]=' "$GEN_DB" || return 1          # multi-line [k]=v entries
  no_match '^[A-Z_]+\["' "$GEN_DB" || return 1                  # NAME["k"]=v      quotes stored in key
  local n; n=$(grep -cE '^GENERIC_[A-Z_]+\+=\( "[a-z_0-9]+" ".*" \)$' "$GEN_DB")
  [ "$n" -eq 10 ] || { echo "expected 10 key/value entries, found $n"; return 1; }
}

_validate_unknown_tenant() {  # was: NameError 'path'; now a message and exit 1
  local out rc
  out=$("$PY" packages/core/scripts/validate_domain.py --tenant no-such-tenant 2>&1); rc=$?
  echo "$out"
  [ "$rc" -eq 1 ] && grep -q "domain.json not found" <<<"$out" && ! grep -q Traceback <<<"$out"
}

gate_17() {
  step "generic nav_maps_db.zsh: portable key/value form" -- _generic_db_form
  step "validate_domain: unknown tenant is a clean error"  -- _validate_unknown_tenant
  step "ruff rules pinned in pyproject"                    -- grep -q '^\[tool.ruff.lint\]' pyproject.toml
  step "ruff: all packages clean"         --needs ruff     -- _ruff check packages
  step "shellcheck + zsh -n: whole repo"  --needs shellcheck -- scripts/lint-shell.sh --all
  step "zsh -n: generic nav_maps_db.zsh"  --needs zsh      -- zsh -n "$GEN_DB"
}

smoke_17() {
  cat <<'EOF2'
- scripts/lint-shell.sh --all → "✔ clean" (this is the run that flagged these findings)
- zsh: source packages/core/generated/generic/nav_maps_db.zsh; print $GENERIC_SQL_TEMPLATES[schema_probe]  → the template text (no quotes in the key)
- ob (generic tenant) db/ticket commands that read GENERIC_TICKET_CONFIG still work
- python3 packages/core/scripts/validate_domain.py --tenant nope → message, exit 1, no traceback
EOF2
}
