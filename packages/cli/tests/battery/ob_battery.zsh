#!/usr/bin/env zsh
# ─────────────────────────────────────────────────────────────────────────────
# ob_battery.zsh — run every supported onboarded command against one tenant or
# instance, assert exit code + output, time each call, write a CSV.
#
#   zsh packages/cli/tests/battery/ob_battery.zsh [options]
#
#   --tenant SLUG    tenant/instance to test (default: active instance, else generic)
#   --db             include database checks (schema --exec, sql --exec)
#   --dba            include DBA engine checks (needs packages/dba venv + psycopg)
#   --instance       include ob-instance checks (doctor, check-paths) for SLUG
#   --max N          cap data-driven checks per map (default: all)
#   --out FILE       CSV path (default: $OB_WORKSPACE_DIR/runs/ or ./, battery-<slug>-<ts>.csv)
#   --quiet          only print FAIL rows and the summary
#
# Data-driven: every operation, status, glossary term, product, portal, queue,
# scan rule, cached table, SQL template, cluster and config key defined in the
# tenant is exercised, so the same script covers msi, generic and every new
# instance. Exit code = number of failures (capped at 125).
# ─────────────────────────────────────────────────────────────────────────────
emulate -R zsh
setopt extendedglob pipefail
zmodload zsh/datetime

typeset -g REPO="${0:A:h:h:h:h:h}"
typeset -g SLUG="" WANT_DB=0 WANT_DBA=0 WANT_INST=0 MAX=0 OUT="" QUIET=0
while (( $# )); do
    case "$1" in
        --tenant)   SLUG="$2"; shift 2 ;;
        --db)       WANT_DB=1; shift ;;
        --dba)      WANT_DBA=1; shift ;;
        --instance) WANT_INST=1; shift ;;
        --max)      MAX="$2"; shift 2 ;;
        --out)      OUT="$2"; shift 2 ;;
        --quiet)    QUIET=1; shift ;;
        -h|--help)  sed -n '2,22p' "$0"; exit 0 ;;
        *) print -u2 "unknown option: $1"; exit 2 ;;
    esac
done
[[ -z "$SLUG" && -f "$HOME/.onboarded/active" ]] && SLUG="$(<"$HOME/.onboarded/active")"
: "${SLUG:=generic}"

# Instance env first (repos, DB), then the tenant is pinned explicitly.
[[ -f "$HOME/.onboarded/instances/${SLUG}.env" ]] && source "$HOME/.onboarded/instances/${SLUG}.env"
export OB_TENANT="$SLUG" OB_NAV_SLUG="${SLUG:u}"
source "$REPO/packages/cli/src/ob_dispatcher.zsh" || { print -u2 "dispatcher failed to load"; exit 2; }

typeset -g TS="$(strftime '%Y%m%d-%H%M%S' $EPOCHSECONDS)"
if [[ -z "$OUT" ]]; then
    if [[ -n "${OB_WORKSPACE_DIR:-}" ]]; then mkdir -p "$OB_WORKSPACE_DIR/runs"; OUT="$OB_WORKSPACE_DIR/runs/battery-${SLUG}-${TS}.csv"
    else OUT="./battery-${SLUG}-${TS}.csv"; fi
fi
print -r -- "id,section,tenant,command,expect,rc,ms,result,note" > "$OUT"

typeset -gi PASS=0 FAIL=0 SKIP=0
typeset -ga TIMES
typeset -g SECTION=""
typeset -g SANDBOX_HOME="$(mktemp -d)"
trap 'rm -rf "$SANDBOX_HOME"' EXIT

_csv() { local s="${1//\"/\"\"}"; print -rn -- "\"$s\""; }
_row() {  # id cmd expect rc ms result note
    { _csv "$1"; print -n ,; _csv "$SECTION"; print -n ,; _csv "$SLUG"; print -n ,; _csv "$2"; print -n ,
      _csv "$3"; print -n ",$4,$5,"; _csv "$6"; print -n ,; _csv "$7"; print } >> "$OUT"
}
section() { SECTION="$1"; (( QUIET )) || print -P "\n%B── $1%b"; }

# check ID EXPECT PATTERN -- command...
#   EXPECT: 0 | !0 | any | <n>     PATTERN: extended regex on ANSI-stripped output ('' = none)
#   PATTERN starting with '!' must NOT match.
check() {
    local id="$1" expect="$2" pat="$3"; shift 3; [[ "$1" == "--" ]] && shift
    local t0=$EPOCHREALTIME out rc
    out="$( { "$@" } 2>&1 < /dev/null )"; rc=$?
    local ms=$(( (EPOCHREALTIME - t0) * 1000 )); ms=${ms%.*}
    out="${out//$'\e'\[[0-9;]#m/}"
    local ok=1 note=""
    case "$expect" in
        0)   (( rc == 0 )) || { ok=0; note="rc=$rc"; } ;;
        '!0') (( rc != 0 )) || { ok=0; note="expected non-zero"; } ;;
        any) ;;
        *)   (( rc == expect )) || { ok=0; note="rc=$rc want $expect"; } ;;
    esac
    if (( ok )) && [[ -n "$pat" ]]; then
        if [[ "$pat" == '!'* ]]; then
            print -r -- "$out" | grep -Eq -- "${pat#!}" && { ok=0; note="unexpected: ${pat#!}"; }
        else
            print -r -- "$out" | grep -Eq -- "$pat" || { ok=0; note="missing: $pat"; }
        fi
    fi
    TIMES+=("$ms")
    local cmd="${(j: :)${(q-)@}}"
    if (( ok )); then
        (( PASS++ )); _row "$id" "$cmd" "$expect" "$rc" "$ms" PASS ""
        (( QUIET )) || printf '  \e[32mPASS\e[0m %-14s %6sms  %s\n' "$id" "$ms" "$cmd"
    else
        (( FAIL++ )); _row "$id" "$cmd" "$expect" "$rc" "$ms" FAIL "$note"
        printf '  \e[31mFAIL\e[0m %-14s %6sms  %s  — %s\n' "$id" "$ms" "$cmd" "$note"
        print -r -- "$out" | head -8 | sed 's/^/         │ /'
    fi
}
skip() { (( SKIP++ )); _row "$1" "$2" "-" "-" 0 SKIP "$3"; (( QUIET )) || printf '  \e[33mSKIP\e[0m %-14s %s — %s\n' "$1" "$2" "$3"; }

keys() { local -a k; k=("${(@f)$(_ob_keys "$1" 2>/dev/null)}"); k=(${k:#}); (( MAX > 0 )) && k=(${k[1,MAX]}); print -rl -- $k; }
first_key() { _ob_keys "$1" 2>/dev/null | head -1; }

# ── 1. Dispatcher ────────────────────────────────────────────────────────────
section "Dispatcher"
check D01 0   'where'              -- onboarded help
check D02 0   'where'              -- onboarded
check D03 '!0' 'Unknown'           -- onboarded no-such-command
check D04 0   '.'                  -- onboarded list ops
check D05 0   '.'                  -- onboarded list rules

# ── 2. Navigation (data-driven) ──────────────────────────────────────────────
section "Navigation: where"
typeset -g HAVE_REPOS=0
[[ -n "${OB_ROOT:-}" && -d "${OB_ROOT}" ]] && (( $(ls -1 "$OB_ROOT" 2>/dev/null | wc -l) > 0 )) && HAVE_REPOS=1
check W00 '!0' 'Usage'             -- onboarded where
check W01 '!0' 'not found'         -- onboarded where __no_such_op__
local -i i=0
for op in ${(f)"$(keys OPS)"}; do
    (( i++ ))
    if (( HAVE_REPOS )); then
        check "W-$i" 0 '!not found on disk|repo not mapped' -- onboarded where "$op"
    else
        check "W-$i" 0 "$op" -- onboarded where "$op"
    fi
done
(( i == 0 )) && skip W-1 "onboarded where <op>" "tenant defines no operations"

section "Navigation: status / explain / product / portal / queue"
check S00 0 '.' -- onboarded status
check S01 '!0' 'not found' -- onboarded status 99999
i=0; for c in ${(f)"$(keys STATUS)"}; do (( i++ )); check "S-$i" 0 '.' -- onboarded status "$c"; done
check E01 '!0' 'not found' -- onboarded explain __nosuchterm__
i=0; for t in ${(f)"$(keys GLOSSARY)"}; do (( i++ )); check "E-$i" 0 '.' -- onboarded explain "$t"; done
(( i == 0 )) && skip E-1 "onboarded explain <term>" "no glossary"
check P00 any '' -- onboarded product
i=0; for p in ${(f)"$(keys PRODUCTS)"}; do (( i++ )); check "P-$i" 0 '.' -- onboarded product "$p"; done
(( i == 0 )) && skip P-1 "onboarded product <key>" "no products defined"
check T00 any '' -- onboarded portal
i=0; for p in ${(f)"$(keys PORTALS)"}; do (( i++ )); check "T-$i" 0 '.' -- onboarded portal "$p"; done
(( i == 0 )) && skip T-1 "onboarded portal <key>" "no portals defined"
check Q00 any '' -- onboarded queue
i=0; for q in ${(f)"$(keys QUEUES)"}; do (( i++ )); check "Q-$i" 0 '.' -- onboarded queue "$q"; done
(( i == 0 )) && skip Q-1 "onboarded queue <name>" "no queues defined"

section "Navigation: grep / cd / doctor"
check G00 '!0' 'Usage' -- onboarded grep
check C00 '!0' 'Usage' -- onboarded cd
check C01 '!0' 'not found' -- onboarded cd __no_such_repo__
if (( HAVE_REPOS )); then
    # grep for the basename of the first mapped controller; cd into the first repo.
    local first_op="$(first_key OPS)" val="" ctl="" base=""
    val="$(_ob_get OPS "$first_op")"; ctl="${${(@s:||:)val}[2]%%;*}"; base="${${ctl:t}%.*}"
    if [[ -n "$base" ]]; then check G01 0 "${ctl:t}" -- onboarded grep "$base"; else skip G01 "onboarded grep" "first op has no controller"; fi
    local rkey="$(first_key REPOS)" rpath="$(_ob_get REPOS "$(first_key REPOS)")"
    check C02 0 "^${rpath}\$" -- zsh -c "source '$REPO/packages/cli/src/ob_dispatcher.zsh'; onboarded cd '$rkey' && pwd"
    check X01 any '.' -- ob_doctor
else
    skip G01 "onboarded grep <pattern>" "no cloned repos (OB_ROOT)"
    skip C02 "onboarded cd <repo>" "no cloned repos (OB_ROOT)"
    skip X01 "ob_doctor" "no cloned repos (OB_ROOT)"
fi

# ── 3. Scanning ──────────────────────────────────────────────────────────────
section "Scanning"
typeset -g FIX="$REPO/packages/cli/tests/fixtures/scan_fixtures"
check R00 0 "$(first_key SCAN_RULES)" -- onboarded scan list
check R01 '!0' 'Usage' -- onboarded scan
check R02 '!0' 'not found' -- onboarded scan __no_such_rule__ "$FIX"
if _ob_keys SCAN_RULES | grep -qx hardcoded_secret; then
    check R03 '!0' 'finding|Finding|match' -- onboarded scan hardcoded_secret "$FIX/ViolationService.cs"
    check R04 0    'No findings'           -- onboarded scan hardcoded_secret "$FIX/PolicyService.clean.cs"
    check R05 '!0' ''                      -- onboarded scan hardcoded_secret "$FIX/TestData.violation.json"
fi
typeset -g SCAN_TARGET="$FIX"; (( HAVE_REPOS )) && SCAN_TARGET="$OB_ROOT"
i=0; for r in ${(f)"$(keys SCAN_RULES)"}; do (( i++ )); check "R-$i" any '' -- onboarded scan "$r" "$SCAN_TARGET"; done
check A01 any 'Audit' -- onboarded audit
check A02 any 'Secrets scan' -- onboarded secrets

# ── 4. Environment / capsules ────────────────────────────────────────────────
section "Environment and capsules"
check V00 0 'env list' -- onboarded env
check V01 0 '.' -- onboarded env list
i=0; for k in ${(f)"$(keys CONFIG_KEYS)"}; do (( i++ )); check "V-$i" 0 '.' -- onboarded env "$k"; done
local envs="$(_ob_get ENV_CONFIG env_names 2>/dev/null)"
if [[ "$envs" == *";"* ]]; then
    check V02 any '.' -- onboarded env diff "${envs%%;*}" "${envs##*;}"
else skip V02 "onboarded env diff" "fewer than two environments"; fi
check K00 any '' -- onboarded capsule list

# ── 5. Database layer (shell) ────────────────────────────────────────────────
section "Database layer"
check B00 0 '.' -- onboarded schema
check B01 0 'information_schema|sys\.columns' -- onboarded schema __probe__.__table__
i=0; for t in ${(f)"$(keys SCHEMA)"}; do (( i++ )); check "B-$i" 0 'Cached column profile' -- onboarded schema "$t"; done
check L00 0 '.' -- onboarded sql
check L01 '!0' 'Unknown template' -- onboarded sql __no_such_template__
i=0; for k in ${(f)"$(keys SQL_TEMPLATES)"}; do
    (( i++ )); local f="$(_ob_get SQL_TEMPLATES "$k")"; f="${f##*|}"
    if [[ -f "$(_ob_templates_dir)/$f" ]]; then check "L-$i" 0 'SQL:' -- onboarded sql "$k"
    else skip "L-$i" "onboarded sql $k" "template file $f missing"; fi
done
check U00 0 '.' -- onboarded cluster
check U01 '!0' 'No cluster match' -- onboarded cluster zzz no such error zzz
i=0; for k in ${(f)"$(keys CLUSTERS)"}; do (( i++ )); check "U-$i" 0 'CLUSTER MATCH' -- onboarded cluster "error: $k occurred"; done
check Y00 '!0' 'Usage' -- onboarded policy
check Y01 0 'Policy lookup|POLICY LOOKUP' -- onboarded policy ABC 123
if (( WANT_DB )); then
    if [[ -z "${OB_DB_NAME:-}" ]]; then skip B-DB "onboarded schema --exec" "OB_DB_NAME not set (activate an instance)"
    else
        local probe="$(first_key SCHEMA)"
        if [[ -z "$probe" ]]; then
            probe="$(PGHOST=${OB_DB_HOST:-localhost} PGPORT=${OB_DB_PORT:-5432} PGUSER=${OB_DB_USER:-$USER} PGDATABASE=$OB_DB_NAME \
                psql -X -Atc "select table_schema||'.'||table_name from information_schema.tables where table_schema not in ('pg_catalog','information_schema','err') order by 1 limit 1" 2>/dev/null)"
        fi
        if [[ -n "$probe" ]]; then check B-DB 0 '\([1-9][0-9]* rows?\)' -- onboarded schema "$probe" --exec
        else skip B-DB "onboarded schema --exec" "instance database has no tables yet"; fi
        if [[ -f "$(_ob_templates_dir)/schema_probe.sql" ]]; then
            check L-DB 0 'rows?\)' -- onboarded sql schema_probe err db_exception_tank --exec
        fi
    fi
fi

# ── 6. Ticket workflow (isolated HOME) ───────────────────────────────────────
section "Ticket workflow"
local tid=990001
check K01 0 'ticket' -- onboarded ticket
check K02 '!0' 'Invalid' -- onboarded ticket not-a-number
check K03 0 'Saved|unclassified|Cluster' -- env HOME="$SANDBOX_HOME" zsh -c "source '$REPO/packages/cli/src/ob_dispatcher.zsh'; onboarded ticket $tid </dev/null"
check K04 0 "$tid" -- env HOME="$SANDBOX_HOME" zsh -c "source '$REPO/packages/cli/src/ob_dispatcher.zsh'; onboarded ticket list"
check K05 0 '✔ .*fix\.sql|placeholder' -- env HOME="$SANDBOX_HOME" zsh -c "source '$REPO/packages/cli/src/ob_dispatcher.zsh'; onboarded ticket fix $tid"
check K06 0 '!placeholder' -- env HOME="$SANDBOX_HOME" zsh -c "source '$REPO/packages/cli/src/ob_dispatcher.zsh'; onboarded ticket fix $tid"
check K07 0 '' -- env HOME="$SANDBOX_HOME" zsh -c "source '$REPO/packages/cli/src/ob_dispatcher.zsh'; onboarded ticket close $tid"
if (( ${+functions[ob_trace]} )); then check K08 any '' -- onboarded trace
else skip K08 "onboarded trace" "ob_nav_trace.zsh not in repo (known gap)"; fi

# ── 7. DBA engine ────────────────────────────────────────────────────────────
if (( WANT_DBA )); then
    section "DBA engine"
    local stid=990002 tdir="$REPO/packages/core/tenants/$SLUG/scripts"
    check M01 0 '://'         -- onboarded dba config
    check M02 0 'version|[0-9]+\.[0-9]+' -- onboarded dba ping
    check M03 0 ''            -- onboarded dba tickets
    check M04 0 'Created'     -- onboarded dba scaffold $stid -t TARGET_TABLE=err.db_exception_tank --force
    check M05 0 "$SLUG:$stid" -- onboarded dba show $stid
    check M06 0 'rows'        -- onboarded dba run $stid diagnostic
    check M07 3 'destructive' -- onboarded dba run $stid fix
    check M08 0 'SANDBOX'     -- onboarded dba run $stid fix --yes --sandbox
    check M09 0 ''            -- onboarded dba run $stid dryrun
    check M10 2 'No ticket'   -- onboarded dba run 999999999 diagnostic
    check M11 0 ''            -- onboarded dba errors -n 5
    check M12 0 'csv'         -- onboarded dba run $stid diagnostic --csv "$SANDBOX_HOME/csv"
    # import a shell-generated package (uses the sandbox HOME from section 6)
    env HOME="$SANDBOX_HOME" zsh -c "source '$REPO/packages/cli/src/ob_dispatcher.zsh'; onboarded ticket 990003 </dev/null; onboarded ticket fix 990003" >/dev/null 2>&1
    check M13 0 'Imported'    -- env HOME="$SANDBOX_HOME" zsh -c "source '$REPO/packages/cli/src/ob_dispatcher.zsh'; onboarded dba import 990003 --force"
    check M14 0 "$SLUG:990003" -- onboarded dba show 990003
    rm -rf "$tdir/$stid" "$tdir/990003"
    if [[ "$SLUG" == generic ]]; then
        check M20 0 'P-1002'    -- onboarded dba run 1001 diagnostic
        check M21 0 'PASS'      -- onboarded dba run 1001 dryrun
        check M22 0 '!FAIL'     -- onboarded dba run 1001 dryrun
        check M23 0 'Verify OK' -- onboarded dba run 1001 fix --yes --sandbox
        check M24 0 'P-1002'    -- onboarded dba run 1001 diagnostic
    fi
    if [[ "$SLUG" == flotilla ]]; then      # Baseline v1 ticket (needs benchmarks/baseline-v1/seed loaded)
        check M30 0 'MR-STUCK-1' -- onboarded dba run 2001 diagnostic
        check M31 0 'PASS'       -- onboarded dba run 2001 dryrun
        check M32 0 '!FAIL'      -- onboarded dba run 2001 dryrun
        check M33 0 'Verify OK'  -- onboarded dba run 2001 fix --yes --sandbox
        check M34 0 'MR-STUCK-1' -- onboarded dba run 2001 diagnostic
    fi
fi

# ── 8. Instance tooling ──────────────────────────────────────────────────────
if (( WANT_INST )); then
    section "Instance tooling"
    local OBI=(python3 "$REPO/packages/core/scripts/ob_instance.py")
    check I01 0 "$SLUG"      -- $OBI list
    check I02 0 "\"slug\": \"$SLUG\"" -- $OBI show "$SLUG"
    check I03 0 'resolve'    -- $OBI check-paths "$SLUG"
    check I04 0 'healthy'    -- $OBI doctor "$SLUG"
    check I05 0 '\.env'      -- $OBI env "$SLUG"
fi

# ── Summary ──────────────────────────────────────────────────────────────────
local -a sorted; sorted=(${(on)TIMES})
local n=${#sorted} p50=0 p95=0 mx=0
(( n )) && { p50=${sorted[$(( (n + 1) / 2 ))]}; p95=${sorted[$(( (n * 95 + 99) / 100 ))]}; mx=${sorted[-1]}; }
print -P "\n%B── Summary: $SLUG%b"
printf '  pass %d · fail %d · skip %d · total %d\n' $PASS $FAIL $SKIP $(( PASS + FAIL + SKIP ))
printf '  timing ms: p50 %s · p95 %s · max %s\n' $p50 $p95 $mx
printf '  results: %s\n' "$OUT"
exit $(( FAIL > 125 ? 125 : FAIL ))
