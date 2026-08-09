#!/usr/bin/env zsh
# ─────────────────────────────────────────────────────────────────────────────
# ob_dispatcher.zsh — Onboarded v4.0.0 Unified CLI Dispatcher
#
# Tenant isolation:
#   - All new modules access maps via _ob_get/_ob_keys (never MSI_ directly)
#   - All tenant-specific SQL, scaffold content, and conventions live in
#     generated/<tenant>/nav_maps_db.zsh and templates/<tenant>/
#   - This dispatcher contains zero tenant-specific knowledge
#
# Changes from v3.0.0:
#   - Sources generated/<tenant>/nav_maps_db.zsh (DB extension data)
#   - Sources 6 new engine modules (db, where_ext, ticket, trace, env, capsule)
#   - 8 new case entries, 4 new help sections, tenant-scoped aliases
# ─────────────────────────────────────────────────────────────────────────────

_OB_DISPATCHER_DIR="${${(%):-%x}:h}"

_ob_bootstrap() {
    local base="$_OB_DISPATCHER_DIR"

    source "${base}/core/ob_core_display.zsh" || { print -u2 "onboarded: display load failed"; return 1; }
    source "${base}/core/ob_core_loader.zsh"  || { print -u2 "onboarded: loader failed"; return 1; }
    _ob_load_tenant || return 1

    source "${base}/nav/ob_nav_engine.zsh"    || { print -u2 "onboarded: nav engine failed"; return 1; }
    source "${base}/scan/ob_scan_engine.zsh"  || { print -u2 "onboarded: scan engine failed"; return 1; }

    # v4.0.0 — DB extension data (must load before engine modules)
    local tenant_slug="${OB_NAV_SLUG:l}"
    local repo_root="${base:h:h:h}"
    local maps_db="${repo_root}/packages/core/generated/${tenant_slug}/nav_maps_db.zsh"
    # Fallback path for development layout
    [[ ! -f "$maps_db" ]] && maps_db="${base}/../generated/${tenant_slug}/nav_maps_db.zsh"
    [[ -f "$maps_db" ]] && source "$maps_db"

    # v4.0.0 — engine modules (conditional: graceful if not yet installed)
    for mod in ob_nav_db ob_nav_where_ext ob_nav_ticket ob_nav_trace ob_nav_env ob_nav_capsule; do
        [[ -f "${base}/nav/${mod}.zsh" ]] && source "${base}/nav/${mod}.zsh"
    done

    return 0
}

_ob_bootstrap || { print -u2 "onboarded: bootstrap failed"; return 1; }

# ── Help ─────────────────────────────────────────────────────────────────────
_ob_help() {
    local cli="${OB_CLI_NAME:-ob}"
    _ob_sep
    _ob_bold "  ${cli} — ${OB_BRAND_NAME:-Onboarded} Platform CLI  v4.0.0"
    _ob_sep
    printf '\n'

    _ob_cyan "  NAVIGATION"
    printf '  %-38s  %s\n' "${cli} where <operation>"     "code + data + clusters for an operation"
    printf '  %-38s  %s\n' "${cli} product [key]"          "product line profile"
    printf '  %-38s  %s\n' "${cli} status [code]"          "policy status code"
    printf '  %-38s  %s\n' "${cli} explain [term]"         "domain glossary"
    printf '  %-38s  %s\n' "${cli} portal [key]"           "portal directory"
    printf '  %-38s  %s\n' "${cli} queue [partial]"        "message queue cross-reference"
    printf '\n'

    # Only show DB section if the module loaded
    if (( $+functions[ob_schema] )); then
        _ob_cyan "  DATABASE"
        printf '  %-38s  %s\n' "${cli} schema <table>"          "cached columns + Q0 probe"
        printf '  %-38s  %s\n' "${cli} sql <template> [args]"   "filled diagnostic SQL"
        printf '  %-38s  %s\n' "${cli} cluster <error>"         "classify error → cluster"
        printf '  %-38s  %s\n' "${cli} policy <identifier>"     "policy lookup SQL"
        printf '\n'
    fi

    if (( $+functions[ob_ticket] )); then
        _ob_cyan "  WORKFLOW"
        printf '  %-38s  %s\n' "${cli} ticket <id>"             "start/resume investigation"
        printf '  %-38s  %s\n' "${cli} ticket fix <id>"         "generate fix package"
        printf '  %-38s  %s\n' "${cli} trace"                   "parse exception chain (stdin)"
        printf '\n'
    fi

    if (( $+functions[ob_env] )); then
        _ob_cyan "  ENVIRONMENT"
        printf '  %-38s  %s\n' "${cli} env <key>"               "config key across environments"
        printf '  %-38s  %s\n' "${cli} env list [category]"     "list known config keys"
        printf '  %-38s  %s\n' "${cli} env diff <e1> <e2>"      "show divergent keys"
        printf '\n'
    fi

    if (( $+functions[ob_capsule] )); then
        _ob_cyan "  CAPSULES"
        printf '  %-38s  %s\n' "${cli} capsule list"             "registered capsules"
        printf '  %-38s  %s\n' "${cli} capsule new <key> <ref>"  "scaffold new capsule"
        printf '  %-38s  %s\n' "${cli} capsule demo <key>"       "demo commands"
        printf '\n'
    fi

    _ob_cyan "  CODE SEARCH"
    printf '  %-38s  %s\n' "${cli} list [filter]"          "list domain keys"
    printf '  %-38s  %s\n' "${cli} grep <pattern> [repo]"  "search codebase"
    printf '  %-38s  %s\n' "${cli} cd <target>"            "jump to repo/dir"
    printf '\n'

    _ob_cyan "  COMPLIANCE"
    printf '  %-38s  %s\n' "${cli} secrets"                "credential scan"
    printf '  %-38s  %s\n' "${cli} audit [sev] [cat]"      "full compliance scan"
    printf '  %-38s  %s\n' "${cli} scan <rule_id>"         "single scan rule"
    printf '\n'

    _ob_dim "  Tenant: ${OB_TENANT:-unknown}  |  Slug: ${OB_NAV_SLUG}  |  v4.0.0"
    _ob_sep
}

# ── Main dispatcher ──────────────────────────────────────────────────────────
onboarded() {
    local cmd="${1:l}"; shift 2>/dev/null

    case "$cmd" in
        # Navigation
        where|w)          ob_where "$@" ;;
        status|s)         ob_status "$@" ;;
        product|prod|p)   ob_product "$@" ;;
        portal)           ob_portal "$@" ;;
        queue|q)          ob_queue "$@" ;;
        explain|def|e)    ob_explain "$@" ;;
        grep|g)           ob_grep "$@" ;;
        list|l)           ob_list "$@" ;;
        cd)               ob_cd "$@" ;;

        # Database
        schema|sch)       ob_schema "$@" ;;
        sql)              ob_sql "$@" ;;
        cluster|cls)      ob_cluster "$@" ;;
        policy|pol)       ob_policy "$@" ;;

        # Workflow
        ticket|t)         ob_ticket "$@" ;;
        trace|tr)         ob_trace "$@" ;;

        # Environment
        env)              ob_env "$@" ;;

        # Capsules
        capsule|cap)      ob_capsule "$@" ;;

        # Scanning
        scan)
            local sub="${1:-}"; shift 2>/dev/null
            case "$sub" in
                list|l|"") ob_scan_list ;; *) ob_scan "$sub" "$@" ;;
            esac ;;
        audit|a)          ob_audit "$@" ;;
        secrets|sec)      ob_secrets "$@" ;;

        help|h|"")        _ob_help ;;
        *) _ob_red "Unknown: '${cmd}'"; _ob_dim "  Run: ${OB_CLI_NAME:-ob} help"; return 1 ;;
    esac
}

# ── Alias registration ──────────────────────────────────────────────────────
_ob_register_alias() {
    local cli="${OB_CLI_NAME:-onboarded}"
    [[ "$cli" == "onboarded" ]] && return

    eval "${cli}() { onboarded \"\$@\"; }"
    local -a suffixes=(w s a sec sch sql cls pol t tr env cap)
    local -a commands=(where status audit secrets schema sql cluster policy ticket trace env capsule)
    local i
    for (( i = 1; i <= ${#suffixes}; i++ )); do
        eval "alias ${cli}${suffixes[$i]}='${cli} ${commands[$i]}'"
    done
}
_ob_register_alias

alias ob='onboarded'
alias obw='onboarded where'; alias obs='onboarded status'
alias oba='onboarded audit'; alias obsec='onboarded secrets'
alias obsch='onboarded schema'; alias obsql='onboarded sql'
alias obcls='onboarded cluster'; alias obpol='onboarded policy'
alias obt='onboarded ticket'; alias obtr='onboarded trace'
alias obenv='onboarded env'; alias obcap='onboarded capsule'