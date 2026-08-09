#!/usr/bin/env zsh
# ─────────────────────────────────────────────────────────────────────────────
# generated/msi/nav_maps_db.zsh — MSI tenant data layer v4.0.0
#
# GENERATED — regenerate: python3 scripts/generate_adapters.py --tenant msi
# Source: data/msi/domain.json → schema, sql_templates, clusters,
#         config_keys, capsules, ticket_config, trace_config, policy_config
#
# All maps use MSI_ prefix. Engine code accesses via _ob_get/keys with the
# suffix only (e.g., _ob_get SCHEMA "policy.PolicyTermSnapshot").
# OB_NAV_SLUG=MSI resolves this to MSI_SCHEMA at runtime.
# ─────────────────────────────────────────────────────────────────────────────


# ══════════════════════════════════════════════════════════════════════════════
# MSI_SCHEMA — confirmed column profiles from live Q0 probes
# ══════════════════════════════════════════════════════════════════════════════
typeset -gA MSI_SCHEMA
MSI_SCHEMA=(
  [policy.PolicyTermSnapshot]="\
PolicyTermSnapshotID:int:0|PolicyTermID:int:0|PolicyTermSnapshotSequenceNumber:smallint:0|\
IsActivePolicyTermSnapshot:bit:0|PolicyStatusCode:tinyint:0|CreatedDate:smalldatetime:0|\
LastUpdateDate:smalldatetime:1|LastUpdateByPartyID:int:1|RecordLastModifiedBy:nvarchar:0"

  [customer.CustomerAddress]="\
CustomerAddressID:int:0|CustomerID:int:0|AddressLine1:nvarchar:1|AddressLine2:nvarchar:1|\
City:nvarchar:1|StateCode:nvarchar:1|ZipCode5:nvarchar:1|IsDeleted:bit:0|\
AddressTypeCode:tinyint:1|LastUpdateDate:smalldatetime:1|LastUpdateByPartyID:int:1"

  [policy.PolicyTermSnapshotCustomer]="\
PolicyTermSnapshotID:int:0|CustomerID:int:0|CustomerTypeCode:tinyint:0|IsDelayedPhysicalDelete:bit:1"

  [policy.PolicyTermSnapshotDeductible]="\
PolicyTermSnapshotDeductibleID:int:0|PolicyTermSnapshotID:int:0|DeductibleTypeCode:tinyint:0|\
DeductibleAmount:decimal:1|DeductiblePercent:decimal:1|IsActive:bit:0|\
CreatedDate:smalldatetime:0|LastUpdateDate:smalldatetime:1|LastUpdateByPartyID:int:1"

  [party.Party]="\
PartyID:int:0|PartyFullName:nvarchar:0|PartyTypeCode:tinyint:0|\
IsDeleted:bit:0|LastUpdateDate:smalldatetime:0|RecordLastModifiedBy:nvarchar:0"

  [party.PartyLogin]="\
PartyLoginID:int:0|PartyID:int:0|LoginName:nvarchar:0|LastLoginDate:smalldatetime:1|IsDeleted:bit:0"
)


# ══════════════════════════════════════════════════════════════════════════════
# MSI_SQL_TEMPLATES — named SQL templates
# Format: "description|filename.sql"
# ══════════════════════════════════════════════════════════════════════════════
typeset -gA MSI_SQL_TEMPLATES
MSI_SQL_TEMPLATES=(
  [cluster_a_diag]="Cluster A — mortgagees + PPPC + Variant C diagnosis|cluster_a_variant_c_diag.sql"
  [cluster_a_dedup]="Cluster A — ROW_NUMBER dedup for mortgagee CustomerIDs|cluster_a_dedup.sql"
  [cluster_c_diag]="Cluster C — snapshot flag scan for a PolicyTermID|cluster_c_diag.sql"
  [cluster_w_diag]="Cluster W — WindHail deductible presence check|cluster_w_diag.sql"
  [policy_q1]="Policy Q1 — terms + snapshots for PolicyPrefix + PolicyNumber|policy_q1.sql"
  [schema_q0]="Schema Q0 — sys.columns probe for any table|schema_q0.sql"
  [party_lookup]="Party lookup — PartyID + LoginName by name or email|party_lookup.sql"
)


# ══════════════════════════════════════════════════════════════════════════════
# MSI_CLUSTERS — error pattern → cluster classification
# Format: label|code|target_table|fix_mechanism|template_key|variant_check
# ══════════════════════════════════════════════════════════════════════════════
typeset -gA MSI_CLUSTERS
MSI_CLUSTERS=(
  ["mortgagee customer not found"]="\
Set as Payor guard throw — compound predicate mismatch|\
Cluster A / Variant C|customer.CustomerAddress|\
UPDATE AddressLine1 to correct non-truncated value|cluster_a_diag|\
Count PPPC rows: 0=Variant A, 2+=Variant B, 1=Variant C."

  ["sequence contains no matching element"]="\
LINQ .Single(predicate) — collection loaded, predicate finds nothing|\
Cluster A (confirm variant)|customer.CustomerAddress OR policy.PolicyTermSnapshotCustomer|\
Depends on variant — run diagnostic first|cluster_a_diag|\
PPPC row count determines variant."

  ["sequence contains no elements"]="\
LINQ .Single() — collection EMPTY — active snapshot flag corrupt|\
Cluster C|policy.PolicyTermSnapshot|\
UPDATE IsActivePolicyTermSnapshot = 1 by PolicyTermSnapshotID|cluster_c_diag|\
Confirm ALL snapshots show IsActivePolicyTermSnapshot = 0."

  ["no payment processor"]="\
Missing Payment Processor Merchant ID for flood endorsement|\
Cluster B|billing.PaymentProcessorPaymentConfiguration|\
INSERT missing PPPC row via service layer (Sean Kimminau)|-|\
Financial writes must go through service layer, not direct SQL."

  ["missing windh"]="\
Missing WindHail deductible row — INSERT required|\
Cluster W|policy.PolicyTermSnapshotDeductible|\
INSERT missing WindHail deductible row|cluster_w_diag|\
Confirm DeductibleTypeCode from reference.DeductibleType before INSERT."

  ["nonpaycancelinprogress"]="\
Non-pay cancellation flag stuck|\
Cluster D|policy.PolicyTermSnapshot|\
UPDATE IsNonPayCancelInProgress = 0|cluster_c_diag|\
Confirm billing payment schedule before clearing the flag."

  ["collected premium"]="\
Billing/refund collected-premium mismatch|\
Cluster E|policy.PolicyTermPaymentAppliedDetail|\
Void duplicate via PolicyService.ProcessManualAdjustment|-|\
Financial corrections go through service layer."

  ["ineligible for coverage"]="\
Endorsement eligibility rule block — mortgagee count exceeds max|\
Cluster A / eligibility side-effect|policy.PolicyTermSnapshotCustomer|\
Remove orphan CustomerTypeCode=5 row via portal|cluster_a_diag|\
Count CustomerTypeCode=5 rows. Product max typically 2."

  ["invalid column"]="\
Msg 207 — column name does not exist|\
Schema mismatch|(table specified in query)|\
Run Q0 to confirm actual column name|schema_q0|\
Always run schema probe before referencing columns."
)


# ══════════════════════════════════════════════════════════════════════════════
# MSI_OPS_TABLES — operation → write-path tables (for where extension)
# Format: table1|table2|table3
# ══════════════════════════════════════════════════════════════════════════════
typeset -gA MSI_OPS_TABLES
MSI_OPS_TABLES=(
  [bind]="policy.PolicyTermSnapshot|policy.PolicyTerm|billing.PolicyPaymentMethod"
  [endorse]="policy.PolicyTermSnapshot|customer.CustomerAddress|customer.CustomerMortgage"
  [cancel]="policy.PolicyTermSnapshot"
  [renew]="policy.PolicyTermSnapshot|policy.PolicyTerm"
  [payment]="policy.PolicyTermPaymentAppliedDetail"
  [fnol]="claim.Claim|claim.ClaimCoverage"
  [quote]="policy.PolicyTermSnapshot|rating.RatingResult"
)


# ══════════════════════════════════════════════════════════════════════════════
# MSI_OPS_CLUSTERS — operation → known cluster codes (for where extension)
# ══════════════════════════════════════════════════════════════════════════════
typeset -gA MSI_OPS_CLUSTERS
MSI_OPS_CLUSTERS=(
  [bind]="C|W"
  [endorse]="A|B|C"
  [cancel]="D"
  [renew]="C|M"
  [payment]="E"
)


# ══════════════════════════════════════════════════════════════════════════════
# MSI_CONFIG_KEYS — environment configuration keys
# Format: key_path|type|category|dev_val|test_val|prod_val|related|notes
# ══════════════════════════════════════════════════════════════════════════════
typeset -gA MSI_CONFIG_KEYS
MSI_CONFIG_KEYS=(
  [otel_enabled]="OpenTelemetry:Enabled|bool|observability|true|true|false|\
OpenTelemetry:Traces:Enabled,OpenTelemetry:Traces:Exporter|Activation is a config change, not a rebuild."
  [gen3_routing]="MSI:Gen3:RoutingEnabled|bool|feature_flag|true|true|false|\
MSI:Gen3:FallbackToGen1|Full Gen3 routing; delegates back into AgencyCommonServices."
  [sentinel_core]="MSI:Sentinel:CoreKey|string|sentinel|sentinel-dev|sentinel-test|sentinel-prod|-|\
Sentinel key triggers config refresh."
  [conn_msi_admin]="ConnectionStrings:MSIAdmin|keyvault|connection|\
(KV: msi-admin-connection-string-dev)|(KV: msi-admin-connection-string-test)|\
(KV: msi-admin-connection-string-prod)|-|Always from Key Vault."
  [feature_flood_api]="MSI:Features:FloodApiV2|bool|feature_flag|true|true|false|\
MSI:Features:FloodApiV2:RolloutPercent|V2 Flood API carrier integration."
  [feature_portal_vue]="MSI:Features:PortalVueIslands|bool|feature_flag|true|false|false|-|\
Vue 3 island architecture for AdminPortal Razor views."
)


# ══════════════════════════════════════════════════════════════════════════════
# MSI_ENV_CONFIG — environment metadata
# ══════════════════════════════════════════════════════════════════════════════
typeset -gA MSI_ENV_CONFIG
MSI_ENV_CONFIG=(
  [env_names]="dev;test;prod"
  [env_dev_instance]="App Config: msi-core-dev"
  [env_test_instance]="App Config: msi-core-test"
  [env_prod_instance]="App Config: msi-core-prod"
)


# ══════════════════════════════════════════════════════════════════════════════
# MSI_CAPSULES — feature capsule registry
# Format: reference|route_prefix|migration_count|display_name
# ══════════════════════════════════════════════════════════════════════════════
typeset -gA MSI_CAPSULES
MSI_CAPSULES=(
  [snapshots]="ADO 103146|/demo/policy-shell|7|PolicyTermSnapshot Invariant Fix"
  [rating]="ADO 103194|/demo/rating-shell|2|Rating Reference Data Migration"
)


# ══════════════════════════════════════════════════════════════════════════════
# MSI_CAPSULE_CONFIG — MsiCatProxy dev environment settings
# ══════════════════════════════════════════════════════════════════════════════
typeset -gA MSI_CAPSULE_CONFIG
MSI_CAPSULE_CONFIG=(
  [root_env_var]="MSICATPROXY_ROOT"
  [root_dir]="${HOME}/develop/work/msi/MsiCatProxy"
  [port_env_var]="MSICATPROXY_PORT"
  [port]="5080"
  [swagger_path]="/swagger/v1/swagger.json"
  [host_project]="src/MsiCatProxy.Host"
)


# ══════════════════════════════════════════════════════════════════════════════
# MSI_TICKET_CONFIG — Phalanx submission conventions
# ══════════════════════════════════════════════════════════════════════════════
typeset -gA MSI_TICKET_CONFIG
MSI_TICKET_CONFIG=(
  [submission_email]="DatabasePhalanx@msimga.com"
  [package_files]="README.md;diagnostic.sql;dryrun.sql;fix.sql;rollback.sql"
  [scaffold_dir]="${_OB_DB_CLI_ROOT:-}/templates/msi/scaffolds"
)


# ══════════════════════════════════════════════════════════════════════════════
# MSI_POLICY_CONFIG — policy decomposition rules
# ══════════════════════════════════════════════════════════════════════════════
typeset -gA MSI_POLICY_CONFIG
MSI_POLICY_CONFIG=(
  [decompose_regex]="^([A-Z]+)([0-9]+)$"
  [prefix_column]="PolicyPrefix"
  [number_column]="PolicyNumber"
  [term_table]="policy.PolicyTerm"
  [snapshot_table]="policy.PolicyTermSnapshot"
  [snapshot_active_column]="IsActivePolicyTermSnapshot"
  [usage_hint]="<prefix> <number>  (e.g., PWB 1175340)"
)


# ══════════════════════════════════════════════════════════════════════════════
# MSI_TRACE_CONFIG — exception parsing settings
# ══════════════════════════════════════════════════════════════════════════════
typeset -gA MSI_TRACE_CONFIG
MSI_TRACE_CONFIG=(
  [delimiter]="--->"
  [skip_types]="TypeLoadException;ReflectionTypeLoadException;FileLoadException;FileNotFoundException"
)