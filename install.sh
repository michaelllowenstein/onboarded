#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# install.sh — clean, idempotent install of onboarded from THIS checkout.
#
#   ./install.sh                       install / repair (safe to re-run any time)
#   ./install.sh --tenant flotilla     default tenant when no instance is active
#   ./install.sh --with-db             also start local Postgres (needs deploy/local/db/.env)
#   ./install.sh --with-dba            also create packages/dba/.venv with psycopg
#   ./install.sh --drop-msi-nav        forget the legacy msi-nav path
#   ./install.sh --check               verify only; change nothing
#   ./install.sh --uninstall           remove shell wiring + launchers (keeps instances, DBs, tickets)
#
# What it does
#   1. checks prerequisites (zsh, python3 ≥ 3.10, git required; psql, docker, just, bats optional)
#   2. validates every tenant and generates its adapters
#   3. ~/.onboarded/root → this checkout, ~/.onboarded/paths.conf, ONE managed block
#      in ~/.zshrc (via packages/core/scripts/ob_paths.py; backups kept)
#   4. launchers in ~/.local/bin (onboarded, ob, obi, obpaths) so the commands work
#      from ANY shell, including bash and scripts
#   5. self-test: a fresh zsh and a fresh bash must both find and run `onboarded`
# No msi-nav involvement anywhere.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
BIN="$HOME/.local/bin"
MARK="# onboarded launcher (install.sh) — do not edit; re-run install.sh"
BASH_BEGIN="# >>> onboarded (bash) >>>"; BASH_END="# <<< onboarded (bash) <<<"

TENANT="" MODE=install WITH_DB=0 WITH_DBA=0 DROP_MSI=0
while (( $# )); do
    case "$1" in
        --tenant)       TENANT="$2"; shift 2 ;;
        --with-db)      WITH_DB=1; shift ;;
        --with-dba)     WITH_DBA=1; shift ;;
        --drop-msi-nav) DROP_MSI=1; shift ;;
        --check)        MODE=check; shift ;;
        --uninstall)    MODE=uninstall; shift ;;
        -h|--help)      sed -n '2,22p' "$0"; exit 0 ;;
        *) echo "install.sh: unknown option $1" >&2; exit 2 ;;
    esac
done

if [[ -t 1 ]]; then G=$'\e[32m' R=$'\e[31m' Y=$'\e[33m' D=$'\e[2m' B=$'\e[1m' N=$'\e[0m'; else G="" R="" Y="" D="" B="" N=""; fi
ok()   { printf '  %s✔%s %s\n' "$G" "$N" "$*"; }
bad()  { printf '  %s✖%s %s\n' "$R" "$N" "$*"; FAILS=$((FAILS+1)); }
warn() { printf '  %s⚠%s %s\n' "$Y" "$N" "$*"; }
step() { printf '\n%s── %s%s\n' "$B" "$*" "$N"; }
FAILS=0

# ── 1. prerequisites ─────────────────────────────────────────────────────────
prereqs() {
    step "Prerequisites"
    if command -v zsh >/dev/null; then ok "zsh $(zsh --version | awk '{print $2}')"; else bad "zsh missing — sudo apt install -y zsh"; fi
    if command -v python3 >/dev/null && python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
        ok "python3 $(python3 -c 'import platform; print(platform.python_version())')"
    else bad "python3 ≥ 3.10 missing — sudo apt install -y python3 python3-venv"; fi
    if command -v git >/dev/null; then ok "git $(git --version | awk '{print $3}')"; else bad "git missing — sudo apt install -y git"; fi
    for t in psql docker just bats; do
        if command -v "$t" >/dev/null; then ok "$t (optional)"; else warn "$t not found (optional: $(case $t in psql) echo 'live DB commands — sudo apt install -y postgresql-client';; docker) echo 'local Postgres';; just) echo 'task runner — make works too';; bats) echo 'shell test suites';; esac))"; fi
    done
    local sh; sh="$(basename "${SHELL:-}")"
    if [[ "$sh" == zsh ]]; then ok "login shell is zsh"
    else warn "login shell is ${sh:-unknown}: commands work through the launchers; for obuse / onboarded cd use zsh (chsh -s \"\$(command -v zsh)\")"; fi
}

default_tenant() {
    if [[ -n "$TENANT" ]]; then echo "$TENANT"; return; fi
    local conf="$HOME/.onboarded/paths.conf" t=""
    [[ -r "$conf" ]] && t="$(sed -n 's/^OB_DEFAULT_TENANT=//p' "$conf" | tail -1)"
    if [[ -n "$t" && "$t" != msi && -f "$HERE/packages/core/tenants/$t/domain/domain.json" ]]; then echo "$t"; return; fi
    [[ -f "$HERE/packages/core/tenants/flotilla/domain/domain.json" ]] && { echo flotilla; return; }
    echo generic
}

# ── self-test (used by install and --check) ──────────────────────────────────
selftest() {
    local t="$1"
    step "Self-test (tenant: $t)"
    if [[ -L "$HOME/.onboarded/root" && "$(cd "$HOME/.onboarded/root" 2>/dev/null && pwd -P)" == "$HERE" ]]; then
        ok "~/.onboarded/root → this checkout"
    else bad "~/.onboarded/root does not point at $HERE"; fi
    if grep -qF "# >>> onboarded >>>" "${ZDOTDIR:-$HOME}/.zshrc" 2>/dev/null; then ok "managed block in ${ZDOTDIR:-$HOME}/.zshrc"
    else bad "managed block missing from ${ZDOTDIR:-$HOME}/.zshrc"; fi
    if [[ -f "$HERE/packages/core/generated/$t/nav_maps.zsh" ]]; then ok "adapters generated for $t"
    else bad "no adapters for $t — python3 packages/core/scripts/generate_adapters.py --tenant $t"; fi
    if command -v zsh >/dev/null; then
        local out
        local -a envv=(HOME="$HOME" PATH="$PATH" TERM=dumb USER="${USER:-}")
        [[ -n "${ZDOTDIR:-}" ]] && envv+=(ZDOTDIR="$ZDOTDIR")
        out="$(cd / && env -i "${envv[@]}" \
               zsh -i -c 'whence -w onboarded ob 2>&1; onboarded help >/dev/null 2>&1 && print help-ok' 2>&1)"
        [[ "$out" == *"onboarded: function"* ]] && ok "fresh zsh: onboarded is a function" || bad "fresh zsh: onboarded not defined — output: ${out:0:200}"
        [[ "$out" == *"ob: alias"* ]] && ok "fresh zsh: ob alias" || bad "fresh zsh: ob alias missing"
        [[ "$out" == *help-ok* ]] && ok "fresh zsh: onboarded help runs" || bad "fresh zsh: onboarded help failed"
    fi
    for l in onboarded ob obi obpaths; do
        if [[ -x "$BIN/$l" ]] && grep -qF "$MARK" "$BIN/$l"; then ok "launcher $BIN/$l"; else bad "launcher $BIN/$l missing"; fi
    done
    local bout
    bout="$(cd / && env -i HOME="$HOME" PATH="$BIN:$PATH" TERM=dumb bash -c 'onboarded help >/dev/null 2>&1 && echo bash-ok' 2>&1)"
    [[ "$bout" == *bash-ok* ]] && ok "bash (via launcher): onboarded help runs" || bad "bash (via launcher): onboarded failed — ${bout:0:200}"
    case ":$PATH:" in *":$BIN:"*) ok "$BIN is on your PATH" ;; *) warn "$BIN is not on this shell's PATH yet — open a new terminal" ;; esac
    if python3 "$HERE/packages/core/scripts/ob_paths.py" check >/dev/null 2>&1; then ok "obpaths check: all paths resolve"
    else warn "obpaths check reports stale paths — run: obpaths check"; fi
}

write_launcher() {   # name, body
    mkdir -p "$BIN"
    local f="$BIN/$1"
    if [[ -e "$f" ]] && ! grep -qF "$MARK" "$f"; then warn "$f exists and is not ours — left alone"; return; fi
    printf '#!/usr/bin/env bash\n%s\n%s\n' "$MARK" "$2" > "$f"
    chmod +x "$f"
}

bash_block() {   # keep ~/.local/bin on PATH for bash users
    local rc="$HOME/.bashrc"
    [[ -f "$rc" ]] || return 0
    grep -qF "$BASH_BEGIN" "$rc" && return 0
    printf '\n%s\ncase ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) export PATH="$HOME/.local/bin:$PATH" ;; esac\n%s\n' \
        "$BASH_BEGIN" "$BASH_END" >> "$rc"
    ok "~/.bashrc: ~/.local/bin on PATH"
}

remove_block() {   # file, begin, end
    local f="$1" b="$2" e="$3"
    [[ -f "$f" ]] && grep -qF "$b" "$f" || return 0
    cp "$f" "$BK/$(echo "$f" | tr / %)"
    awk -v b="$b" -v e="$e" '$0==b{skip=1;next} $0==e{skip=0;next} !skip' "$f" > "$f.tmp" && mv "$f.tmp" "$f"
    ok "removed onboarded block from ${f/#$HOME/~}"
}

# ── modes ────────────────────────────────────────────────────────────────────
case "$MODE" in
check)
    prereqs
    selftest "$(default_tenant)"
    echo
    (( FAILS )) && { echo "${R}✖ $FAILS problem(s).${N} Repair: $HERE/install.sh"; exit 1; } || echo "${G}✔ onboarded is installed and working.${N}"
    exit 0 ;;
uninstall)
    BK="$HOME/.onboarded/backups/uninstall-$(date +%Y%m%d-%H%M%S)"; mkdir -p "$BK"
    step "Uninstall"
    remove_block "${ZDOTDIR:-$HOME}/.zshrc" "# >>> onboarded >>>" "# <<< onboarded <<<"
    remove_block "$HOME/.bashrc" "$BASH_BEGIN" "$BASH_END"
    for l in onboarded ob obi obpaths; do
        [[ -f "$BIN/$l" ]] && grep -qF "$MARK" "$BIN/$l" && rm -f "$BIN/$l" && ok "removed $BIN/$l"
    done
    [[ -L "$HOME/.onboarded/root" ]] && rm -f "$HOME/.onboarded/root" && ok "removed ~/.onboarded/root"
    echo; echo "  Kept: ~/.onboarded (paths.conf, instances, tickets), workspace, databases. Backups: ${BK/#$HOME/~}"
    exit 0 ;;
esac

# ── install ──────────────────────────────────────────────────────────────────
echo "${B}Installing onboarded from ${HERE/#$HOME/~}${N}"
prereqs
(( FAILS )) && { echo; echo "${R}Install stopped: required tools missing (see ✖ above).${N}"; exit 1; }
T="$(default_tenant)"

step "Tenants: validate + generate"
if ( cd "$HERE" && python3 packages/core/scripts/validate_domain.py --all >/dev/null ); then ok "all tenant domains valid"
else bad "validation failed — python3 packages/core/scripts/validate_domain.py --all"; fi
if ( cd "$HERE" && python3 packages/core/scripts/generate_adapters.py --all >/dev/null ); then ok "adapters generated for every tenant"
else bad "generation failed — python3 packages/core/scripts/generate_adapters.py --all"; fi

step "Paths and shell wiring (default tenant: $T)"
args=(fix --apply --default-tenant "$T")
(( DROP_MSI )) && args+=(--no-msi-nav)
if python3 "$HERE/packages/core/scripts/ob_paths.py" "${args[@]}" > "$HOME/.onboarded-install.log" 2>&1; then
    ok "~/.onboarded/root, paths.conf, ~/.zshrc managed block (details: ~/.onboarded-install.log)"
else
    grep -q '✖' "$HOME/.onboarded-install.log" && warn "some paths still stale — see ~/.onboarded-install.log (obpaths check)" || bad "ob_paths failed — see ~/.onboarded-install.log"
fi
mkdir -p "$HOME/.onboarded"; mv -f "$HOME/.onboarded-install.log" "$HOME/.onboarded/install.log" 2>/dev/null || true

step "Launchers (any shell)"
LAUNCH_OB='exec zsh -f -c '"'"'r=$1; shift; source "$r/packages/cli/src/ob_profile.zsh" && onboarded "$@"'"'"' onboarded "$HOME/.onboarded/root" "$@"'
write_launcher onboarded "$LAUNCH_OB"
write_launcher ob "$LAUNCH_OB"
write_launcher obi 'exec python3 "$HOME/.onboarded/root/packages/core/scripts/ob_instance.py" "$@"'
write_launcher obpaths 'exec python3 "$HOME/.onboarded/root/packages/core/scripts/ob_paths.py" "$@"'
ok "onboarded, ob, obi, obpaths → $BIN"
bash_block

if (( WITH_DBA )); then
    step "DBA engine venv"
    if python3 -m venv "$HERE/packages/dba/.venv" && "$HERE/packages/dba/.venv/bin/pip" install -q -e "$HERE/packages/dba[postgres,test]"; then
        ok "packages/dba/.venv with psycopg"
    else bad "DBA venv failed — see pip output above"; fi
fi
if (( WITH_DB )); then
    step "Local Postgres"
    if [[ -f "$HERE/deploy/local/db/.env" ]]; then "$HERE/deploy/local/db/init-local-db.sh" && python3 "$HERE/packages/core/scripts/ob_instance.py" pgpass && ok "Postgres up, ~/.pgpass written"
    else warn "deploy/local/db/.env missing — cp deploy/local/db/.env.example deploy/local/db/.env (edit passwords), then re-run with --with-db"; fi
fi

selftest "$T"
echo
if (( FAILS )); then echo "${R}✖ $FAILS problem(s) above.${N} Fix them and re-run ./install.sh (it is safe to re-run)."; exit 1; fi
echo "${G}✔ onboarded installed.${N} Open a new terminal (or: exec zsh), then:  onboarded help"
