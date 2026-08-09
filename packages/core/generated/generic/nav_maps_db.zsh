#!/usr/bin/env zsh
# ─────────────────────────────────────────────────────────────────────────────
# generated/generic/nav_maps_db.zsh — Generic tenant data layer v4.0.0
#
# Skeleton adapter showing how a non-MSI tenant would populate the same
# map suffixes with different data. Proves the engine is tenant-agnostic.
# ─────────────────────────────────────────────────────────────────────────────

typeset -gA GENERIC_SCHEMA
GENERIC_SCHEMA=()  # No cached schemas for the generic tenant

typeset -gA GENERIC_SQL_TEMPLATES
GENERIC_SQL_TEMPLATES=(
  [schema_probe]="Schema probe — column listing for any table|schema_probe.sql"
)

typeset -gA GENERIC_CLUSTERS
GENERIC_CLUSTERS=()  # No error patterns registered

typeset -gA GENERIC_OPS_TABLES
GENERIC_OPS_TABLES=()

typeset -gA GENERIC_OPS_CLUSTERS
GENERIC_OPS_CLUSTERS=()

typeset -gA GENERIC_CONFIG_KEYS
GENERIC_CONFIG_KEYS=()

typeset -gA GENERIC_ENV_CONFIG
GENERIC_ENV_CONFIG=( [env_names]="dev;staging;prod" )

typeset -gA GENERIC_CAPSULES
GENERIC_CAPSULES=()

typeset -gA GENERIC_CAPSULE_CONFIG
GENERIC_CAPSULE_CONFIG=( [root_dir]="${HOME}/capsule-proxy" [port]="5080" )

typeset -gA GENERIC_TICKET_CONFIG
GENERIC_TICKET_CONFIG=(
  [submission_email]=""
  [package_files]="README.md;diagnostic.sql;fix.sql;rollback.sql"
)

typeset -gA GENERIC_POLICY_CONFIG
GENERIC_POLICY_CONFIG=(
  [decompose_regex]="^([A-Z]+)([0-9]+)$"
  [usage_hint]="<identifier>"
)

typeset -gA GENERIC_TRACE_CONFIG
GENERIC_TRACE_CONFIG=(
  [delimiter]="--->"
  [skip_types]="TypeLoadException;ReflectionTypeLoadException"
)