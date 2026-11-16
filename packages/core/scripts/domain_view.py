"""
domain_view.py — the one place where a tenant's domain.json (snake_case,
authoring format) becomes the public TenantDomain view (camelCase, the shape
declared in packages/shared/src/lib/types/tenant.types.ts).

Consumers
---------
* generate_adapters.py  → TypeScript snapshots in packages/shared (portal build)
* packages/api          → every /api/v1/tenants/{slug}/... response
* packages/admin-cli    → offline mode

Keeping one normalizer means the portal's build-time snapshot and the API's
runtime responses can never drift: both are `to_view(domain)`.

Rules
-----
* Collection *entry ids* are data and are never renamed
  (operation `schedule_mission`, status `0`, glossary `master_policy`).
* Field names inside entries are camelCased (`see_also` → `seeAlso`).
* Every collection the TS interface declares as required is present
  (empty `{}` when the tenant does not author it — e.g. generic has no queues).
* List fields always exist as lists, so clients can iterate without guards.

Stdlib only. Safe to import from anywhere (no repo-path side effects).
"""

from __future__ import annotations

import copy
from typing import Any

VIEW_VERSION = "1"

# domain.json collection key → view key. Collections are dict[id, entry].
REQUIRED_COLLECTIONS = {
    "operations": "operations",
    "statuses": "statuses",
    "products": "products",
    "portals": "portals",
    "queues": "queues",
    "glossary": "glossary",
    "scan_rules": "scanRules",
}
OPTIONAL_COLLECTIONS = {
    "status_triggers": "statusTriggers",
    "glossary_xrefs": "glossaryXrefs",
    "qe_tests": "qeTests",
    "clusters": "clusters",
    "config_keys": "configKeys",
    "sql_templates": "sqlTemplates",
    "capsules": "capsules",
}
# Top-level objects passed through with camelCased keys (one level).
OPTIONAL_OBJECTS = {
    "config": "config",
    "db_schema": "dbSchema",
    "ticket_config": "ticketConfig",
    "env_config": "envConfig",
    "trace_config": "traceConfig",
}

LIST_FIELDS = {
    "operations": ("controllers", "services", "queues", "js"),
    "scan_rules": ("scope", "repos", "exclude"),
    "glossary": ("see_also",),
    "portals": ("products",),
}
SCAN_RULE_DEFAULTS = {"reference": "", "fixHint": "", "category": "convention", "severity": "info"}


def camel(key: str) -> str:
    """snake_case → camelCase. Keys that are already camel are unchanged."""
    if "_" not in key:
        return key
    head, *rest = [p for p in key.split("_") if p]
    return head + "".join(p[:1].upper() + p[1:] for p in rest) if head else key


def _camel_keys(obj: Any) -> Any:
    """camelCase the keys of one dict level (values untouched)."""
    if not isinstance(obj, dict):
        return obj
    return {camel(k): v for k, v in obj.items()}


def _entry(collection: str, entry: Any) -> Any:
    if not isinstance(entry, dict):
        return entry                         # statuses, triggers, xrefs: plain strings
    out = dict(entry)
    for f in LIST_FIELDS.get(collection, ()):
        v = out.get(f)
        if v is None:
            out[f] = []
        elif isinstance(v, str):
            out[f] = [s for s in (x.strip() for x in v.replace(";", ",").split(",")) if s]
    out = _camel_keys(out)
    if collection == "scan_rules":
        if "fixhint" in out and "fixHint" not in out:       # tolerate odd casing
            out["fixHint"] = out.pop("fixhint")
        for k, d in SCAN_RULE_DEFAULTS.items():
            out.setdefault(k, d)
    return out


def _collection(domain: dict, src: str) -> dict:
    raw = domain.get(src) or {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): _entry(src, v) for k, v in raw.items()}


def to_view(domain: dict) -> dict:
    """Return the camelCase TenantDomain view of a parsed domain.json."""
    d = copy.deepcopy(domain)
    meta = d.get("tenant") or {}
    view: dict[str, Any] = {
        "viewVersion": VIEW_VERSION,
        "version": str(d.get("version", "0.0.0")),
        "tenant": {
            "slug": meta.get("slug", ""),
            "brandName": meta.get("brand_name") or meta.get("brandName") or meta.get("slug", ""),
            "cliName": meta.get("cli_name") or meta.get("cliName") or "ob",
            "terminology": dict(meta.get("terminology") or {}),
        },
    }
    for src, dst in REQUIRED_COLLECTIONS.items():
        view[dst] = _collection(d, src)
    for src, dst in OPTIONAL_COLLECTIONS.items():
        if d.get(src):
            view[dst] = _collection(d, src)
    for src, dst in OPTIONAL_OBJECTS.items():
        if isinstance(d.get(src), dict) and d[src]:
            view[dst] = _camel_keys(d[src])
    return view


def summary(domain: dict) -> dict:
    """Small per-tenant card: identity + collection counts (no payload)."""
    v = to_view(domain)
    return {
        "slug": v["tenant"]["slug"],
        "brandName": v["tenant"]["brandName"],
        "cliName": v["tenant"]["cliName"],
        "version": v["version"],
        "terminology": v["tenant"]["terminology"],
        "counts": {k: len(v[k]) for k in REQUIRED_COLLECTIONS.values()},
        "dialect": (v.get("dbSchema") or {}).get("dialect"),
        "database": (v.get("dbSchema") or {}).get("database"),
    }
