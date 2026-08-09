#!/usr/bin/env zsh
# ─────────────────────────────────────────────────────────────────────────────
# ob_nav_where_ext.zsh — Enhanced 'where' output extension  v4.0.0
#
# Extends ob_where() with two sections after its standard output:
#   1. Database Tables (write path) — from ${OB_NAV_SLUG}_OPS_TABLES
#   2. Known Failure Clusters — from ${OB_NAV_SLUG}_OPS_CLUSTERS → CLUSTERS
#
# Uses the wrapper pattern (same as ob_telemetry.zsh): captures the original
# ob_where body, renames it, replaces with wrapper + extension output.
#
# Tenant isolation:
#   Reads OPS_TABLES and OPS_CLUSTERS via _ob_get. These maps are populated
#   by the tenant's generated adapter (nav_maps_db.zsh). Engine code has no
#   knowledge of which tables or clusters exist for any tenant.
#
# Depends on: ob_nav_engine.zsh (ob_where), ob_core_loader.zsh (_ob_get)
# ─────────────────────────────────────────────────────────────────────────────
 
[[ -n "${_OB_NAV_WHERE_EXT_LOADED:-}" ]] && return 0
typeset -g _OB_NAV_WHERE_EXT_LOADED=1
 
if (( $+functions[ob_where] )); then
    # Save original
    functions[_ob_where_original]="${functions[ob_where]}"
 
    ob_where() {
        _ob_where_original "$@"
        local exit_code=$?
 
        local op="${1:l}"
        [[ -z "$op" ]] && return $exit_code
 
        # ── Database Tables section ──────────────────────────────────────
        local tables; tables="$(_ob_get OPS_TABLES "$op" 2>/dev/null)"
        if [[ -n "$tables" ]]; then
            print ""
            _ob_dim "  ── Database Tables (write path) ──"
            local IFS='|'
            for tbl in $tables; do
                printf "    %s\n" "$tbl"
            done
        fi
 
        # ── Known Failure Clusters section ───────────────────────────────
        local clusters; clusters="$(_ob_get OPS_CLUSTERS "$op" 2>/dev/null)"
        if [[ -n "$clusters" ]]; then
            print ""
            _ob_dim "  ── Known Failure Clusters ──"
            local IFS='|'
            for cluster_code in $clusters; do
                # Find label by scanning CLUSTERS entries for matching code
                local found=0
                while IFS= read -r ck; do
                    local c_data; c_data="$(_ob_get CLUSTERS "$ck")"
                    local c_rest="${c_data#*|}"
                    local c_code="${c_rest%%|*}"
                    if [[ "$c_code" == *"Cluster ${cluster_code}"* ]]; then
                        local c_label="${c_data%%|*}"
                        printf "    Cluster %s — %s\n" "$cluster_code" "${c_label:0:60}"
                        _ob_dim   "      ${OB_CLI_NAME:-ob} cluster '${ck}'"
                        found=1; break
                    fi
                done < <(_ob_keys CLUSTERS 2>/dev/null)
                (( found )) || printf "    Cluster %s\n" "$cluster_code"
            done
        fi
 
        [[ -n "${tables}${clusters}" ]] && _ob_sep
        return $exit_code
    }
fi

