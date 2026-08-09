# msi-nav v4.0.0 — Benchmark (Tenant-Correct)

**Author:** michael.lowenstein@msimga.com
**Date:** 2026-08-02
**Baseline:** v3.0.0

---

## Directory Tree — v4.0.0

```
packages/cli/
├── src/
│   ├── ob_dispatcher.zsh                    (MODIFIED — 8 new case entries)
│   ├── core/
│   │   ├── ob_core_display.zsh              (unchanged)
│   │   └── ob_core_loader.zsh               (unchanged)
│   ├── nav/
│   │   ├── ob_nav_engine.zsh                (unchanged — where extended via wrapper)
│   │   ├── ob_nav_db.zsh                    (NEW — schema, sql, cluster, policy)
│   │   ├── ob_nav_where_ext.zsh             (NEW — tables + clusters in where)
│   │   ├── ob_nav_ticket.zsh                (NEW — ticket workflow orchestrator)
│   │   ├── ob_nav_trace.zsh                 (NEW — exception chain parser)
│   │   ├── ob_nav_env.zsh                   (NEW — config key lookup)
│   │   └── ob_nav_capsule.zsh               (NEW — capsule management)
│   └── scan/
│       └── ob_scan_engine.zsh               (unchanged)
├── generated/
│   ├── msi/
│   │   ├── nav_maps.zsh                     (unchanged — existing v3 maps)
│   │   └── nav_maps_db.zsh                  (NEW — 12 MSI-prefixed maps)
│   └── generic/
│       ├── nav_maps.zsh                     (unchanged)
│       └── nav_maps_db.zsh                  (NEW — skeleton for tenant proof)
├── templates/
│   ├── msi/
│   │   ├── schema_q0.sql                    (diagnostic template)
│   │   ├── cluster_c_diag.sql               (diagnostic template)
│   │   ├── cluster_a_variant_c_diag.sql     (diagnostic template)
│   │   ├── cluster_a_dedup.sql              (diagnostic template)
│   │   ├── policy_q1.sql                    (diagnostic template)
│   │   └── scaffolds/
│   │       ├── README.md                    (Phalanx scaffold)
│   │       ├── diagnostic.sql               (Phalanx scaffold)
│   │       ├── dryrun.sql                   (Phalanx scaffold)
│   │       ├── fix.sql                      (Phalanx scaffold)
│   │       └── rollback.sql                 (Phalanx scaffold)
│   └── generic/
│       └── scaffolds/                       (empty — awaits generic tenant)
└── tickets/                                 (~/.onboarded/<slug>/tickets/ at runtime)
```

---

## Tenant Isolation Audit

**v1 (previous attempt) violations → v2 (this attempt) corrections:**

| Violation | v1 | v2 |
|---|---|---|
| Map names in engine | `MSI_SCHEMA` hardcoded | `_ob_get SCHEMA "$key"` |
| Phalanx SQL in engine | `ERR.DB_EXCEPTION_TANK` hardcoded | Scaffold .sql files in `templates/msi/scaffolds/` |
| Author identity in engine | `1779900450` hardcoded | `OB_AUTHOR_PARTY_ID` env var |
| Policy decomposition in engine | `PWB` regex hardcoded | `POLICY_CONFIG` map (prefix_column, decompose_regex) |
| Data declared in engine | `MSI_OPS_TABLES` in where_ext.zsh | `_ob_get OPS_TABLES "$op"` → populated by adapter |
| Exception delimiter in engine | `--->` hardcoded | `TRACE_CONFIG[delimiter]` |
| Env instance names in engine | `msi-core-dev` hardcoded | `ENV_CONFIG[env_dev_instance]` |
| Capsule root in engine | `~/develop/work/msi/MsiCatProxy` hardcoded | `CAPSULE_CONFIG[root_dir]` + `root_env_var` |

**Test:** The generic tenant adapter (`generated/generic/nav_maps_db.zsh`) populates
all 12 map suffixes with empty/default values. Every engine module functions with
generic data — it just has nothing to display. No MSI-specific code path is triggered
by any engine module, because no MSI-specific code path exists.

---

## New Map Suffixes (v4.0.0)

All accessed via `_ob_get SUFFIX key` and `_ob_keys SUFFIX`:

| Suffix | Purpose | MSI entries | Generic entries |
|---|---|---|---|
| SCHEMA | Column profiles | 6 tables | 0 |
| SQL_TEMPLATES | Template key → desc\|file | 7 | 1 |
| CLUSTERS | Error pattern → classification | 9 | 0 |
| OPS_TABLES | Operation → write-path tables | 7 | 0 |
| OPS_CLUSTERS | Operation → cluster codes | 5 | 0 |
| CONFIG_KEYS | Config key → per-env values | 6 | 0 |
| ENV_CONFIG | Environment metadata | 4 | 1 |
| CAPSULES | Capsule registry | 2 | 0 |
| CAPSULE_CONFIG | Proxy settings | 5 | 2 |
| TICKET_CONFIG | Fix package conventions | 3 | 2 |
| POLICY_CONFIG | Policy decomposition rules | 7 | 2 |
| TRACE_CONFIG | Exception parsing settings | 2 | 2 |

---

## What Changed from v1 (Previous Attempt)

1. **Engine code references zero tenant-specific constants.** Every `MSI_*` reference
   was replaced with `_ob_get SUFFIX key`. The engine modules can be loaded against
   any tenant that populates the same map suffixes.

2. **Phalanx scaffold SQL is now template-driven.** The ERR.DB_EXCEPTION_TANK pattern,
   the XACT_ABORT/XACT_STATE branching, the `AzureAD\` author format — all of these
   are MSI-specific conventions that now live in `templates/msi/scaffolds/`. A
   PostgreSQL tenant would have different scaffold files with different error-handling
   patterns.

3. **`ob_policy` reads decomposition rules from `POLICY_CONFIG`.** The regex, column
   names, table names, and active-flag column are all configurable. The engine
   constructs the SELECT dynamically from the config values.

4. **`ob_trace` reads the exception delimiter from `TRACE_CONFIG`.** A Java tenant
   could set `delimiter` to `Caused by:` instead of `--->`. The skip-types list
   is also tenant-configurable.

5. **`ob_env` reads environment names from `ENV_CONFIG`.** The engine doesn't
   know that environments are named dev/test/prod — it reads the list from
   `ENV_CONFIG[env_names]`. A tenant with staging/canary/prod would just
   populate different environment names.

---

## Key Takeaways

1. **The tenant boundary is the map, not the module.** Engine modules are generic.
   Generated adapters are tenant-specific. Templates are tenant-specific. The maps
   are the bridge between them. This is the same pattern as the existing nav/scan
   split — v4.0.0 extends it to the database, workflow, and environment layers.

2. **Scaffold templates are the tenant's voice.** The Phalanx 5-file format, the
   ERR.DB_EXCEPTION_TANK error logging, the `AzureAD\` author prefix — these are
   MSI business conventions, not engineering patterns. They live in template files
   that MSI owns and controls. The engine's job is to fill tokens and write files,
   not to encode business rules.

3. **Config-map-driven commands scale to N tenants.** Adding a second tenant
   requires populating 12 map suffixes (most can be empty) and creating a
   `templates/<slug>/` directory. No engine code changes. The generic adapter
   proves this by existing as a functional tenant with empty maps.

4. **The wrapper pattern avoids engine modification.** `ob_nav_where_ext.zsh`
   extends `ob_where` without modifying `ob_nav_engine.zsh`. This means the
   v3.0.0 engine is unchanged — no merge conflicts, no regression risk. The
   extension is a separate file that can be installed or removed independently.