# domain.json v4.0.0 Schema Extension

**Purpose:** Documents the new top-level sections in `domain.json` that
`generate_adapters.py` v4.0.0 reads to emit the DB extension maps.

All sections are optional. If absent, the generator emits empty maps and
the engine modules display "no data registered" messages gracefully.

---

## New sections (add to existing domain.json)

### `schema` — confirmed table column profiles

```json
"schema": {
  "policy.PolicyTermSnapshot": [
    { "name": "PolicyTermSnapshotID", "type": "int",          "nullable": false },
    { "name": "PolicyTermID",         "type": "int",          "nullable": false },
    { "name": "IsActivePolicyTermSnapshot", "type": "bit",    "nullable": false },
    { "name": "LastUpdateDate",       "type": "smalldatetime", "nullable": true }
  ]
}
```

### `sql_templates` — named SQL template files

```json
"sql_templates": {
  "cluster_c_diag": {
    "description": "Cluster C — snapshot flag scan for a PolicyTermID",
    "file": "cluster_c_diag.sql"
  },
  "schema_q0": {
    "description": "Schema Q0 — sys.columns probe for any table",
    "file": "schema_q0.sql"
  }
}
```

### `clusters` — error pattern classification

```json
"clusters": {
  "sequence contains no elements": {
    "label": "LINQ .Single() — collection EMPTY",
    "code": "Cluster C",
    "target_table": "policy.PolicyTermSnapshot",
    "fix_mechanism": "UPDATE IsActivePolicyTermSnapshot = 1",
    "template": "cluster_c_diag",
    "variant_check": "Confirm ALL snapshots show IsActivePolicyTermSnapshot = 0."
  }
}
```

### `operations` extensions (on existing entries)

```json
"operations": {
  "endorse": {
    "label": "...",
    "controllers": [...],
    "services": [...],
    "queues": [...],
    "js": [...],
    "tables": ["policy.PolicyTermSnapshot", "customer.CustomerAddress"],
    "clusters": ["A", "B", "C"]
  }
}
```

The `tables` and `clusters` fields are optional on each operation. When
present, they populate `{SLUG}_OPS_TABLES` and `{SLUG}_OPS_CLUSTERS`.

### `config_keys` — environment configuration

```json
"config_keys": {
  "otel_enabled": {
    "key": "OpenTelemetry:Enabled",
    "type": "bool",
    "category": "observability",
    "environments": {
      "dev": "true",
      "test": "true",
      "prod": "false"
    },
    "related": ["OpenTelemetry:Traces:Enabled"],
    "notes": "Activation is a config change, not a rebuild."
  }
}
```

### `env_config` — environment metadata

```json
"env_config": {
  "env_names": ["dev", "test", "prod"],
  "instances": {
    "dev": "App Config: msi-core-dev",
    "test": "App Config: msi-core-test",
    "prod": "App Config: msi-core-prod"
  }
}
```

### `capsules` — feature capsule registry

```json
"capsules": {
  "snapshots": {
    "reference": "ADO 103146",
    "route": "/demo/policy-shell",
    "migrations": 7,
    "display_name": "PolicyTermSnapshot Invariant Fix"
  }
}
```

### `capsule_config` — proxy settings (flat key-value)

```json
"capsule_config": {
  "root_env_var": "MSICATPROXY_ROOT",
  "root_dir": "~/develop/work/msi/MsiCatProxy",
  "port_env_var": "MSICATPROXY_PORT",
  "port": "5080",
  "swagger_path": "/swagger/v1/swagger.json",
  "host_project": "src/MsiCatProxy.Host"
}
```

### `ticket_config` — fix package conventions (flat key-value)

```json
"ticket_config": {
  "submission_email": "DatabasePhalanx@msimga.com",
  "package_files": "README.md;diagnostic.sql;dryrun.sql;fix.sql;rollback.sql",
  "scaffold_dir": "templates/msi/scaffolds"
}
```

### `policy_config` — policy decomposition rules (flat key-value)

```json
"policy_config": {
  "decompose_regex": "^([A-Z]+)([0-9]+)$",
  "prefix_column": "PolicyPrefix",
  "number_column": "PolicyNumber",
  "term_table": "policy.PolicyTerm",
  "snapshot_table": "policy.PolicyTermSnapshot",
  "snapshot_active_column": "IsActivePolicyTermSnapshot",
  "usage_hint": "<prefix> <number>  (e.g., PWB 1175340)"
}
```

### `trace_config` — exception parsing settings (flat key-value)

```json
"trace_config": {
  "delimiter": "--->",
  "skip_types": "TypeLoadException;ReflectionTypeLoadException;FileLoadException"
}
```

---

## Generator output

For each tenant that has any of the above sections, `generate_adapters.py`
emits two new files alongside the existing four:

```
generated/<tenant>/nav_maps_db.zsh     ← Zsh typeset -gA declarations
generated/<tenant>/nav_maps_db.ps1     ← PowerShell $global: declarations
```

The dispatcher sources `nav_maps_db.zsh` during bootstrap, after
`nav_maps.zsh` and before the engine modules.