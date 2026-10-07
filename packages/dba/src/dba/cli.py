"""
dba.cli — command line entry point:  python -m dba <command>  (or `ob-dba`)

    config                         Show resolved connection (no secrets)
    ping                           Connect and print server/db/login
    tenants                        Tenants that have a scripts/ directory
    tickets                        Tickets for the current tenant
    show <ticket>                  Scripts + runbook for a ticket
    import <ticket>                Copy ~/.onboarded/<slug>/tickets/<id>-package into scripts/
    scaffold <ticket> [-t K=V ...] Create the 5-file ticket directory
    run <ticket> <script>          Execute one script (fix/rollback need --yes)
    exec (-q SQL | -f FILE)        Ad-hoc SQL (no safety gate — use --sandbox)
    errors [-n N]                  Recent failures logged to err.db_exception_tank

Tenant:     --tenant <slug>  or  OB_TENANT   (default: generic)
Repo root:  OB_REPO_ROOT, else detected from this file's location.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dba.connection import ConnectionConfig
from dba.formatters import render_console, write_csv
from dba.models import Script
from dba.registry import TenantRegistry, TicketRegistry
from dba.scaffold import scaffold_ticket


def repo_root() -> Path:
    env = os.environ.get("OB_REPO_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    # packages/dba/src/dba/cli.py → repo root is 4 levels up from the package dir
    return Path(__file__).resolve().parents[4]


def tenants_root() -> Path:
    return Path(os.environ.get("OB_DBA_TENANTS_ROOT") or repo_root() / "packages" / "core" / "tenants")


def domain_path(slug: str) -> Path:
    return repo_root() / "packages" / "core" / "tenants" / slug / "domain" / "domain.json"


def scaffold_dir(slug: str) -> Path:
    return repo_root() / "templates" / slug / "scaffolds"


def _registry(slug: str) -> TicketRegistry:
    return TicketRegistry(scripts_root=tenants_root() / slug / "scripts", tenant_slug=slug)


def tenant_dialect(slug: str) -> str:
    """Dialect without needing a full connection config (used by scaffold)."""
    if os.environ.get("OB_DB_DIALECT"):
        return os.environ["OB_DB_DIALECT"].lower()
    dp = domain_path(slug)
    if dp.is_file():
        import json
        return ((json.loads(dp.read_text(encoding="utf-8")).get("db_schema") or {})
                .get("dialect") or "postgres").lower()
    return "postgres"


def _config(slug: str) -> ConnectionConfig:
    return ConnectionConfig.from_domain(domain_path(slug))


def _run_sql(args, slug: str, sql: str | None = None, script: Script | None = None) -> int:
    from dba.runner import Runner  # imported late so non-DB commands work without a driver

    cfg = _config(slug)
    label = script.qualified_label if script else "adhoc"

    def go(target_cfg, mssql_outer_rollback=False):
        with Runner(target_cfg, stop_on_error=not args.continue_on_error, label=label,
                    mssql_outer_rollback=mssql_outer_rollback) as r:
            return r.execute(script, confirm=args.yes) if script else r.execute_raw(sql or "")

    if args.sandbox and cfg.dialect == "postgres":
        from dba.sandbox import postgres_clone
        with postgres_clone(cfg) as clone:
            print(f"→ {clone.summary()}  ·  SANDBOX clone of '{cfg.database}' (dropped afterwards)", file=sys.stderr)
            results = go(clone)
    elif args.sandbox:
        print(f"→ {cfg.summary()}  ·  SANDBOX (outer transaction, always rolled back)", file=sys.stderr)
        results = go(cfg, mssql_outer_rollback=True)
    else:
        print(f"→ {cfg.summary()}  ·  LIVE (script controls its own transaction)", file=sys.stderr)
        results = go(cfg)

    errors = render_console(results, max_rows=args.max_rows)
    if args.csv:
        prefix = label.replace(":", "_").replace("/", "_")
        for p in write_csv(results, Path(args.csv), prefix=prefix):
            print(f"  csv → {p}", file=sys.stderr)
    return 1 if errors else 0


PING_SQL = {
    "postgres": "SELECT inet_server_addr()::text AS host, current_database() AS db, "
                "session_user AS login, current_setting('server_version') AS version;",
    "mssql": "SELECT @@SERVERNAME AS server_name, DB_NAME() AS db, SUSER_SNAME() AS login, "
             "CAST(SERVERPROPERTY('ProductVersion') AS nvarchar(32)) AS version;",
}
ERRORS_SQL = ("SELECT logged_at, script_label, sqlstate, left(error_message, 120) AS error_message, "
              "user_name FROM err.db_exception_tank ORDER BY logged_at DESC LIMIT {n};")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ob-dba", description="Onboarded DBA engine")
    p.add_argument("--tenant", default=os.environ.get("OB_TENANT", "generic"))
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("config")
    sub.add_parser("ping")
    er = sub.add_parser("errors", help="recent rows from err.db_exception_tank (postgres)")
    er.add_argument("-n", type=int, default=20)
    sub.add_parser("tenants")
    sub.add_parser("tickets")
    sp = sub.add_parser("show"); sp.add_argument("ticket")
    im = sub.add_parser("import", help="copy a `onboarded ticket fix` package into the tenant's scripts/")
    im.add_argument("ticket"); im.add_argument("--force", action="store_true")

    sc = sub.add_parser("scaffold")
    sc.add_argument("ticket")
    sc.add_argument("-t", "--token", action="append", default=[], metavar="KEY=VALUE")
    sc.add_argument("--force", action="store_true")

    def exec_flags(x):
        x.add_argument("--yes", action="store_true", help="confirm destructive script")
        x.add_argument("--sandbox", action="store_true", help="run on a throwaway copy of the database")
        x.add_argument("--continue-on-error", action="store_true")
        x.add_argument("--csv", metavar="DIR")
        x.add_argument("--max-rows", type=int, default=200)

    rn = sub.add_parser("run"); rn.add_argument("ticket"); rn.add_argument("script"); exec_flags(rn)
    ex = sub.add_parser("exec")
    g = ex.add_mutually_exclusive_group(required=True)
    g.add_argument("-q", "--query"); g.add_argument("-f", "--file")
    exec_flags(ex)

    a = p.parse_args(argv)
    slug = a.tenant.lower()

    try:
        if a.cmd == "config":
            print(_config(slug).summary())
            return 0
        if a.cmd in ("ping", "errors"):
            a.sandbox, a.continue_on_error, a.csv, a.max_rows, a.yes = False, False, None, 200, False
            dialect = _config(slug).dialect
            q = PING_SQL[dialect] if a.cmd == "ping" else ERRORS_SQL.format(n=int(a.n))
            return _run_sql(a, slug, sql=q)
        if a.cmd == "tenants":
            reg = TenantRegistry(tenants_root())
            for s in reg.auto_discover():
                print(f"{s:16} {reg.get_registry(s).count} ticket(s)")
            return 0
        if a.cmd == "tickets":
            for t in _registry(slug).all_tickets():
                rb = " +runbook" if t.has_runbook else ""
                print(f"{t.qualified_label:24} {', '.join(t.script_names)}{rb}")
            return 0
        if a.cmd == "show":
            t = _registry(slug).get(a.ticket)
            if not t:
                print(f"No ticket '{a.ticket}' for tenant '{slug}'", file=sys.stderr); return 2
            for n in t.script_names:
                s = t.get_script(n)
                print(f"  {'⚠' if s.is_destructive else '·'} {s.qualified_label}")
            if t.has_runbook:
                print("\n" + (t.path / "runbook.md").read_text(encoding="utf-8"))
            return 0
        if a.cmd == "scaffold":
            tokens = dict(kv.split("=", 1) for kv in a.token)
            for env_key, tok in (("OB_AUTHOR_NAME", "AUTHOR_NAME"), ("OB_AUTHOR_LOGIN", "AUTHOR_LOGIN"),
                                 ("OB_AUTHOR_PARTY_ID", "AUTHOR_PARTY_ID")):
                if os.environ.get(env_key):
                    tokens.setdefault(tok, os.environ[env_key])
            sd = scaffold_dir(slug)
            report = scaffold_ticket(tenants_root() / slug / "scripts", a.ticket,
                                     scaffold_dir=sd if sd.is_dir() else None, tokens=tokens, overwrite=a.force,
                                     dialect=tenant_dialect(slug))
            print(f"Created {tenants_root() / slug / 'scripts' / a.ticket}"
                  f"  (scaffolds: {sd if sd.is_dir() else 'built-in'})")
            for f, missing in report.items():
                print(f"  {'○' if missing else '✔'} {f}" + (f"  unfilled: {', '.join(missing)}" if missing else ""))
            return 0
        if a.cmd == "import":
            import shutil
            src = Path(os.environ.get("HOME", "~")).expanduser() / ".onboarded" / slug / "tickets" / f"{a.ticket}-package"
            if not src.is_dir():
                print(f"No package at {src} — run: onboarded ticket fix {a.ticket}", file=sys.stderr); return 2
            dest = tenants_root() / slug / "scripts" / a.ticket
            if dest.exists() and any(dest.iterdir()) and not a.force:
                print(f"{dest} already exists (use --force)", file=sys.stderr); return 2
            dest.mkdir(parents=True, exist_ok=True)
            for f in sorted(src.iterdir()):
                name = "runbook.md" if f.name == "README.md" else f.name.replace(f"-{a.ticket}.sql", ".sql")
                shutil.copy2(f, dest / name)
                print(f"  ✔ {name}")
            print(f"Imported into {dest}")
            return 0
        if a.cmd == "run":
            t = _registry(slug).get(a.ticket)
            if not t:
                print(f"No ticket '{a.ticket}' for tenant '{slug}'", file=sys.stderr); return 2
            s = t.get_script(a.script) or next(
                (t.get_script(n) for n in t.script_names if n.startswith(a.script + "-")), None)
            if not s:
                print(f"No script '{a.script}' in {t.qualified_label} (have: {', '.join(t.script_names)})",
                      file=sys.stderr); return 2
            if s.is_destructive and not a.yes:
                raise PermissionError(f"Script '{s.qualified_label}' is destructive. Re-run with --yes "
                                      f"(add --sandbox to rehearse on a throwaway copy).")
            return _run_sql(a, slug, script=s)
        if a.cmd == "exec":
            sql = a.query if a.query else Path(a.file).read_text(encoding="utf-8")
            return _run_sql(a, slug, sql=sql)
    except PermissionError as e:
        print(f"✖ {e}", file=sys.stderr); return 3
    except (ValueError, FileExistsError, RuntimeError) as e:
        print(f"✖ {e}", file=sys.stderr); return 2
    except ImportError as e:
        print(f"✖ {e}. Install the driver: pip install -e 'packages/dba[postgres]' "
              f"(or [mssql] for SQL Server tenants).", file=sys.stderr); return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
