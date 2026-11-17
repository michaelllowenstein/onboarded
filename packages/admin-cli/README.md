# @onboarded/admin-cli

One CLI, two backends, same answers:

* **API mode** (default when the API answers `/health`): stdlib HTTP client for `packages/api`.
* **Local mode** (`--local`, or automatic fallback when no API is running): reads the repo
  directly through the API's own service layer. No server needed.

`--api URL` / `$OB_API_URL` force API mode and never fall back silently.

## Install

```bash
pip install -e packages/admin-cli                       # API mode only (stdlib)
pip install -e packages/admin-cli -e packages/api -e 'packages/dba[postgres]'   # + local mode
ob-admin --help
```

Without installing: `just admin <args>` from the repo root.

## Commands

```bash
ob-admin health                       # API/tenant health
ob-admin tenants                      # loaded tenants + counts
ob-admin -t msi where bind            # controllers/services/queues/code path
ob-admin -t msi status 13             # status code (+ trigger)
ob-admin -t msi explain fnol          # glossary
ob-admin ops -q payment               # search operations
ob-admin rules                        # scan rules
ob-admin scan ./src -s warning        # scan; exit code = worst severity
ob-admin -t flotilla tickets          # DBA tickets
ob-admin -t flotilla ticket 2001      # scripts + runbook
ob-admin -t flotilla sql 2001 dryrun  # print SQL
ob-admin -t flotilla run 2001 dryrun  # execute in a sandbox clone
ob-admin -t flotilla run 2001 fix --yes --live    # real database, destructive: both flags required
ob-admin instances                    # ▶ marks the active instance
ob-admin --json <command>             # exact API payloads for scripting
```

Tenant: `-t SLUG`, else `$OB_TENANT`, else `~/.onboarded/active` (set by `obi use`), else `generic`.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | ok / scan clean |
| 1 / 2 / 3 | scan found critical / error / warning-or-info (worst wins) |
| 4 | not found (tenant, operation, ticket…) |
| 5 | bad request (unknown rule, invalid input, SQL batch failed) |
| 6 | unavailable (API down, DB driver missing, database unreachable) |
| 7 | refused (exec disabled on server, destructive script without `--yes`) |

## Why one Python CLI (not Typer + a TypeScript `ob-admin`)

The scratch-build plan (PR-8) proposed two CLIs. For the MVP one is enough: local mode covers
offline authoring, API mode covers operating a deployed API, and both share one code path for
results. Stdlib-only matches `ob-dba` and `ob_instance.py`, so it installs anywhere Python does.
