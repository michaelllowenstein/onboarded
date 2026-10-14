#!/usr/bin/env zsh
# ─────────────────────────────────────────────────────────────────────────────
# ob_profile.zsh — the ONLY onboarded file your ~/.zshrc sources.
#
# ~/.zshrc carries one managed block (written by `obpaths fix`):
#
#   # >>> onboarded >>>
#   [[ -r "$HOME/.onboarded/root/packages/cli/src/ob_profile.zsh" ]] && \
#       source "$HOME/.onboarded/root/packages/cli/src/ob_profile.zsh"
#   # <<< onboarded <<<
#
# ~/.onboarded/root is a symlink to the checkout. When the repo moves, only that
# link changes (`<new checkout>/reorient.sh --apply`); ~/.zshrc never does.
#
# This file:
#   1. derives ONBOARDED_DIR from its own location (never hard-coded)
#   2. loads ~/.onboarded/paths.conf — the paths that live OUTSIDE the repo:
#        MSI_NAV_DIR        msi-nav checkout (stable tool, swap harness)
#        OB_WORKSPACE       instance workspaces (client clones, runs, overlays)
#        OB_REPOS_ROOT      repos root for tenants without an instance (msi)
#        OB_DEFAULT_TENANT  tenant to load when no instance is active
#   3. warns (does not fail) when any of them no longer exists
#   4. loads the onboarded dispatcher
# ─────────────────────────────────────────────────────────────────────────────
[[ -n "${_OB_PROFILE_LOADED:-}" ]] && return 0
typeset -g _OB_PROFILE_LOADED=1

export ONBOARDED_DIR="${${(%):-%x}:A:h:h:h:h}"

() {
    local conf="$HOME/.onboarded/paths.conf" line k v
    [[ -r "$conf" ]] || return 0
    while IFS= read -r line || [[ -n "$line" ]]; do
        [[ "$line" == [[:space:]]#\#* || "$line" != *=* ]] && continue
        k="${${line%%=*}//[[:space:]]/}"
        v="${line#*=}"; v="${v#[\"\']}"; v="${v%[\"\']}"; v="${v/#\~/$HOME}"
        case "$k" in
            MSI_NAV_DIR|OB_WORKSPACE|OB_REPOS_ROOT|OB_DEFAULT_TENANT) export "$k=$v" ;;
        esac
    done < "$conf"
}

[[ -n "${OB_REPOS_ROOT:-}" && -z "${OB_ROOT:-}" ]] && export OB_ROOT="$OB_REPOS_ROOT"
# An active instance (~/.onboarded/active) beats the default tenant.
if [[ -z "${OB_TENANT:-}" && ! -f "$HOME/.onboarded/active" && -n "${OB_DEFAULT_TENANT:-}" ]]; then
    export OB_TENANT="$OB_DEFAULT_TENANT"
fi

obpaths() { python3 "$ONBOARDED_DIR/packages/core/scripts/ob_paths.py" "$@"; }

() {
    local k stale=()
    for k in MSI_NAV_DIR OB_WORKSPACE OB_REPOS_ROOT; do
        [[ -n "${(P)k:-}" && ! -d "${(P)k}" ]] && stale+=("$k=${(P)k}")
    done
    (( ${#stale} )) && print -u2 "onboarded: path(s) no longer exist: ${(j:, :)stale} — run: obpaths check"
}

source "$ONBOARDED_DIR/packages/cli/src/ob_dispatcher.zsh"
