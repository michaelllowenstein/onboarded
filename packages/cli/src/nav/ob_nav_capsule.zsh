#!/usr/bin/env zsh
# ─────────────────────────────────────────────────────────────────────────────
# ob_nav_capsule.zsh — Feature capsule integration  v4.0.0
#
# Commands:
#   ob_capsule list               List registered capsules
#   ob_capsule new <key> <ref>    Scaffold a new capsule
#   ob_capsule demo <key>         Emit demo commands for a capsule
#   ob_capsule start              Start the dev environment
#
# Tenant isolation:
#   - Capsule registry: ${OB_NAV_SLUG}_CAPSULES
#     Format: reference|route_prefix|migration_count|display_name
#   - Config: ${OB_NAV_SLUG}_CAPSULE_CONFIG
#     Keys: root_dir, root_env_var, port, port_env_var, swagger_path,
#           scaffold_feature_template, scaffold_controller_template
#   - Scaffolds: files in templates/<slug>/capsule_scaffolds/
#     Token-filled with {{KEY}}, {{PASCAL_KEY}}, {{REFERENCE}}, etc.
#
# Depends on: ob_core_loader.zsh
# ─────────────────────────────────────────────────────────────────────────────

[[ -n "${_OB_NAV_CAPSULE_LOADED:-}" ]] && return 0
typeset -g _OB_NAV_CAPSULE_LOADED=1

# ── Config accessors ─────────────────────────────────────────────────────────
_ob_capsule_root() {
    local env_var; env_var="$(_ob_get CAPSULE_CONFIG root_env_var 2>/dev/null)"
    [[ -n "$env_var" ]] && [[ -n "${(P)env_var:-}" ]] && { print "${(P)env_var}"; return; }
    local default; default="$(_ob_get CAPSULE_CONFIG root_dir 2>/dev/null)"
    print "${default:-${HOME}/capsule-proxy}"
}

_ob_capsule_port() {
    local env_var; env_var="$(_ob_get CAPSULE_CONFIG port_env_var 2>/dev/null)"
    [[ -n "$env_var" ]] && [[ -n "${(P)env_var:-}" ]] && { print "${(P)env_var}"; return; }
    local default; default="$(_ob_get CAPSULE_CONFIG port 2>/dev/null)"
    print "${default:-5080}"
}

# ═══════════════════════════════════════════════════════════════════════════════
ob_capsule() {
    local sub="${1:-}"; shift 2>/dev/null
    case "$sub" in
        list|l|"")  _ob_capsule_list ;;
        new|n)      _ob_capsule_new "$@" ;;
        demo|d)     _ob_capsule_demo "$@" ;;
        start)      _ob_capsule_start ;;
        *)          _ob_red "Unknown: '${sub}'"; return 1 ;;
    esac
}

_ob_capsule_list() {
    _ob_bold "Registered Feature Capsules"
    _ob_sep
    printf "  %-14s  %-12s  %-28s  %s\n" "Key" "Ref" "Route" "Migrations"
    _ob_sep

    while IFS= read -r k; do
        local data; data="$(_ob_get CAPSULES "$k")"
        local ref="${data%%|*}"; local rest="${data#*|}"
        local route="${rest%%|*}"; rest="${rest#*|}"
        local mig="${rest%%|*}"
        printf "  %-14s  %-12s  %-28s  %s\n" "$k" "$ref" "$route" "${mig} migrations"
    done < <(_ob_keys CAPSULES 2>/dev/null)

    _ob_sep
    local root; root="$(_ob_capsule_root)"
    [[ -d "$root" ]] && _ob_green "  Proxy root: ${root}" || _ob_dim "  Proxy not found: ${root}"
}

_ob_capsule_new() {
    local key="${1:l}" ref="$2"
    [[ -z "$key" || -z "$ref" ]] && { _ob_red "Usage: ${OB_CLI_NAME:-ob} capsule new <key> <reference>"; return 1; }

    local root; root="$(_ob_capsule_root)"
    [[ -d "$root" ]] || { _ob_red "Proxy root not found: ${root}"; return 1; }

    # PascalCase: mortgage → Mortgage, stuck_cancel → StuckCancel
    local pascal=""
    local IFS='_'
    for seg in $key; do pascal+="${(C)seg}"; done

    local scaffold_dir="${_OB_DB_CLI_ROOT}/templates/${OB_NAV_SLUG:l}/capsule_scaffolds"

    # Token values
    local -A tokens
    tokens=( [KEY]="$key" [PASCAL_KEY]="$pascal" [REFERENCE]="$ref" )

    _ob_sep
    _ob_bold "  CAPSULE SCAFFOLD: ${key} (${ref})"
    _ob_sep
    print ""

    # Process each scaffold file
    if [[ -d "$scaffold_dir" ]]; then
        for tmpl_file in "${scaffold_dir}"/*; do
            [[ -f "$tmpl_file" ]] || continue
            local tmpl_name="${tmpl_file:t}"
            # Replace KEY/PASCAL_KEY in filename itself
            local out_name="${tmpl_name//KEY/${key}}"
            out_name="${out_name//PASCAL/${pascal}}"

            # Determine output path based on file extension
            local out_dir="${root}/src/Features.${pascal}"
            [[ "$tmpl_name" == *migration* ]] && out_dir="${root}/src/Data/migrations/${key}"
            mkdir -p "$out_dir"

            local content; content=$(< "$tmpl_file")
            for tk tv in "${(@kv)tokens}"; do
                content="${content//\{\{${tk}\}\}/${tv}}"
            done
            printf '%s\n' "$content" > "${out_dir}/${out_name}"
            _ob_green "    ✔ ${out_name}"
        done
    else
        _ob_yellow "  No scaffold templates at: ${scaffold_dir}"
        _ob_dim    "  Create scaffold templates to enable code generation."
    fi

    print ""
    _ob_cyan "  Next: register in the feature registry, write migrations, build"
    _ob_sep
}

_ob_capsule_demo() {
    local key="${1:l}"
    [[ -z "$key" ]] && { _ob_red "Usage: ${OB_CLI_NAME:-ob} capsule demo <key>"; return 1; }

    local data; data="$(_ob_get CAPSULES "$key" 2>/dev/null)"
    [[ -z "$data" ]] && { _ob_red "Unknown capsule: '${key}'"; return 1; }

    local ref="${data%%|*}"
    local port; port="$(_ob_capsule_port)"
    local swagger_path; swagger_path="$(_ob_get CAPSULE_CONFIG swagger_path 2>/dev/null)"
    : "${swagger_path:=/swagger/v1/swagger.json}"

    _ob_sep
    _ob_bold "  DEMO: ${key} (${ref})"
    _ob_sep
    print ""

    # Try live Swagger
    local live=0
    if command -v curl &>/dev/null && command -v jq &>/dev/null; then
        local swagger_json
        swagger_json=$(curl -sf --max-time 2 "http://localhost:${port}${swagger_path}" 2>/dev/null)
        [[ $? -eq 0 && -n "$swagger_json" ]] && live=1

        if (( live )); then
            _ob_green "  Live routes from Swagger:"
            print ""
            echo "$swagger_json" | jq -r --arg key "$key" '
                .paths | to_entries[] |
                select(.key | contains("/demo/" + $key)) |
                .key as $path |
                .value | to_entries[] |
                "\(.key | ascii_upcase) \($path)"
            ' 2>/dev/null | while read -r method path; do
                printf "  curl -s"
                [[ "$method" != "GET" ]] && printf " -X %s" "$method"
                printf " localhost:%s%s" "$port" "$path"
                [[ "$method" == "POST" || "$method" == "PUT" ]] && \
                    printf " \\\\\n    -H 'Content-Type: application/json' -d '{}'"
                printf " | python3 -m json.tool\n\n"
            done
        fi
    fi

    if (( ! live )); then
        _ob_yellow "  Proxy offline — conventional endpoints:"
        print ""
        printf "  curl -s localhost:%s/api/demo/%s/health | python3 -m json.tool\n\n" "$port" "$key"
    fi

    _ob_sep
}

_ob_capsule_start() {
    local root; root="$(_ob_capsule_root)"
    [[ -d "$root" ]] || { _ob_red "Proxy not found: ${root}"; return 1; }
    local port; port="$(_ob_capsule_port)"

    _ob_cyan "Starting proxy..."
    (cd "$root" && docker compose up -d demo-sql 2>&1 | sed 's/^/    /')
    print ""
    (cd "$root" && \
        ASPNETCORE_URLS="http://0.0.0.0:${port}" \
        ASPNETCORE_ENVIRONMENT=Development \
        local proj; proj="$(_ob_get CAPSULE_CONFIG host_project 2>/dev/null)"
        dotnet run --project "${proj:-src/Host}" --no-launch-profile)
}