#!/usr/bin/env zsh
# ─────────────────────────────────────────────────────────────────────────────
# ob_instance.zsh — switch the active onboarded instance in the current shell
#
#   obuse <slug>     load ~/.onboarded/instances/<slug>.env, reload the tenant's
#                    adapters, remember it as the active instance
#   obuse            reload the active instance
#   obi …            ob_instance.py (new, list, clone, db-create, doctor, …)
#
# Sourced by ob_dispatcher.zsh. If OB_TENANT is not set when the dispatcher
# loads, the active instance (~/.onboarded/active) is applied automatically.
# ─────────────────────────────────────────────────────────────────────────────
[[ -n "${_OB_INSTANCE_LOADED:-}" ]] && return 0
typeset -g _OB_INSTANCE_LOADED=1
typeset -g _OB_INSTANCE_REPO="${${(%):-%x}:A:h:h:h:h}"

obi() { python3 "${_OB_INSTANCE_REPO}/packages/core/scripts/ob_instance.py" "$@"; }

_ob_instance_env() {
    local slug="$1" envf="${HOME}/.onboarded/instances/${1}.env"
    [[ -f "$envf" ]] || obi env "$slug" >/dev/null || return 1
    # Unset exactly what the previous instance's env file exported (and nothing
    # else — msi-nav's own MSI_REPO_* variables in a login shell stay untouched).
    local prev="${HOME}/.onboarded/instances/${OB_INSTANCE:-}.env" line
    if [[ -n "${OB_INSTANCE:-}" && -f "$prev" ]]; then
        while IFS= read -r line; do
            [[ "$line" == export\ *=* ]] && { line="${line#export }"; unset "${line%%=*}"; }
        done < "$prev"
    fi
    source "$envf"
}

obuse() {
    local slug="${1:-}"
    [[ -z "$slug" && -f "${HOME}/.onboarded/active" ]] && slug="$(<"${HOME}/.onboarded/active")"
    [[ -z "$slug" ]] && { print -u2 "usage: obuse <slug>   (obi list)"; return 1; }
    _ob_instance_env "$slug" || return 1
    print -r -- "$slug" > "${HOME}/.onboarded/active"
    if (( $+functions[_ob_load_tenant] )); then
        _ob_load_tenant || return 1
        local maps_db="${_OB_INSTANCE_REPO}/packages/core/generated/${slug}/nav_maps_db.zsh"
        [[ -f "$maps_db" ]] && source "$maps_db"
    fi
    print -P "  %F{green}▶ ${slug}%f  db=${OB_DB_NAME:-?}  repos=${OB_ROOT:-?}"
}
