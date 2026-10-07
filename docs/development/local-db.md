# Local Postgres + DBA engine

One Postgres 18 server for the whole workspace, one database per onboarded
instance (`ob_<slug>`). Runs in Docker on `localhost:55432` so it never
collides with another local Postgres on 5432.

## Pieces

| Path | What it is |
|---|---|
| `deploy/local/db/docker-compose.db.yml` | `postgres:18`, loopback-only, volume `onboarded_pg_data` |
| `deploy/local/db/.env` (gitignored) | superuser + `ob_dba` + `ob_reader` passwords, port |
| `deploy/local/db/sql/00_roles.sql` | roles: `ob_dba` (owns instance DBs, CREATEDB for sandboxes), `ob_reader` (read-only) |
| `deploy/local/db/sql/10_instance_db.sql` | per-instance DB, `err.db_exception_tank`, default read grants |
| `deploy/local/db/sql/20_demo_schema.sql` | demo data for the generic tenant (P-1002 is broken on purpose) |
| `deploy/local/db/init-local-db.sh` | up + roles + `ob_generic` + demo, idempotent |
| `packages/dba/` | `ob-dba` / `onboarded dba`: ticket runner (psycopg 3) |

## Bring-up

```bash
cp deploy/local/db/.env.example deploy/local/db/.env && chmod 600 deploy/local/db/.env   # edit passwords
just db-init                                   # or deploy/local/db/init-local-db.sh
python3 packages/core/scripts/ob_instance.py pgpass        # ~/.pgpass for ob_dba / ob_reader

python3 -m venv packages/dba/.venv
packages/dba/.venv/bin/pip install -e 'packages/dba[postgres,test]'
just dba-test
```

## Ticket conventions (Postgres)

- `diagnostic.sql` — read only; safe as `ob_reader`.
- `dryrun.sql` — `BEGIN; … ROLLBACK;` and ends with a PASS/FAIL gate table.
- `fix.sql`, `rollback.sql` — ship with `ROLLBACK;  -- COMMIT;` as the last line.
  Guards and verification are `DO $$ … RAISE EXCEPTION … $$;` blocks, so a
  failed check aborts before the last line is reached.
- No psql meta-commands (`\set`, `\gexec`) in ticket scripts: the runner sends
  SQL to the server, not to psql. It rejects them with the line number.
- `-- @batch` on its own line splits a script into independent batches.
  Without it, the whole file is one batch (like `psql -f` with ON_ERROR_STOP).

## Runner behaviour

- Connections are autocommit: the script owns its transaction.
- `--yes` is required for `fix*` and `rollback*`.
- `--sandbox` copies the instance database (`CREATE DATABASE … TEMPLATE`), runs
  there, and drops the copy. Needs no other open sessions on the source DB.
- On error the runner rolls back whatever the script left open and records the
  failure in `err.db_exception_tank` on a fresh transaction (`ob-dba errors`).
- Every result set and every `RAISE NOTICE` is printed; `--csv DIR` writes one
  file per result set.

Connection resolution: `OB_DB_*` env → tenant `domain.json` `db_schema` →
libpq `PG*` env / `~/.pgpass`. `ob-instance use <slug>` writes the `OB_DB_*`
values for you.

SQL Server remains available as a legacy dialect (`OB_DB_DIALECT=mssql`,
`pip install -e 'packages/dba[mssql]'`) for T-SQL tenants such as `msi`.
