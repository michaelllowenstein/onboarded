#!/usr/bin/env python3
"""
patch_domain.py — Merge v4.0.0 sections into an existing domain.json

Usage (from scripts/):
    python patch_domain.py < ./domain.json > ./domain_ext.json

What it does:
    1. Bumps version to 4.0.0
    2. Adds tables/clusters fields to specified operations
    3. Adds 10 new top-level sections (schema, sql_templates, clusters, etc.)
    4. Preserves all existing content unchanged

Idempotent: running twice produces the same output.
"""

import json
import sys


def patch_msi_domain(domain: dict) -> dict:
    """Apply v4.0.0 patches to the MSI domain.json."""

    # 1. Bump version
    domain["version"] = "4.0.0"

    # 2. Patch operations with tables/clusters
    ops_tables = {
        "quote":   ["policy.PolicyTermSnapshot", "rating.RatingResult"],
        "bind":    ["policy.PolicyTermSnapshot", "policy.PolicyTerm", "billing.PolicyPaymentMethod"],
        "endorse": ["policy.PolicyTermSnapshot", "customer.CustomerAddress", "customer.CustomerMortgage"],
        "cancel":  ["policy.PolicyTermSnapshot"],
        "renew":   ["policy.PolicyTermSnapshot", "policy.PolicyTerm"],
        "payment": ["policy.PolicyTermPaymentAppliedDetail"],
        "fnol":    ["claim.Claim", "claim.ClaimCoverage"],
    }
    ops_clusters = {
        "bind":    ["C", "W"],
        "endorse": ["A", "B", "C"],
        "cancel":  ["D"],
        "renew":   ["C", "M"],
        "payment": ["E"],
    }

    for op_key, tables in ops_tables.items():
        if op_key in domain.get("operations", {}):
            domain["operations"][op_key]["tables"] = tables

    for op_key, clusters in ops_clusters.items():
        if op_key in domain.get("operations", {}):
            domain["operations"][op_key]["clusters"] = clusters

    # 3. Add new sections (only if not already present)

    if "schema" not in domain:
        domain["schema"] = {
            "policy.PolicyTermSnapshot": [
                {"name": "PolicyTermSnapshotID", "type": "int", "nullable": False},
                {"name": "PolicyTermID", "type": "int", "nullable": False},
                {"name": "PolicyTermSnapshotSequenceNumber", "type": "smallint", "nullable": False},
                {"name": "IsActivePolicyTermSnapshot", "type": "bit", "nullable": False},
                {"name": "PolicyStatusCode", "type": "tinyint", "nullable": False},
                {"name": "CreatedDate", "type": "smalldatetime", "nullable": False},
                {"name": "LastUpdateDate", "type": "smalldatetime", "nullable": True},
                {"name": "LastUpdateByPartyID", "type": "int", "nullable": True},
                {"name": "RecordLastModifiedBy", "type": "nvarchar", "nullable": False},
            ],
            "customer.CustomerAddress": [
                {"name": "CustomerAddressID", "type": "int", "nullable": False},
                {"name": "CustomerID", "type": "int", "nullable": False},
                {"name": "AddressLine1", "type": "nvarchar", "nullable": True},
                {"name": "AddressLine2", "type": "nvarchar", "nullable": True},
                {"name": "City", "type": "nvarchar", "nullable": True},
                {"name": "StateCode", "type": "nvarchar", "nullable": True},
                {"name": "ZipCode5", "type": "nvarchar", "nullable": True},
                {"name": "IsDeleted", "type": "bit", "nullable": False},
                {"name": "AddressTypeCode", "type": "tinyint", "nullable": True},
                {"name": "LastUpdateDate", "type": "smalldatetime", "nullable": True},
                {"name": "LastUpdateByPartyID", "type": "int", "nullable": True},
            ],
            "policy.PolicyTermSnapshotCustomer": [
                {"name": "PolicyTermSnapshotID", "type": "int", "nullable": False},
                {"name": "CustomerID", "type": "int", "nullable": False},
                {"name": "CustomerTypeCode", "type": "tinyint", "nullable": False},
                {"name": "IsDelayedPhysicalDelete", "type": "bit", "nullable": True},
            ],
            "policy.PolicyTermSnapshotDeductible": [
                {"name": "PolicyTermSnapshotDeductibleID", "type": "int", "nullable": False},
                {"name": "PolicyTermSnapshotID", "type": "int", "nullable": False},
                {"name": "DeductibleTypeCode", "type": "tinyint", "nullable": False},
                {"name": "DeductibleAmount", "type": "decimal", "nullable": True},
                {"name": "DeductiblePercent", "type": "decimal", "nullable": True},
                {"name": "IsActive", "type": "bit", "nullable": False},
                {"name": "CreatedDate", "type": "smalldatetime", "nullable": False},
                {"name": "LastUpdateDate", "type": "smalldatetime", "nullable": True},
                {"name": "LastUpdateByPartyID", "type": "int", "nullable": True},
            ],
            "party.Party": [
                {"name": "PartyID", "type": "int", "nullable": False},
                {"name": "PartyFullName", "type": "nvarchar", "nullable": False},
                {"name": "PartyTypeCode", "type": "tinyint", "nullable": False},
                {"name": "IsDeleted", "type": "bit", "nullable": False},
                {"name": "LastUpdateDate", "type": "smalldatetime", "nullable": False},
                {"name": "RecordLastModifiedBy", "type": "nvarchar", "nullable": False},
            ],
            "party.PartyLogin": [
                {"name": "PartyLoginID", "type": "int", "nullable": False},
                {"name": "PartyID", "type": "int", "nullable": False},
                {"name": "LoginName", "type": "nvarchar", "nullable": False},
                {"name": "LastLoginDate", "type": "smalldatetime", "nullable": True},
                {"name": "IsDeleted", "type": "bit", "nullable": False},
            ],
        }

    if "sql_templates" not in domain:
        domain["sql_templates"] = {
            "cluster_a_diag":  {"description": "Cluster A — mortgagees + PPPC + Variant C diagnosis", "file": "cluster_a_variant_c_diag.sql"},
            "cluster_a_dedup": {"description": "Cluster A — ROW_NUMBER dedup for mortgagee CustomerIDs", "file": "cluster_a_dedup.sql"},
            "cluster_c_diag":  {"description": "Cluster C — snapshot flag scan for a PolicyTermID", "file": "cluster_c_diag.sql"},
            "cluster_w_diag":  {"description": "Cluster W — WindHail deductible presence check", "file": "cluster_w_diag.sql"},
            "policy_q1":       {"description": "Policy Q1 — terms + snapshots for PolicyPrefix + PolicyNumber", "file": "policy_q1.sql"},
            "schema_q0":       {"description": "Schema Q0 — sys.columns probe for any table", "file": "schema_q0.sql"},
            "party_lookup":    {"description": "Party lookup — PartyID + LoginName by name or email", "file": "party_lookup.sql"},
        }

    if "clusters" not in domain:
        domain["clusters"] = {
            "mortgagee customer not found": {
                "label": "Set as Payor guard throw — compound predicate mismatch",
                "code": "Cluster A / Variant C", "target_table": "customer.CustomerAddress",
                "fix_mechanism": "UPDATE AddressLine1 to correct non-truncated value",
                "template": "cluster_a_diag",
                "variant_check": "Count PPPC rows: 0=Variant A, 2+=Variant B, 1=Variant C.",
            },
            "sequence contains no matching element": {
                "label": "LINQ .Single(predicate) — collection loaded, predicate finds nothing",
                "code": "Cluster A (confirm variant)", "target_table": "customer.CustomerAddress OR policy.PolicyTermSnapshotCustomer",
                "fix_mechanism": "Depends on variant — run diagnostic first",
                "template": "cluster_a_diag", "variant_check": "PPPC row count determines variant.",
            },
            "sequence contains no elements": {
                "label": "LINQ .Single() — collection EMPTY — active snapshot flag corrupt",
                "code": "Cluster C", "target_table": "policy.PolicyTermSnapshot",
                "fix_mechanism": "UPDATE IsActivePolicyTermSnapshot = 1 by PolicyTermSnapshotID",
                "template": "cluster_c_diag",
                "variant_check": "Confirm ALL snapshots show IsActivePolicyTermSnapshot = 0.",
            },
            "no payment processor": {
                "label": "Missing Payment Processor Merchant ID for flood endorsement",
                "code": "Cluster B", "target_table": "billing.PaymentProcessorPaymentConfiguration",
                "fix_mechanism": "INSERT missing PPPC row via service layer (Sean Kimminau)",
                "template": "", "variant_check": "Financial writes must go through service layer.",
            },
            "missing windh": {
                "label": "Missing WindHail deductible row — INSERT required",
                "code": "Cluster W", "target_table": "policy.PolicyTermSnapshotDeductible",
                "fix_mechanism": "INSERT missing WindHail deductible row",
                "template": "cluster_w_diag",
                "variant_check": "Confirm DeductibleTypeCode from reference.DeductibleType.",
            },
            "nonpaycancelinprogress": {
                "label": "Non-pay cancellation flag stuck",
                "code": "Cluster D", "target_table": "policy.PolicyTermSnapshot",
                "fix_mechanism": "UPDATE IsNonPayCancelInProgress = 0",
                "template": "cluster_c_diag",
                "variant_check": "Confirm billing payment schedule before clearing.",
            },
            "collected premium": {
                "label": "Billing/refund collected-premium mismatch",
                "code": "Cluster E", "target_table": "policy.PolicyTermPaymentAppliedDetail",
                "fix_mechanism": "Void duplicate via PolicyService.ProcessManualAdjustment",
                "template": "", "variant_check": "Financial corrections go through service layer.",
            },
            "ineligible for coverage": {
                "label": "Endorsement eligibility rule block — mortgagee count exceeds max",
                "code": "Cluster A / eligibility side-effect", "target_table": "policy.PolicyTermSnapshotCustomer",
                "fix_mechanism": "Remove orphan CustomerTypeCode=5 row via portal",
                "template": "cluster_a_diag",
                "variant_check": "Count CustomerTypeCode=5 rows. Product max typically 2.",
            },
            "invalid column": {
                "label": "Msg 207 — column name does not exist",
                "code": "Schema mismatch", "target_table": "(table specified in query)",
                "fix_mechanism": "Run Q0 to confirm actual column name",
                "template": "schema_q0",
                "variant_check": "Always run schema probe before referencing columns.",
            },
        }

    if "config_keys" not in domain:
        domain["config_keys"] = {
            "otel_enabled": {"key": "OpenTelemetry:Enabled", "type": "bool", "category": "observability", "environments": {"dev": "true", "test": "true", "prod": "false"}, "related": ["OpenTelemetry:Traces:Enabled", "OpenTelemetry:Traces:Exporter", "OpenTelemetry:Traces:SamplerRatio"], "notes": "Activation is a config change, not a rebuild."},
            "gen3_routing": {"key": "MSI:Gen3:RoutingEnabled", "type": "bool", "category": "feature_flag", "environments": {"dev": "true", "test": "true", "prod": "false"}, "related": ["MSI:Gen3:FallbackToGen1"], "notes": "Full Gen3 routing; delegates back into AgencyCommonServices."},
            "sentinel_core": {"key": "MSI:Sentinel:CoreKey", "type": "string", "category": "sentinel", "environments": {"dev": "sentinel-dev", "test": "sentinel-test", "prod": "sentinel-prod"}, "related": [], "notes": "Sentinel key triggers config refresh."},
            "conn_msi_admin": {"key": "ConnectionStrings:MSIAdmin", "type": "keyvault", "category": "connection", "environments": {"dev": "(KV: msi-admin-connection-string-dev)", "test": "(KV: msi-admin-connection-string-test)", "prod": "(KV: msi-admin-connection-string-prod)"}, "related": [], "notes": "Always from Key Vault."},
            "feature_flood_api": {"key": "MSI:Features:FloodApiV2", "type": "bool", "category": "feature_flag", "environments": {"dev": "true", "test": "true", "prod": "false"}, "related": ["MSI:Features:FloodApiV2:RolloutPercent"], "notes": "V2 Flood API carrier integration."},
            "feature_portal_vue": {"key": "MSI:Features:PortalVueIslands", "type": "bool", "category": "feature_flag", "environments": {"dev": "true", "test": "false", "prod": "false"}, "related": [], "notes": "Vue 3 island architecture for AdminPortal Razor views."},
        }

    if "env_config" not in domain:
        domain["env_config"] = {"env_names": ["dev", "test", "prod"], "instances": {"dev": "App Config: msi-core-dev", "test": "App Config: msi-core-test", "prod": "App Config: msi-core-prod"}}

    if "capsules" not in domain:
        domain["capsules"] = {
            "snapshots": {"reference": "ADO 103146", "route": "/demo/policy-shell", "migrations": 7, "display_name": "PolicyTermSnapshot Invariant Fix"},
            "rating": {"reference": "ADO 103194", "route": "/demo/rating-shell", "migrations": 2, "display_name": "Rating Reference Data Migration"},
        }

    if "capsule_config" not in domain:
        domain["capsule_config"] = {"root_env_var": "MSICATPROXY_ROOT", "root_dir": "~/develop/work/msi/MsiCatProxy", "port_env_var": "MSICATPROXY_PORT", "port": "5080", "swagger_path": "/swagger/v1/swagger.json", "host_project": "src/MsiCatProxy.Host"}

    if "ticket_config" not in domain:
        domain["ticket_config"] = {"submission_email": "DatabasePhalanx@msimga.com", "package_files": "README.md;diagnostic.sql;dryrun.sql;fix.sql;rollback.sql", "scaffold_dir": "templates/msi/scaffolds"}

    if "policy_config" not in domain:
        domain["policy_config"] = {"decompose_regex": "^([A-Z]+)([0-9]+)$", "prefix_column": "PolicyPrefix", "number_column": "PolicyNumber", "term_table": "policy.PolicyTerm", "snapshot_table": "policy.PolicyTermSnapshot", "snapshot_active_column": "IsActivePolicyTermSnapshot", "usage_hint": "<prefix> <number>  (e.g., PWB 1175340)"}

    if "trace_config" not in domain:
        domain["trace_config"] = {"delimiter": "--->", "skip_types": "TypeLoadException;ReflectionTypeLoadException;FileLoadException;FileNotFoundException"}

    return domain


if __name__ == "__main__":
    domain = json.load(sys.stdin)
    patched = patch_msi_domain(domain)
    json.dump(patched, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")