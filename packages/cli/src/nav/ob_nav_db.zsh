#!/usr/bin/env zsh
# ─────────────────────────────────────────────────────────────────────────────
# ob_nav_db.zsh — Database investigation layer  v4.0.0
#
# Commands:
#   ob_schema <table>          Cached column profile + live schema probe
#   ob_sql <template> [args]   Filled SQL from a named template
#   ob_cluster <error>         Classify error → cluster code + triage path
#   ob_policy <identifier>     Policy lookup SQL pre-filled
#
# Tenant isolation:
#   All data access goes through _ob_get/_ob_keys with these suffixes:
#     SCHEMA          — confirmed table column profiles
#     SQL_TEMPLATES   — template key → description|filename
#     CLUSTERS        — error pattern → classification
#     POLICY_CONFIG   — policy decomposition rules (regex, columns, etc.)
#
#   SQL templates live in templates/${OB_NAV_SLUG:l}/*.sql
#   Token substitution uses {{TOKEN}} placeholders.
#   Clipboard: xclip (Linux/WSL), pbcopy (macOS), wl-copy (Wayland).
#
# Depends on: ob_core_display.zsh, ob_core_loader.zsh
# ─────────────────────────────────────────────────────────────────────────────

[[ -n "${_OB_NAV_DB_LOADED:-}" ]] && return 0
typeset -g _OB_NAV_DB_LOADED=1

# ── Resolve templates directory ──────────────────────────────────────────────
_OB_DB_CLI_ROOT="${${(%):-%x}:h:h:h}"
_ob_templates_dir() { print "${_OB_DB_CLI_ROOT}/templates/${OB_NAV_SLUG:l}"; }

# ── Private: clipboard copy ─────────────────────────────────────────────────
_ob_db_copy() {
    local content="$1"
    local copied=0
    if command -v xclip &>/dev/null; then
        printf '%s' "$content" | xclip -selection clipboard 2>/dev/null && copied=1
    elif command -v pbcopy &>/dev/null; then
        printf '%s' "$content" | pbcopy && copied=1
    elif command -v wl-copy &>/dev/null; then
        printf '%s' "$content" | wl-copy 2>/dev/null && copied=1
    fi
    (( copied )) && _ob_dim "  → Copied to clipboard." || _ob_dim "  → Install xclip/pbcopy for clipboard copy."
}

# ── Private: optional live execution ─────────────────────────────────────────
_ob_db_exec() {
    local sql="$1"
    local server="${OB_DB_READONLY_SERVER:-}"
    [[ -z "$server" ]] && { _ob_yellow "  Live execution disabled. Set OB_DB_READONLY_SERVER."; return 1; }
    command -v sqlcmd &>/dev/null || { _ob_yellow "  sqlcmd not in PATH."; return 1; }
    _ob_cyan "  Executing against ${server} ..."
    sqlcmd -S "$server" -d "${OB_DB_NAME:-MSI}" -G -Q "$sql"
}

# ── Private: token substitution ──────────────────────────────────────────────
_ob_db_fill_tokens() {
    local sql="$1"; shift
    local -a tokens
    tokens=( $(grep -oP '\{\{[A-Z_]+\}\}' <<< "$sql" | sed 's/[{}]//g' | awk '!seen[$0]++') )
    local i=1
    for tok in "${tokens[@]}"; do
        local val="${(P)${:-${i}}}"; [[ -z "$val" ]] && val="${argv[$i]:-}"
        [[ -n "$val" ]] && sql="${sql//\{\{${tok}\}\}/${val}}"
        (( i++ ))
    done
    printf '%s' "$sql"
}

# ═══════════════════════════════════════════════════════════════════════════════
# ob_schema — cached column profile + live probe
# ═══════════════════════════════════════════════════════════════════════════════
ob_schema() {
    local query="${1:l}"

    if [[ -z "$query" ]]; then
        _ob_bold "Cached Schema Profiles"
        _ob_sep
        while IFS= read -r k; do
            local v; v="$(_ob_get SCHEMA "$k")"
            local col_count="${#${(@s:|:)v}}"
            printf "  %-52s  %d confirmed columns\n" "$k" "$col_count"
        done < <(_ob_keys SCHEMA)
        _ob_sep
        _ob_dim "Usage: ${OB_CLI_NAME:-ob} schema <schema.Table>"
        return 0
    fi

    # Match: exact first, then case-insensitive substring
    local matched_key=""
    while IFS= read -r k; do
        [[ "${k:l}" == "${query}" ]] && { matched_key="$k"; break; }
    done < <(_ob_keys SCHEMA)
    if [[ -z "$matched_key" ]]; then
        while IFS= read -r k; do
            [[ "${k:l}" == *"${query}"* ]] && { matched_key="$k"; break; }
        done < <(_ob_keys SCHEMA)
    fi

    local target="${matched_key:-$1}"

    _ob_sep
    _ob_bold "  SCHEMA: ${target}"
    _ob_sep

    if [[ -n "$matched_key" ]]; then
        local col_data; col_data="$(_ob_get SCHEMA "$matched_key")"
        if [[ -n "$col_data" ]]; then
            _ob_yellow "  Cached column profile (confirmed from prior Q0):"
            print ""
            local col_id=0
            for col_entry in "${(@s:|:)col_data}"; do
                (( col_id++ ))
                local cname="${col_entry%%:*}"; local crest="${col_entry#*:}"
                local ctype="${crest%%:*}";     local cnull="${crest##*:}"
                local null_label; [[ "$cnull" == "1" ]] && null_label="NULL    " || null_label="NOT NULL"
                printf "    %3d  %-38s  %-16s  %s\n" "$col_id" "$cname" "$ctype" "$null_label"
            done
            print ""
        fi
    else
        _ob_yellow "  No cached profile for '${target}'."
        _ob_dim    "  Run the Q0 probe below, then update domain.json → schema."
        print ""
    fi

    # Live Q0 probe — always emitted
    local q0_sql
    read -r -d '' q0_sql << ENDSQL
SELECT
    c.column_id,
    c.name          AS ColumnName,
    t.name          AS TypeName,
    c.max_length,
    c.is_nullable
FROM   sys.columns c
JOIN   sys.types   t ON t.user_type_id = c.user_type_id
WHERE  c.object_id = OBJECT_ID(N'${target}')
ORDER  BY c.column_id;
ENDSQL

    _ob_yellow "  Live Q0 probe:"
    print ""
    while IFS= read -r line; do printf "    %s\n" "$line"; done <<< "$q0_sql"
    print ""
    _ob_db_copy "$q0_sql"
    [[ "${2:-}" == "--exec" || "${2:-}" == "-x" ]] && _ob_db_exec "$q0_sql"
    _ob_sep
}

# ═══════════════════════════════════════════════════════════════════════════════
# ob_cluster — classify error → cluster + triage path
# ═══════════════════════════════════════════════════════════════════════════════
ob_cluster() {
    local input="${(L)*}"

    if [[ -z "$input" ]]; then
        _ob_bold "Cluster Classification — Error Pattern Registry"
        _ob_sep
        while IFS= read -r k; do
            local data; data="$(_ob_get CLUSTERS "$k")"
            local label="${data%%|*}"; local rest="${data#*|}"
            local code="${rest%%|*}"
            printf "  %-46s  %s\n" "$k" "${code}"
        done < <(_ob_keys CLUSTERS)
        _ob_sep
        _ob_dim "Usage: ${OB_CLI_NAME:-ob} cluster <error message fragment>"
        return 0
    fi

    # Substring match — first match wins
    local matched_key="" matched_data=""
    while IFS= read -r k; do
        if [[ "${input}" == *"${(L)k}"* ]]; then
            matched_key="$k"; matched_data="$(_ob_get CLUSTERS "$k")"; break
        fi
    done < <(_ob_keys CLUSTERS)

    if [[ -z "$matched_key" ]]; then
        _ob_red "No cluster match for: '${*}'"
        _ob_dim "Run: ${OB_CLI_NAME:-ob} cluster  (no args) to browse."
        return 1
    fi

    # Parse: label|cluster_code|target_table|fix_mechanism|template_key|variant_check
    local label="${matched_data%%|*}";  local rest="${matched_data#*|}"
    local code="${rest%%|*}";           rest="${rest#*|}"
    local table="${rest%%|*}";          rest="${rest#*|}"
    local fix="${rest%%|*}";            rest="${rest#*|}"
    local tmpl="${rest%%|*}";           rest="${rest#*|}"
    local check="${rest%%|*}"

    _ob_sep
    _ob_bold "  CLUSTER MATCH"
    _ob_cyan  "  ${label}"
    _ob_sep
    print ""
    _ob_yellow "  Classification:"
    printf "    %-22s  %s\n" "Cluster" "$code"
    printf "    %-22s  %s\n" "Target table" "$table"
    printf "    %-22s  %s\n" "Fix mechanism" "$fix"
    print ""
    [[ -n "$check" ]] && { _ob_yellow "  Variant check:"; _ob_dim "    ${check}"; print ""; }
    if [[ -n "$tmpl" ]]; then
        _ob_yellow "  Diagnostic template:"
        printf "    %s sql %s <id>\n" "${OB_CLI_NAME:-ob}" "$tmpl"
    fi
    print ""
    _ob_sep
}

# ═══════════════════════════════════════════════════════════════════════════════
# ob_sql — emit filled SQL from a named template
# ═══════════════════════════════════════════════════════════════════════════════
ob_sql() {
    local key="$1"; shift 2>/dev/null

    if [[ -z "$key" ]]; then
        _ob_bold "SQL Template Library"
        _ob_sep
        local tmpl_dir; tmpl_dir="$(_ob_templates_dir)"
        while IFS= read -r k; do
            local data; data="$(_ob_get SQL_TEMPLATES "$k")"
            local desc="${data%%|*}" fname="${data##*|}"
            local marker="○"
            [[ -f "${tmpl_dir}/${fname}" ]] && marker="✔"
            printf "  %s %-42s  %s\n" "$marker" "$k" "$desc"
        done < <(_ob_keys SQL_TEMPLATES)
        _ob_sep
        _ob_dim "Usage: ${OB_CLI_NAME:-ob} sql <template> [arg1 ...] [--exec]"
        return 0
    fi

    local tmpl_data; tmpl_data="$(_ob_get SQL_TEMPLATES "$key")"
    [[ -z "$tmpl_data" ]] && { _ob_red "Unknown template: '${key}'"; return 1; }

    local desc="${tmpl_data%%|*}" fname="${tmpl_data##*|}"
    local tmpl_path="$(_ob_templates_dir)/${fname}"
    [[ ! -f "$tmpl_path" ]] && { _ob_red "Template file not found: ${tmpl_path}"; return 1; }

    local raw_sql exec_flag=""
    raw_sql=$(< "$tmpl_path")

    local -a clean_args=()
    for arg in "$@"; do
        [[ "$arg" == "--exec" || "$arg" == "-x" ]] && { exec_flag=1; continue; }
        clean_args+=("$arg")
    done

    local sql; sql="$(_ob_db_fill_tokens "$raw_sql" "${clean_args[@]}")"

    _ob_sep
    _ob_bold "  SQL: ${key}"
    _ob_cyan  "  ${desc}"
    _ob_sep
    print ""

    if [[ "$sql" == *"{{"* ]]; then
        _ob_yellow "  Unfilled tokens remain:"
        grep -oP '\{\{[A-Z_]+\}\}' <<< "$sql" | sort -u | while read -r tok; do _ob_dim "    ${tok}"; done
        print ""
    fi

    while IFS= read -r line; do printf "    %s\n" "$line"; done <<< "$sql"
    print ""
    _ob_db_copy "$sql"
    [[ -n "$exec_flag" ]] && _ob_db_exec "$sql"
    _ob_sep
}

# ═══════════════════════════════════════════════════════════════════════════════
# ob_policy — policy lookup SQL, tenant-configurable decomposition
# ═══════════════════════════════════════════════════════════════════════════════
ob_policy() {
    local arg1="${1:-}" arg2="${2:-}"

    if [[ -z "$arg1" ]]; then
        # Read tenant-specific usage hint from POLICY_CONFIG
        local hint; hint="$(_ob_get POLICY_CONFIG usage_hint 2>/dev/null)"
        _ob_red "Usage: ${OB_CLI_NAME:-ob} policy ${hint:-<identifier>}"
        return 1
    fi

    # Read decomposition pattern from tenant config
    local decompose_regex; decompose_regex="$(_ob_get POLICY_CONFIG decompose_regex 2>/dev/null)"
    local prefix_col; prefix_col="$(_ob_get POLICY_CONFIG prefix_column 2>/dev/null)"
    local number_col; number_col="$(_ob_get POLICY_CONFIG number_column 2>/dev/null)"
    local term_table; term_table="$(_ob_get POLICY_CONFIG term_table 2>/dev/null)"
    local snap_table; snap_table="$(_ob_get POLICY_CONFIG snapshot_table 2>/dev/null)"
    local snap_active_col; snap_active_col="$(_ob_get POLICY_CONFIG snapshot_active_column 2>/dev/null)"

    # Defaults for unconfigured tenants
    : "${decompose_regex:=^([A-Z]+)([0-9]+)$}"
    : "${prefix_col:=Prefix}"
    : "${number_col:=Number}"
    : "${term_table:=Term}"
    : "${snap_table:=Snapshot}"
    : "${snap_active_col:=IsActive}"

    local prefix="" number=""
    if [[ -n "$arg2" ]]; then
        prefix="${arg1:u}"; number="$arg2"
    elif [[ "${arg1:u}" =~ ${decompose_regex} ]]; then
        prefix="${match[1]}"; number="${match[2]}"
    else
        _ob_red "Could not parse identifier: '${arg1}'"
        return 1
    fi

    local sql
    read -r -d '' sql << ENDSQL
-- Policy lookup — ${prefix}${number}
SELECT
    pt.PolicyTermID,
    pt.${number_col},
    pt.${prefix_col},
    pt.TermNumber,
    pts.PolicyTermSnapshotID,
    pts.${snap_active_col},
    pts.PolicyTermSnapshotSequenceNumber,
    pts.PolicyStatusCode,
    pts.CreatedDate,
    pts.LastUpdateDate
FROM   ${term_table}  pt
JOIN   ${snap_table}  pts ON pts.PolicyTermID = pt.PolicyTermID
WHERE  pt.${prefix_col}  = N'${prefix}'
  AND  pt.${number_col}  = ${number}
ORDER  BY pt.TermNumber ASC, pts.PolicyTermSnapshotID DESC;
ENDSQL

    _ob_sep
    _ob_bold "  POLICY LOOKUP: ${prefix}${number}"
    _ob_sep
    print ""
    while IFS= read -r line; do printf "    %s\n" "$line"; done <<< "$sql"
    print ""
    _ob_db_copy "$sql"
    [[ "${3:-}" == "--exec" || "${3:-}" == "-x" ]] && _ob_db_exec "$sql"
    _ob_sep
}