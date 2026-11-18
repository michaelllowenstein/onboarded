#!/usr/bin/env zsh
# ─────────────────────────────────────────────────────────────────────────────
# generated/generic/nav_maps_db.zsh — Generic tenant data layer v4.0.0
#
# Skeleton adapter showing how a non-MSI tenant would populate the same
# map suffixes with different data. Proves the engine is tenant-agnostic.
#
# Hand-written (generate_adapters.py does not emit this file for generic).
# Entries are flat key/value appends, `NAME+=( "key" "value" )` — the form
# generate_adapters.py writes (see fix_zsh_assoc_keys). Not `NAME=( [key]=value )`,
# which older zsh and `zsh -n` reject ("bad subscript for direct array assignment"),
# and not `NAME["key"]=value`, which stores the quotes as part of the key.
# ─────────────────────────────────────────────────────────────────────────────

typeset -gA GENERIC_SCHEMA
GENERIC_SCHEMA=()  # No cached schemas for the generic tenant

typeset -gA GENERIC_SQL_TEMPLATES
GENERIC_SQL_TEMPLATES=()
GENERIC_SQL_TEMPLATES+=( "schema_probe" "Schema probe — column listing for any table|schema_probe.sql" )

typeset -gA GENERIC_CLUSTERS
GENERIC_CLUSTERS=()  # No error patterns registered

typeset -gA GENERIC_OPS_TABLES
GENERIC_OPS_TABLES=()

typeset -gA GENERIC_OPS_CLUSTERS
GENERIC_OPS_CLUSTERS=()

typeset -gA GENERIC_CONFIG_KEYS
GENERIC_CONFIG_KEYS=()

typeset -gA GENERIC_ENV_CONFIG
GENERIC_ENV_CONFIG=()
GENERIC_ENV_CONFIG+=( "env_names" "dev;staging;prod" )

typeset -gA GENERIC_CAPSULES
GENERIC_CAPSULES=()

typeset -gA GENERIC_CAPSULE_CONFIG
GENERIC_CAPSULE_CONFIG=()
GENERIC_CAPSULE_CONFIG+=( "root_dir" "${HOME}/capsule-proxy" )
GENERIC_CAPSULE_CONFIG+=( "port" "5080" )

typeset -gA GENERIC_TICKET_CONFIG
GENERIC_TICKET_CONFIG=()
GENERIC_TICKET_CONFIG+=( "submission_email" "" )
GENERIC_TICKET_CONFIG+=( "package_files" "README.md;diagnostic.sql;dryrun.sql;fix.sql;rollback.sql" )

typeset -gA GENERIC_POLICY_CONFIG
GENERIC_POLICY_CONFIG=()
GENERIC_POLICY_CONFIG+=( "decompose_regex" "^([A-Z]+)([0-9]+)$" )
GENERIC_POLICY_CONFIG+=( "usage_hint" "<identifier>" )

typeset -gA GENERIC_TRACE_CONFIG
GENERIC_TRACE_CONFIG=()
GENERIC_TRACE_CONFIG+=( "delimiter" "--->" )
GENERIC_TRACE_CONFIG+=( "skip_types" "TypeLoadException;ReflectionTypeLoadException" )
