#!/usr/bin/env zsh
# ─────────────────────────────────────────────────────────────────────────────
# ob_nav_ticket.zsh — Production support ticket workflow  v4.0.0
#
# Commands:
#   ob_ticket <id>          Start or resume a ticket investigation
#   ob_ticket fix <id>      Generate fix package scaffold from templates
#   ob_ticket list          List active ticket investigations
#   ob_ticket close <id>    Close an investigation
#
# Tenant isolation:
#   - Author identity: OB_AUTHOR_NAME, OB_AUTHOR_PARTY_ID, OB_AUTHOR_LOGIN
#   - Package conventions: read from ${OB_NAV_SLUG}_TICKET_CONFIG
#       submission_email   — where to send packages
#       package_files      — semicolon-delimited list of scaffold file basenames
#       scaffold_dir       — path to scaffold templates (templates/<slug>/scaffolds/)
#       ticket_dir_name    — what to call the output directory
#   - Fix/rollback SQL structure: tenant-specific scaffold .sql files in
#     templates/<slug>/scaffolds/ — the engine reads and token-fills them,
#     never generates SQL inline.
#
# Depends on: ob_nav_db.zsh (ob_cluster via _ob_get CLUSTERS)
# ─────────────────────────────────────────────────────────────────────────────

[[ -n "${_OB_NAV_TICKET_LOADED:-}" ]] && return 0
typeset -g _OB_NAV_TICKET_LOADED=1
 
# ── State directory ──────────────────────────────────────────────────────────
_ob_ticket_state_dir() { print "${HOME}/.onboarded/${OB_NAV_SLUG:l}/tickets"; }
_ob_ticket_path()      { print "$(_ob_ticket_state_dir)/${1}.json"; }
_ob_ticket_ensure()    { local d; d="$(_ob_ticket_state_dir)"; [[ -d "$d" ]] || mkdir -p "$d"; }
 
# ── Scaffold templates directory ─────────────────────────────────────────────
_ob_scaffold_dir() {
    local dir; dir="$(_ob_get TICKET_CONFIG scaffold_dir 2>/dev/null)"
    if [[ -n "$dir" ]]; then
        print "$dir"
    else
        print "${_OB_DB_CLI_ROOT}/templates/${OB_NAV_SLUG:l}/scaffolds"
    fi
}
 
# ── Minimal JSON field reader (no jq dependency) ─────────────────────────────
_ob_json_str()  { [[ -f "$1" ]] && grep -oP "\"${2}\"\s*:\s*\"[^\"]*\"" "$1" | head -1 | sed 's/.*: *"\(.*\)"/\1/'; }
_ob_json_int()  { [[ -f "$1" ]] && grep -oP "\"${2}\"\s*:\s*[0-9]+"     "$1" | head -1 | grep -oP '[0-9]+'; }
 
# ═══════════════════════════════════════════════════════════════════════════════
# ob_ticket — main entry point
# ═══════════════════════════════════════════════════════════════════════════════
ob_ticket() {
    local sub="${1:-}"
    case "$sub" in
        fix)    shift; _ob_ticket_fix "$@"; return $? ;;
        list)   _ob_ticket_list; return $? ;;
        close)  shift; _ob_ticket_close "$@"; return $? ;;
        "")     _ob_ticket_help; return 0 ;;
    esac
 
    [[ "$sub" =~ ^[0-9]+$ ]] || { _ob_red "Invalid: '${sub}'"; return 1; }
 
    local ticket_id="$sub"
    _ob_ticket_ensure
    local tfile; tfile="$(_ob_ticket_path "$ticket_id")"
 
    if [[ -f "$tfile" ]]; then
        _ob_ticket_resume "$ticket_id" "$tfile"
    else
        _ob_ticket_start "$ticket_id" "$tfile"
    fi
}
 
_ob_ticket_help() {
    _ob_bold "Production Support Ticket Workflow"
    _ob_sep
    printf "  %-42s  %s\n" "${OB_CLI_NAME:-ob} ticket <id>"        "Start/resume investigation"
    printf "  %-42s  %s\n" "${OB_CLI_NAME:-ob} ticket fix <id>"    "Generate fix package scaffold"
    printf "  %-42s  %s\n" "${OB_CLI_NAME:-ob} ticket list"        "List active investigations"
    printf "  %-42s  %s\n" "${OB_CLI_NAME:-ob} ticket close <id>"  "Close investigation"
    _ob_sep
}
 
# ── Start a new investigation ────────────────────────────────────────────────
_ob_ticket_start() {
    local ticket_id="$1" tfile="$2"
 
    cat > "$tfile" << TEOF
{ "id": ${ticket_id}, "cluster": "", "target_table": "", "status": "new", "classified": "" }
TEOF
 
    _ob_sep
    _ob_bold "  TICKET: ${ticket_id}  (new)"
    _ob_sep
    print ""
    _ob_cyan "  Step 1 — Classify the error"
    _ob_dim  "  Paste the exception message:"
    print -n "  > "
    local err_input; read -r err_input
 
    [[ -z "$err_input" ]] && { _ob_yellow "  Saved as unclassified."; _ob_sep; return 0; }
 
    _ob_ticket_classify "$ticket_id" "$err_input"
    _ob_sep
}
 
# ── Resume an existing investigation ─────────────────────────────────────────
_ob_ticket_resume() {
    local ticket_id="$1" tfile="$2"
    local status; status="$(_ob_json_str "$tfile" status)"
    local cluster; cluster="$(_ob_json_str "$tfile" cluster)"
 
    _ob_sep
    _ob_bold "  TICKET: ${ticket_id}  (resuming)"
    _ob_sep
    print ""
    printf "    %-18s  %s\n" "Status" "${status:-new}"
    printf "    %-18s  %s\n" "Cluster" "${cluster:-(not classified)}"
    print ""
 
    if [[ "$status" == "classified" && -n "$cluster" ]]; then
        _ob_cyan "  Next: run the diagnostic or generate the fix package"
        _ob_dim  "    ${OB_CLI_NAME:-ob} ticket fix ${ticket_id}"
    else
        _ob_cyan "  Step 1 — Classify the error"
        _ob_dim  "  Paste the exception message:"
        print -n "  > "
        local err_input; read -r err_input
        [[ -n "$err_input" ]] && _ob_ticket_classify "$ticket_id" "$err_input"
    fi
    _ob_sep
}
 
# ── Classify error and update state ──────────────────────────────────────────
_ob_ticket_classify() {
    local ticket_id="$1" err_input="$2"
    local tfile; tfile="$(_ob_ticket_path "$ticket_id")"
    local input="${(L)err_input}"
 
    local matched_key="" matched_data=""
    while IFS= read -r k; do
        if [[ "${input}" == *"${(L)k}"* ]]; then
            matched_key="$k"; matched_data="$(_ob_get CLUSTERS "$k")"; break
        fi
    done < <(_ob_keys CLUSTERS 2>/dev/null)
 
    if [[ -z "$matched_key" ]]; then
        _ob_yellow "  No cluster match. Manual classification needed."
        _ob_dim    "  Browse: ${OB_CLI_NAME:-ob} cluster"
        return 1
    fi
 
    local label="${matched_data%%|*}"; local rest="${matched_data#*|}"
    local code="${rest%%|*}";          rest="${rest#*|}"
    local table="${rest%%|*}";         rest="${rest#*|}"
    local fix="${rest%%|*}";           rest="${rest#*|}"
    local tmpl="${rest%%|*}"
 
    local now; now=$(date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date +"%Y-%m-%dT%H:%M:%SZ")
 
    cat > "$tfile" << TEOF
{ "id": ${ticket_id}, "cluster": "${code}", "target_table": "${table}", "fix_mechanism": "${fix}", "template": "${tmpl}", "status": "classified", "classified": "${now}" }
TEOF
 
    print ""
    _ob_green "  Classification: ${code}"
    _ob_cyan  "  ${label}"
    print ""
    printf "    %-18s  %s\n" "Target table" "$table"
    printf "    %-18s  %s\n" "Fix mechanism" "$fix"
    print ""
    _ob_cyan "  Next:"
    [[ -n "$tmpl" ]] && _ob_dim "    ${OB_CLI_NAME:-ob} sql ${tmpl} <id>"
    _ob_dim "    ${OB_CLI_NAME:-ob} ticket fix ${ticket_id}"
}
 
# ═══════════════════════════════════════════════════════════════════════════════
# _ob_ticket_fix — generate fix package from tenant scaffold templates
# ═══════════════════════════════════════════════════════════════════════════════
_ob_ticket_fix() {
    local ticket_id="$1"
    [[ -z "$ticket_id" ]] && { _ob_red "Usage: ${OB_CLI_NAME:-ob} ticket fix <id>"; return 1; }
 
    local tfile; tfile="$(_ob_ticket_path "$ticket_id")"
    [[ ! -f "$tfile" ]] && { _ob_red "No investigation for ${ticket_id}."; return 1; }
 
    local cluster; cluster="$(_ob_json_str "$tfile" cluster)"
    local table; table="$(_ob_json_str "$tfile" target_table)"
    local fix_mech; fix_mech="$(_ob_json_str "$tfile" fix_mechanism)"
 
    # Read tenant-configurable package settings
    local submission_email; submission_email="$(_ob_get TICKET_CONFIG submission_email 2>/dev/null)"
    local package_files_str; package_files_str="$(_ob_get TICKET_CONFIG package_files 2>/dev/null)"
    local author_name="${OB_AUTHOR_NAME:-Unknown}"
    local author_login="${OB_AUTHOR_LOGIN:-unknown@example.com}"
    local author_party_id="${OB_AUTHOR_PARTY_ID:-0}"
 
    : "${submission_email:=support@example.com}"
    : "${package_files_str:=README.md;diagnostic.sql;dryrun.sql;fix.sql;rollback.sql}"
 
    local scaffold_dir; scaffold_dir="$(_ob_scaffold_dir)"
    local outdir; outdir="$(_ob_ticket_state_dir)/${ticket_id}-package"
    mkdir -p "$outdir"
 
    # Token values available for scaffold substitution
    local -A tokens
    tokens=(
        [TICKET_ID]="$ticket_id"
        [CLUSTER]="${cluster:-TBD}"
        [TARGET_TABLE]="${table:-TBD}"
        [FIX_MECHANISM]="${fix_mech:-TBD}"
        [AUTHOR_NAME]="$author_name"
        [AUTHOR_LOGIN]="$author_login"
        [AUTHOR_PARTY_ID]="$author_party_id"
        [SUBMISSION_EMAIL]="$submission_email"
    )
 
    _ob_sep
    _ob_bold "  FIX PACKAGE: ${ticket_id}"
    _ob_sep
    print ""
 
    local IFS=';'
    local -a files=( $package_files_str )
    for f in "${files[@]}"; do
        [[ -z "$f" ]] && continue
 
        # Replace "dryrun.sql" → "dryrun-<ticket_id>.sql" if it contains "dryrun"
        local outname="$f"
        [[ "$f" == *"dryrun"* ]] && outname="${f%.sql}-${ticket_id}.sql"
 
        local scaffold_src="${scaffold_dir}/${f}"
        if [[ -f "$scaffold_src" ]]; then
            # Read scaffold template and substitute tokens
            local content; content=$(< "$scaffold_src")
            for tk tv in "${(@kv)tokens}"; do
                content="${content//\{\{${tk}\}\}/${tv}}"
            done
            printf '%s\n' "$content" > "${outdir}/${outname}"
            _ob_green "    ✔ ${outname}  (from scaffold)"
        else
            # Emit a minimal placeholder
            printf '# %s — %s (scaffold template not found)\n# Ticket: %s | Cluster: %s\n' \
                "$outname" "${OB_CLI_NAME:-ob}" "$ticket_id" "${cluster:-TBD}" \
                > "${outdir}/${outname}"
            _ob_yellow "    ○ ${outname}  (placeholder — no scaffold at ${scaffold_src})"
        fi
    done
 
    print ""
    _ob_cyan "  Output: ${outdir}"
    [[ -n "$submission_email" ]] && _ob_dim "  Submit to: ${submission_email}"
    _ob_sep
}
 
# ═══════════════════════════════════════════════════════════════════════════════
# _ob_ticket_list / _ob_ticket_close
# ═══════════════════════════════════════════════════════════════════════════════
_ob_ticket_list() {
    _ob_ticket_ensure
    local state_dir; state_dir="$(_ob_ticket_state_dir)"
    local -a files=("${state_dir}"/*.json(N))
 
    (( ${#files} == 0 )) && { _ob_dim "No active investigations."; return 0; }
 
    _ob_bold "Active Ticket Investigations"
    _ob_sep
    printf "  %-12s  %-18s  %-12s  %s\n" "ID" "Cluster" "Status" "Classified"
    _ob_sep
    for f in "${files[@]}"; do
        printf "  %-12s  %-18s  %-12s  %s\n" \
            "$(_ob_json_int "$f" id)" \
            "$(_ob_json_str "$f" cluster)" \
            "$(_ob_json_str "$f" status)" \
            "$(_ob_json_str "$f" classified)"
    done
    _ob_sep
}
 
_ob_ticket_close() {
    local ticket_id="$1"
    [[ -z "$ticket_id" ]] && { _ob_red "Usage: ${OB_CLI_NAME:-ob} ticket close <id>"; return 1; }
 
    local tfile; tfile="$(_ob_ticket_path "$ticket_id")"
    [[ ! -f "$tfile" ]] && { _ob_red "No investigation for ${ticket_id}."; return 1; }
 
    local closed_dir; closed_dir="$(_ob_ticket_state_dir)/closed"
    mkdir -p "$closed_dir"
    mv "$tfile" "${closed_dir}/${ticket_id}.json"
    _ob_green "  Ticket ${ticket_id} closed."
}