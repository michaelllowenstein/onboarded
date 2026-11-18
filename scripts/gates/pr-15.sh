# shellcheck shell=bash
# shellcheck disable=SC2034,SC2154
# SC2034: PR_* entries are read by scripts/pr.sh, not here.
# SC2154: PY, REPO, API_URL, GATE_* are set by scripts/gates/lib.sh before this file is sourced.
# PR-15 — shell lint (ShellCheck) + gates runbook + pr.sh doctor
PR_TITLE[15]="Shell lint — ShellCheck config, lint-shell.sh, runbook, pr.sh doctor"
PR_BRANCH[15]="chore/shell-lint"
PR_BASE[15]="feat/mvp-devstack"

_bash_parses() {  # bash -n every tracked bash/sh script (needs no tools)
  local f bad=0
  while IFS= read -r f; do bash -n "$f" || { echo "syntax: $f"; bad=1; }; done < <(_shell_files bash)
  return $bad
}
_shell_files() {  # _shell_files bash|zsh  — tracked files of that kind (same rules as lint-shell.sh)
  local f
  # shellcheck source=scripts/lint-shell.sh disable=SC1091
  source <(sed -n '/^kind() {/,/^}/p' scripts/lint-shell.sh)
  git ls-files | while IFS= read -r f; do [ -f "$f" ] && [ "$(kind "$f")" = "$1" ] && echo "$f"; done
}
_no_crlf() {  # CRLF line endings break bash ("$'\r': command not found") and trip SC1017
  local hits
  hits=$( { _shell_files bash; _shell_files zsh; } | xargs grep -l $'\r' 2>/dev/null)
  [ -z "$hits" ] || { echo "CRLF line endings in:"; echo "$hits"; echo "fix: git add --renormalize . (with .gitattributes '*.sh text eol=lf')"; return 1; }
}

gate_15() {
  step ".shellcheckrc present"                -- test -s .shellcheckrc
  step "lint-shell.sh --help"                 -- scripts/lint-shell.sh --help
  step "every bash script parses (bash -n)"   -- _bash_parses
  step "no CRLF in shell scripts"             -- _no_crlf
  step "shell files are LF in .gitattributes" -- grep -qE '^\*\.(sh|zsh) .*eol=lf' .gitattributes
  step "shellcheck: PR tooling"         --needs shellcheck -- scripts/lint-shell.sh
  step "shellcheck: files changed vs master" --needs shellcheck -- scripts/lint-shell.sh --changed
  step "zsh -n: CLI + feedback zsh"     --needs zsh -- bash -c 'scripts/lint-shell.sh $(git ls-files "*.zsh") | tee /dev/stderr | grep -q "✔ clean"'
  step "pr.sh doctor runs"                    -- scripts/pr.sh doctor
  step "runbook present"                      -- test -s docs/development/runbook-pr-gates.md
}

smoke_15() {
  cat <<'EOF2'
- scripts/pr.sh doctor on your machine: every row you need for --strict is ✔
- scripts/lint-shell.sh --all: read the findings in pre-existing scripts (install.sh, reorient.sh, init-local-db.sh); fix or file them — not a blocker for this PR
- Open a .sh file in your editor with the ShellCheck extension: warnings match scripts/lint-shell.sh
- Follow docs/development/runbook-pr-gates.md §2 from a fresh terminal; anything unclear → fix the runbook
EOF2
}
