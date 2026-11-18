#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# scripts/lint-shell.sh — ShellCheck for bash/sh scripts; `zsh -n` for zsh scripts
#
#   scripts/lint-shell.sh                    PR tooling: scripts/pr.sh, scripts/lint-shell.sh, scripts/gates/*.sh
#   scripts/lint-shell.sh --changed [BASE]   shell files changed vs BASE (default: merge-base with master)
#   scripts/lint-shell.sh --all              every tracked shell script in the repo
#   scripts/lint-shell.sh FILE...            exactly these files
#   ... -- SHELLCHECK-ARGS                   passed through, e.g.  -- -f diff   or   -- -S style
#
#   LINT_SEVERITY=style|info|warning|error   minimum severity reported (default: warning)
#
# ShellCheck does not support zsh. Files with a .zsh extension or a zsh shebang get a
# syntax-only `zsh -n` check instead (skipped with a notice when zsh is not installed).
#
# Only ShellCheck's own findings go to stdout (so `-- -f diff | git apply` works);
# status lines go to stderr.
# Exit: 0 clean · 1 findings or zsh syntax errors · 2 shellcheck missing / usage
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$REPO" || exit 2

mode=tooling base="" files=() extra=()
while [ $# -gt 0 ]; do
  case $1 in
    --all) mode=all ;;
    --changed) mode=changed; if [ $# -gt 1 ] && [ "${2#-}" = "$2" ]; then base=$2; shift; fi ;;
    --) shift; extra=("$@"); break ;;
    -h|--help) sed -n '3,18p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) echo "lint-shell: unknown option $1" >&2; exit 2 ;;
    *) mode=files; files+=("$1") ;;
  esac
  shift
done

# kind FILE → bash | zsh | other   (shebang wins; extension when there is none)
# .bats files are left out on purpose: they source zsh helpers (lint them by hand if wanted).
kind() {
  local first=""
  IFS= read -r first < "$1" 2>/dev/null || true
  case $first in
    '#!'*bats*) echo other; return ;;
    '#!'*zsh*) echo zsh; return ;;
    '#!'*bash*|'#!'*/sh|'#!'*/sh\ *|'#!'*' sh'|'#!'*dash*|'#!'*ksh*) echo bash; return ;;
  esac
  case $1 in
    *.zsh) echo zsh ;;
    *.sh|*.bash) echo bash ;;
    *) echo other ;;
  esac
}

case $mode in
  tooling) mapfile -t files < <(ls scripts/pr.sh scripts/lint-shell.sh scripts/gates/*.sh 2>/dev/null) ;;
  all)     mapfile -t files < <(git ls-files) ;;
  changed)
    base=${base:-$(git merge-base HEAD master 2>/dev/null || git rev-parse HEAD~1)}
    mapfile -t files < <({ git diff --name-only --diff-filter=ACMR "$base"; git diff --name-only --diff-filter=ACMR; } | sort -u) ;;
esac

sh_files=() zsh_files=()
for f in "${files[@]}"; do
  [ -f "$f" ] || continue
  case $(kind "$f") in
    bash) sh_files+=("$f") ;;
    zsh)  zsh_files+=("$f") ;;
  esac
done

rc=0
if [ ${#sh_files[@]} -gt 0 ]; then
  if ! command -v shellcheck >/dev/null 2>&1; then
    echo "✖ shellcheck not installed — see docs/development/runbook-pr-gates.md §1" >&2
    exit 2
  fi
  echo "shellcheck $(shellcheck --version | sed -n 's/^version: //p') · ${#sh_files[@]} file(s) · severity ≥ ${LINT_SEVERITY:-warning}" >&2
  shellcheck -x -S "${LINT_SEVERITY:-warning}" "${extra[@]}" "${sh_files[@]}" || rc=1
fi
if [ ${#zsh_files[@]} -gt 0 ]; then
  if command -v zsh >/dev/null 2>&1; then
    echo "zsh -n · ${#zsh_files[@]} file(s) (syntax only — shellcheck does not support zsh)" >&2
    for f in "${zsh_files[@]}"; do zsh -n "$f" || { echo "  ✖ $f" >&2; rc=1; }; done
  else
    echo "○ zsh not installed — ${#zsh_files[@]} zsh file(s) not syntax-checked" >&2
  fi
fi
[ ${#sh_files[@]} -eq 0 ] && [ ${#zsh_files[@]} -eq 0 ] && echo "no shell files to lint" >&2
[ $rc -eq 0 ] && echo "✔ clean" >&2
exit $rc
