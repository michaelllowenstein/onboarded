#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# scripts/pr.sh — the routine for every MVP PR (see docs/roadmap/PR_WORKFLOW.md)
#
#   scripts/pr.sh doctor                    which tools are installed, and which gates need them
#   scripts/pr.sh list                      PRs known to this checkout + gate status
#   scripts/pr.sh flow   NN                 print the whole routine for PR NN
#   scripts/pr.sh start  NN [--patch FILE] [--force]
#                                           new branch for NN (previous gate must be green)
#   scripts/pr.sh gate   NN [--fast] [--strict] [--only] [-v]
#                                           regression (earlier gates, fast) + NN's full gate
#   scripts/pr.sh smoke  NN                 the manual checks a human must eyeball
#   scripts/pr.sh finish NN [--push]        verify green gate on HEAD; push + open the PR
#
#   --fast    skip slow steps (portal builds, docker)       — for the edit/test loop
#   --strict  a step skipped for a missing tool FAILS       — use before `finish`, and in CI
#   --only    don't re-run earlier gates
#
# Exit status: 0 green · 1 a step failed · 2 usage / precondition.
# A green gate writes .gates/NN.pass (HEAD + working-tree fingerprint); `finish` and the
# next `start` refuse to proceed unless that marker matches the current commit.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

if [ -z "${BASH_VERSINFO:-}" ] || [ "${BASH_VERSINFO[0]}" -lt 4 ]; then
  echo "scripts/pr.sh needs bash >= 4 (associative arrays); this is ${BASH_VERSION:-not bash}." >&2
  echo "macOS: brew install bash  (then re-run; the #!/usr/bin/env bash shebang picks it up)" >&2
  exit 2
fi

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
GATES_DIR="$REPO/scripts/gates"
STATE="$REPO/.gates"
export REPO

declare -A PR_TITLE PR_BRANCH PR_BASE
# shellcheck source=scripts/gates/lib.sh
. "$GATES_DIR/lib.sh"
for f in "$GATES_DIR"/pr-*.sh; do
  # shellcheck disable=SC1090
  [ -e "$f" ] && . "$f"
done
IDS=$(printf '%s\n' "${!PR_TITLE[@]}" | sort)

die() { echo "${C_BAD}✖ $*${C_0}" >&2; exit 2; }
known() { [ -n "${PR_TITLE[$1]:-}" ] || die "unknown PR '$1' (known: ${IDS//$'\n'/ })"; }
prev_of() { local p=""; for i in $IDS; do [ "$i" = "$1" ] && break; p=$i; done; echo "$p"; }
fingerprint() { (cd "$REPO" && { git rev-parse HEAD; git status --porcelain --untracked-files=no; } | sha1sum | cut -c1-12); }
marker_ok() {  # marker_ok NN → 0 when .gates/NN.pass matches HEAD and a clean tree
  local m="$STATE/$1.pass"
  [ -f "$m" ] && [ "$(sed -n 's/^fingerprint=//p' "$m")" = "$(fingerprint)" ] &&
    [ -z "$(cd "$REPO" && git status --porcelain --untracked-files=no)" ]
}
norm() { printf '%02d' "$((10#${1:-x}))" 2>/dev/null || die "PR id must be a number"; }

cmd_list() {
  printf '%s%-4s %-22s %-8s %s%s\n' "$C_B" "PR" "BRANCH" "GATE" "TITLE" "$C_0"
  for i in $IDS; do
    local s="-" c=""
    if [ -f "$STATE/$i.pass" ]; then if marker_ok "$i"; then s=green c=$C_OK; else s=stale c=$C_SKIP; fi; fi
    printf '%-4s %-22s %s%-8s%s %s\n' "$i" "${PR_BRANCH[$i]}" "$c" "$s" "$C_0" "${PR_TITLE[$i]}"
  done
}

cmd_doctor() {
  local missing=0
  row() {  # row OK|NO|-- LABEL DETAIL NEEDED-BY
    local mark
    case $1 in OK) mark="${C_OK}✔${C_0}" ;; NO) mark="${C_BAD}✖${C_0}"; missing=$((missing + 1)) ;; *) mark="${C_SKIP}○${C_0}" ;; esac
    printf '  %s %-20s %-34s %s%s%s\n' "$mark" "$2" "$3" "$C_DIM" "$4" "$C_0"
  }
  ver() { "$@" 2>/dev/null | head -1 | grep -oE '[0-9]+(\.[0-9]+)+' | head -1; }
  pymod() { "$PY" -c "import $1, sys; print(getattr($1, '__version__', 'ok'))" 2>/dev/null; }

  echo "${C_B}Toolchain for scripts/pr.sh gates${C_0}  (python: $PY)"
  row OK "bash" "$BASH_VERSION" "all"
  if has git; then row OK git "$(ver git --version)" all; else row NO git "" all; fi
  if has shellcheck; then row OK shellcheck "$(shellcheck --version | sed -n 's/^version: //p')" "00 · 15 (strict)"
  else row NO shellcheck "not installed" "00 · 15 (strict)"; fi
  if has zsh; then row OK zsh "$(ver zsh --version)" "15 (zsh -n)"; else row -- zsh "not installed (zsh -n skipped)" "15"; fi
  local m v
  for m in pytest fastapi uvicorn httpx psycopg yaml; do
    if v=$(pymod "$m"); then row OK "python: $m" "$v" "$(case $m in pytest) echo 09-16;; fastapi|uvicorn) echo 'live steps 09-13';; httpx) echo '09-10 HTTP tests';; psycopg) echo '10 db steps';; yaml) echo 14;; esac)"
    else row NO "python: $m" "missing - just mvp-install" "$(case $m in pytest) echo 09-16;; fastapi|uvicorn) echo 'live steps 09-13';; httpx) echo '09-10 HTTP tests';; psycopg) echo '10 db steps';; yaml) echo 14;; esac)"; fi
  done
  if [ -x "$REPO/node_modules/.bin/tsc" ]; then row OK tsc "node_modules $(ver "$REPO/node_modules/.bin/tsc" -v)" "09"
  elif has tsc; then row OK tsc "PATH $(ver tsc -v)" "09"; else row NO tsc "npm install" "09"; fi
  if [ -d "$REPO/node_modules/@angular/build" ]; then row OK "node_modules" "@angular/build present" "12-13 builds"
  else row NO "node_modules" "npm install" "12-13 builds"; fi
  if has curl; then row OK curl "$(ver curl --version)" "live steps"; else row NO curl "" "live steps"; fi
  if has docker; then
    if docker info >/dev/null 2>&1; then row OK docker "daemon running" "14"; else row NO docker "CLI only - daemon not running" "14 (compose e2e)"; fi
  else row NO docker "not installed" "14"; fi
  if has make; then row OK make "$(ver make --version)" "14"; else row NO make "" "14"; fi
  if has just; then row OK just "$(ver just --version)" "14 (recipes)"; else row NO just "not installed" "14 (recipes)"; fi
  if pg_up; then row OK "postgres :${OB_DB_PORT:-55432}" "answering" "10 db steps"; else row NO "postgres :${OB_DB_PORT:-55432}" "not answering - just db-init" "10 db steps"; fi
  if [ -n "${OB_DB_USER:-}${PGUSER:-}" ]; then row OK "DB user" "${OB_DB_USER:-$PGUSER}" "10 db steps"; else row NO "DB user" "export OB_DB_USER=ob_dba" "10 db steps"; fi
  local pgpass=${PGPASSFILE:-$HOME/.pgpass}
  if [ -f "$pgpass" ]; then row OK "pgpass" "$pgpass" "10 db steps"; else row NO "pgpass" "ob_instance.py pgpass" "10 db steps"; fi
  if has gh; then
    if gh auth status >/dev/null 2>&1; then row OK gh "authenticated" "finish --push"; else row NO gh "not logged in - gh auth login" "finish --push"; fi
  else row -- gh "not installed (finish prints the commands)" "finish --push"; fi
  echo
  if [ "$missing" -eq 0 ]; then echo "${C_OK}✔ everything a --strict gate needs is available${C_0}"
  else echo "${C_SKIP}▲ $missing missing - those steps SKIP normally and FAIL under --strict${C_0}"; fi
  return 0
}

cmd_flow() {
  local n=$1 p; p=$(prev_of "$n")
  cat <<EOF
${C_B}PR-$n — ${PR_TITLE[$n]}${C_0}
  branch ${PR_BRANCH[$n]}  ←  base ${PR_BASE[$n]}

  1. start    scripts/pr.sh start $n${p:+            # requires PR-$p gate green on HEAD}
              (or apply the archive: scripts/pr.sh start $n --patch PR-$n.patch)
  2. build    edit / apply; commit as you go
  3. loop     scripts/pr.sh gate $n --fast          # seconds; repeat until green
  4. full     scripts/pr.sh gate $n --strict        # everything, no skips allowed
  5. smoke    scripts/pr.sh smoke $n                # human checks, tick them off
  6. finish   scripts/pr.sh finish $n --push        # push + gh pr create --base ${PR_BASE[$n]}
  7. merge    after review; on the merged branch re-run: scripts/pr.sh gate $n --strict
EOF
  declare -F "smoke_$n" >/dev/null && { echo; echo "  Smoke checklist:"; "smoke_$n" | sed 's/^/    /'; }
}

cmd_start() {
  local n=$1; shift; local patch="" force=0
  while [ $# -gt 0 ]; do case $1 in --patch) patch=$2; shift ;; --force) force=1 ;; *) die "start: unknown $1" ;; esac; shift; done
  cd "$REPO" || exit 2
  [ -z "$(git status --porcelain --untracked-files=no)" ] || die "working tree not clean — commit or stash first"
  local p; p=$(prev_of "$n")
  if [ -n "$p" ] && [ "$force" = 0 ] && ! marker_ok "$p"; then
    die "PR-$p gate is not green on HEAD. Run: scripts/pr.sh gate $p --strict   (or --force)"
  fi
  if git show-ref --verify --quiet "refs/heads/${PR_BRANCH[$n]}"; then
    git switch "${PR_BRANCH[$n]}" || exit 2
  else
    git switch -c "${PR_BRANCH[$n]}" || exit 2
  fi
  if [ -n "$patch" ]; then
    [ -f "$patch" ] || die "no such patch: $patch"
    git am --3way "$patch" || die "git am stopped — resolve, 'git add', 'git am --continue', then gate"
  fi
  echo "${C_OK}✔${C_0} on ${PR_BRANCH[$n]}. Next: scripts/pr.sh gate $n --fast"
}

cmd_gate() {
  local n=$1; shift; local only=0
  while [ $# -gt 0 ]; do
    case $1 in --fast) GATE_FAST=1 ;; --strict) GATE_STRICT=1 ;; --only) only=1 ;; -v) GATE_VERBOSE=1 ;; *) die "gate: unknown $1" ;; esac
    shift
  done
  export GATE_FAST GATE_STRICT GATE_VERBOSE
  local t0=$SECONDS
  printf '%sGate PR-%s%s — %s%s\n' "$C_B" "$n" "$C_0" "${PR_TITLE[$n]}" \
    "$([ "$GATE_FAST" = 1 ] && echo ' [fast]')$([ "$GATE_STRICT" = 1 ] && echo ' [strict]')"
  if [ "$only" = 0 ]; then
    for i in $IDS; do
      [ "$i" = "$n" ] && break
      local saved=$GATE_FAST; GATE_FAST=1
      section "regression PR-$i (fast)"; "gate_$i"
      GATE_FAST=$saved
    done
  fi
  section "PR-$n"; "gate_$n"

  printf '\n%s%d passed · %d failed · %d skipped%s  (%ss)\n' "$C_B" "$GATE_PASS" "$GATE_FAIL" "$GATE_SKIP" "$C_0" "$((SECONDS - t0))"
  mkdir -p "$STATE"
  if [ "$GATE_FAIL" -gt 0 ]; then
    local f; for f in "${GATE_FAILED_STEPS[@]}"; do printf '  %s✖ %s%s\n' "$C_BAD" "$f" "$C_0"; done
    rm -f "$STATE/$n.pass"; return 1
  fi
  if [ "$GATE_FAST" = 1 ] || [ "$GATE_SKIP" -gt 0 ]; then
    echo "${C_SKIP}▲ green but not complete ($( [ "$GATE_FAST" = 1 ] && echo 'fast mode' || echo "$GATE_SKIP skipped")) — no pass marker written.${C_0}"
    echo "  Before finishing: scripts/pr.sh gate $n --strict"
    return 0
  fi
  { echo "pr=$n"; echo "fingerprint=$(fingerprint)"; echo "head=$(git -C "$REPO" rev-parse --short HEAD)";
    echo "when=$(date -u +%FT%TZ)"; echo "result=$GATE_PASS passed"; } > "$STATE/$n.pass"
  echo "${C_OK}✔ PR-$n gate green — marker written. Next: scripts/pr.sh smoke $n${C_0}"
}

cmd_smoke() {
  local n=$1
  declare -F "smoke_$n" >/dev/null || { echo "PR-$n has no manual checks."; return 0; }
  echo "${C_B}PR-$n manual smoke — do each, tick it in the PR description:${C_0}"
  "smoke_$n"
}

cmd_finish() {
  local n=$1; shift; local push=0
  while [ $# -gt 0 ]; do case $1 in --push) push=1 ;; *) die "finish: unknown $1" ;; esac; shift; done
  cd "$REPO" || exit 2
  [ "$(git branch --show-current)" = "${PR_BRANCH[$n]}" ] || die "not on ${PR_BRANCH[$n]}"
  marker_ok "$n" || die "no green --strict gate for this exact commit. Run: scripts/pr.sh gate $n --strict"
  local body; body=$(mktemp)
  { echo "## ${PR_TITLE[$n]}"; echo; git log --format='%b' -1; echo; echo "## Gate";
    echo; echo '```'; cat "$STATE/$n.pass"; echo '```'; echo; echo "## Manual smoke"; echo;
    declare -F "smoke_$n" >/dev/null && "smoke_$n" | sed 's/^\s*- /- [ ] /'; } > "$body"
  if [ "$push" = 1 ]; then
    git push -u origin "${PR_BRANCH[$n]}" || exit 2
    if has gh; then gh pr create --base "${PR_BASE[$n]}" --head "${PR_BRANCH[$n]}" --title "PR-$n: ${PR_TITLE[$n]}" --body-file "$body"
    else echo "gh not installed — open the PR by hand; body is in $body"; fi
  else
    echo "Gate is green on $(git rev-parse --short HEAD). To publish:"
    echo "  git push -u origin ${PR_BRANCH[$n]}"
    echo "  gh pr create --base ${PR_BASE[$n]} --head ${PR_BRANCH[$n]} --title \"PR-$n: ${PR_TITLE[$n]}\" --body-file $body"
    echo "(or: scripts/pr.sh finish $n --push)"
  fi
}

usage() { sed -n '3,21p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 2; }

[ $# -ge 1 ] || usage
cmd=$1; shift
case $cmd in
  list) cmd_list ;;
  doctor) cmd_doctor ;;
  flow|start|gate|smoke|finish)
    [ $# -ge 1 ] || usage
    n=$(norm "$1"); shift; known "$n"; "cmd_$cmd" "$n" "$@" ;;
  -h|--help|help) usage ;;
  *) usage ;;
esac
