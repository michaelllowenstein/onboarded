#!/usr/bin/env zsh
# ─────────────────────────────────────────────────────────────────────────────
# ob_nav_env.zsh — Environment and config awareness  v4.0.0
#
# Commands:
#   ob_env <key>                 Look up a config key across environments
#   ob_env list [category]       List all known config keys
#   ob_env diff <env1> <env2>    Show divergent keys
#
# Tenant isolation:
#   - Config keys: ${OB_NAV_SLUG}_CONFIG_KEYS
#     Format: key_path|type|category|env1_val|env2_val|env3_val|related|notes
#   - Environment list: ${OB_NAV_SLUG}_ENV_CONFIG
#     Keys: env_names (semicolon-separated), env_<name>_instance
#     The engine doesn't know environment names — it reads them from data.
#
# Depends on: ob_core_loader.zsh
# ─────────────────────────────────────────────────────────────────────────────

[[ -n "${_OB_NAV_ENV_LOADED:-}" ]] && return 0
typeset -g _OB_NAV_ENV_LOADED=1

# ── Read environment list from tenant config ─────────────────────────────────
_ob_env_names() {
    local names; names="$(_ob_get ENV_CONFIG env_names 2>/dev/null)"
    : "${names:=dev;test;prod}"
    printf '%s' "$names"
}

_ob_env_instance() {
    local env_name="$1"
    _ob_get ENV_CONFIG "env_${env_name}_instance" 2>/dev/null
}

# ═══════════════════════════════════════════════════════════════════════════════
ob_env() {
    local sub="${1:-}"
    case "$sub" in
        list) shift; _ob_env_list "$@" ;;
        diff) shift; _ob_env_diff "$@" ;;
        "")   _ob_env_help ;;
        *)    _ob_env_lookup "$sub" ;;
    esac
}

_ob_env_help() {
    _ob_bold "Environment & Config Awareness"
    _ob_sep
    printf "  %-42s  %s\n" "${OB_CLI_NAME:-ob} env <key>"           "Config key across environments"
    printf "  %-42s  %s\n" "${OB_CLI_NAME:-ob} env list [category]" "List all known config keys"
    printf "  %-42s  %s\n" "${OB_CLI_NAME:-ob} env diff <e1> <e2>"  "Show divergent keys"
    _ob_sep
}

_ob_env_lookup() {
    local query="${1:l}"

    local matched_key=""
    while IFS= read -r k; do
        [[ "${k:l}" == "${query}" ]] && { matched_key="$k"; break; }
    done < <(_ob_keys CONFIG_KEYS 2>/dev/null)
    if [[ -z "$matched_key" ]]; then
        while IFS= read -r k; do
            [[ "${k:l}" == *"${query}"* ]] && { matched_key="$k"; break; }
        done < <(_ob_keys CONFIG_KEYS 2>/dev/null)
    fi
    [[ -z "$matched_key" ]] && { _ob_red "No config key matching: '${1}'"; return 1; }

    local data; data="$(_ob_get CONFIG_KEYS "$matched_key")"
    # Parse: key_path|type|category|val1|val2|val3|related|notes
    local key_path="${data%%|*}";  local rest="${data#*|}"
    local ktype="${rest%%|*}";     rest="${rest#*|}"
    local category="${rest%%|*}";  rest="${rest#*|}"

    _ob_sep
    _ob_bold "  CONFIG KEY: ${key_path}"
    _ob_sep
    print ""

    # Display value per environment
    local -a env_names; env_names=("${(@s:;:)$(_ob_env_names)}")
    for env_name in "${env_names[@]}"; do
        local val="${rest%%|*}"; rest="${rest#*|}"
        local instance; instance="$(_ob_env_instance "$env_name")"
        printf "  %-8s  %-14s  %s\n" "${env_name}:" "$val" "${instance:+(${instance})}"
    done
    print ""
    _ob_dim "  Type: ${ktype}  |  Category: ${category}"

    local related="${rest%%|*}"; rest="${rest#*|}"
    local notes="${rest%%|*}"
    [[ -n "$related" && "$related" != "-" ]] && { print ""; _ob_yellow "  Related:"; printf "    %s\n" "${related//,/$'\n    '}"; }
    [[ -n "$notes" && "$notes" != "-" ]] && { print ""; _ob_dim "  Note: ${notes}"; }
    _ob_sep
}

_ob_env_list() {
    local filter="${1:l}"
    _ob_bold "Known Configuration Keys"
    _ob_sep
    printf "  %-24s  %-40s  %-14s\n" "Slug" "Key Path" "Category"
    _ob_sep
    while IFS= read -r k; do
        local data; data="$(_ob_get CONFIG_KEYS "$k")"
        local key_path="${data%%|*}"; local rest="${data#*|}"
        local ktype="${rest%%|*}"; rest="${rest#*|}"
        local category="${rest%%|*}"
        [[ -n "$filter" && "${category:l}" != *"$filter"* ]] && continue
        printf "  %-24s  %-40s  %-14s\n" "$k" "$key_path" "$category"
    done < <(_ob_keys CONFIG_KEYS 2>/dev/null)
    _ob_sep
}

_ob_env_diff() {
    local env1="${1:l}" env2="${2:l}"
    [[ -z "$env1" || -z "$env2" ]] && { _ob_red "Usage: ${OB_CLI_NAME:-ob} env diff <e1> <e2>"; return 1; }

    local -a env_names; env_names=("${(@s:;:)$(_ob_env_names)}")

    # Determine positional indices for the two environments
    local idx1=0 idx2=0 pos=0
    for en in "${env_names[@]}"; do
        (( pos++ ))
        [[ "$en" == "$env1" ]] && idx1=$pos
        [[ "$en" == "$env2" ]] && idx2=$pos
    done
    (( idx1 == 0 )) && { _ob_red "Unknown environment: ${env1}"; return 1; }
    (( idx2 == 0 )) && { _ob_red "Unknown environment: ${env2}"; return 1; }

    _ob_bold "Config Diff: ${env1} vs ${env2}"
    _ob_sep
    printf "  %-40s  %-14s  %s\n" "Key Path" "$env1" "$env2"
    _ob_sep

    local diff_count=0
    while IFS= read -r k; do
        local data; data="$(_ob_get CONFIG_KEYS "$k")"
        local key_path="${data%%|*}"; local rest="${data#*|}"
        rest="${rest#*|}"; rest="${rest#*|}"  # skip type, category

        # Extract values positionally
        local -a vals=()
        for en in "${env_names[@]}"; do
            vals+=("${rest%%|*}"); rest="${rest#*|}"
        done

        local v1="${vals[$idx1]}" v2="${vals[$idx2]}"
        if [[ "$v1" != "$v2" ]]; then
            (( diff_count++ ))
            printf "  %-40s  %-14s  %s\n" "$key_path" "$v1" "$v2"
        fi
    done < <(_ob_keys CONFIG_KEYS 2>/dev/null)

    (( diff_count == 0 )) && _ob_dim "  No differences found."
    _ob_sep
}