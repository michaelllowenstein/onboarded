# @onboarded/api

REST API over the tenant domain, the scan engine and (from PR-10) DBA tickets.
FastAPI app, framework-free service layer under `src/onboarded_api/services/`.

## Run

```bash
cd packages/api
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[test]' -e '../dba[postgres]'
python -m onboarded_api --reload          # http://127.0.0.1:8000  · docs at /docs
```

Or from the repo root: `just api` (see justfile).

## Configuration (env)

| Variable | Default | Purpose |
|---|---|---|
| `OB_REPO_ROOT` | auto (dir with `nx.json`) | where tenants live |
| `OB_API_HOST` / `OB_API_PORT` | `127.0.0.1` / `8000` | bind |
| `OB_API_CORS_ORIGINS` | `http://localhost:4200` | portal origin(s), comma-separated |
| `OB_API_SCAN_ROOTS` | `$OB_WORKSPACE` + CLI fixtures | dirs `POST /scan` may read (`:`-separated) |
| `OB_API_DBA_EXEC` | off | `1` enables SQL execution endpoints |

## Endpoints

| Method | Path | Returns |
|---|---|---|
| GET | `/health` | status, loaded tenants, per-tenant load errors, feature flags |
| GET | `/api/v1/tenants` | `TenantSummary[]` |
| GET | `/api/v1/tenants/{slug}` | `TenantSummary` |
| GET | `/api/v1/tenants/{slug}/domain` | full camelCase `TenantDomain` (same object as the portal snapshot) |
| GET | `/api/v1/tenants/{slug}/operations[?q=]` · `/operations/{id}` | operations |
| GET | `/api/v1/tenants/{slug}/where/{key}` | exact-then-fuzzy lookup (≈ `ob where`) |
| GET | `/api/v1/tenants/{slug}/statuses[?q=]` · `/statuses/{code}` | status codes + triggers |
| GET | `/api/v1/tenants/{slug}/glossary[?q=]` · `/glossary/{term}` | glossary |
| GET | `/api/v1/tenants/{slug}/scan-rules[?severity=&category=]` | rules |
| GET | `/api/v1/tenants/{slug}/{products,portals,queues}` | id-keyed objects |
| POST | `/api/v1/tenants/{slug}/scan` | `ScanReport` — body `{content?, paths?, ruleIds?, minSeverity?}` |
| POST | `/api/v1/admin/reload` | re-read every `domain.json` |
| GET | `/api/v1/tenants/{slug}/tickets` · `/tickets/{id}` | DBA tickets (detail includes runbook) |
| GET | `/api/v1/tenants/{slug}/tickets/{id}/scripts/{name}` | script SQL |
| POST | `/api/v1/tenants/{slug}/tickets/{id}/scripts/{name}/run` | `RunResult` — body `{sandbox=true, maxRows, continueOnError}` |
| GET | `/api/v1/instances` · `/instances/{slug}` | instance manifests, active marker |

### Running SQL safely

* Off unless the server starts with `OB_API_DBA_EXEC=1` (`403` otherwise).
* `sandbox` defaults to **true** (Postgres: throwaway `TEMPLATE` clone; SQL Server: outer rollback).
* Destructive scripts (`fix*`, `rollback*`) need `X-Onboarded-Confirm: <ticket>/<script>` —
  an exact echo — or the API answers `428 Confirmation required` without touching the database.

Errors are always RFC 9457 `application/problem+json`: `{type, title, status, detail}`.

Scan `exitCode` (also the CLI's exit status): `0` clean · `1` critical · `2` error · `3` warning/info.

## Design notes

* **One view, two delivery paths.** `packages/core/scripts/domain_view.py:to_view()` turns
  snake_case `domain.json` into the camelCase shape in `packages/shared` `tenant.types.ts`.
  The generator uses it for the portal's build-time snapshot; the API uses it at runtime.
  `tests/test_services.py::test_api_view_equals_generated_ts_snapshot` fails if they drift.
* **Tenant in the path**, not a header: URLs are cacheable, curl-able and self-describing.
* **Scanning is sandboxed.** Inline `content` never touches disk; `paths` must resolve
  (after symlinks) inside `OB_API_SCAN_ROOTS`.

## Test

```bash
python -m pytest -q          # service suite always; HTTP suite when fastapi+httpx are installed
```
