"""
ob-admin — Onboarded admin CLI.

    ob-admin [global options] <command> [args]

Global options
    -t, --tenant SLUG   tenant (default: $OB_TENANT, then ~/.onboarded/active, then generic)
    --api URL           use the REST API at URL ($OB_API_URL, default http://127.0.0.1:8000)
    --local             read the repo directly (no server)
    --json              machine-readable output (exact API payloads)
    Without --api/--local the API is used when it answers /health, else local.

Commands
    health                              server/tenant health
    tenants                             loaded tenants with counts
    tenant [SLUG]                       one tenant card
    domain                              full camelCase domain view (JSON)
    ops [-q TEXT]                       operations
    where KEY                           exact-then-fuzzy lookup (like `ob where`)
    status [CODE|-q TEXT]               status codes
    explain [TERM|-q TEXT]              glossary
    rules                               scan rules
    scan PATH... [-r RULE] [-s SEV]     run scan rules; exit 0/1/2/3 = clean/critical/error/warning
    tickets                             DBA tickets for the tenant
    ticket ID                           scripts + runbook
    sql ID SCRIPT                       print a script
    run ID SCRIPT [--live] [--yes]      execute (sandbox unless --live; fix/rollback need --yes)
    instances                           instance manifests (▶ = active)
    reload                              re-read domain.json files

Exit codes
    0 ok · 1 scan: critical · 2 scan: error · 3 scan: warning/info
    4 not found · 5 bad request/usage · 6 unavailable (API down, no driver, DB down)
    7 refused (exec disabled, confirmation needed)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

from onboarded_admin import render
from onboarded_admin.backends import DEFAULT_API, CliError, HttpBackend, LocalBackend

EXIT = {"not_found": 4, "bad_request": 5, "unavailable": 6, "forbidden": 7, "confirm": 7}

# def default_tenant() -> str:
#     if os.environ.get("OB_TENANT"):
#         return os.environ["OB_TENANT"].lower()
#     home = Path(os.environ.get("OB_HOME", Path.home() / ".onboarded")).expanduser()
#     try:
#         active = (home / "active").read_text(encoding="utf-8").strip()
#         if active:
#             return active
#     except OSError:
#         pass
#     return "generic"


# def pick_backend(a: argparse.Namespace):
#     if a.local:
#         return LocalBackend()
#     url = a.api or os.environ.get("OB_API_URL") or DEFAULT_API
#     http = HttpBackend(url)
#     if a.api or os.environ.get("OB_API_URL"):
#         return http                                  # explicit: never silently fall back
#     return http if http.reachable() else LocalBackend()


# def build_parser() -> argparse.ArgumentParser:
#     p = argparse.ArgumentParser(prog="ob-admin", description="Onboarded admin CLI",
#                                 formatter_class=argparse.RawDescriptionHelpFormatter,
#                                 epilog="Exit codes: 0 ok · 1/2/3 scan severity · 4 not found · "
#                                        "5 bad request · 6 unavailable · 7 refused")
#     p.add_argument("-t", "--tenant", default=None)
#     g = p.add_mutually_exclusive_group()
#     g.add_argument("--api", metavar="URL")
#     g.add_argument("--local", action="store_true")
#     p.add_argument("--json", action="store_true")
#     sub = p.add_subparsers(dest="cmd", required=True, metavar="<command>")

#     for name, hlp in (("health", "server health"), ("tenants", "list tenants"), ("domain", "domain view"),
#                       ("rules", "scan rules"), ("tickets", "DBA tickets"), ("instances", "instances"),
#                       ("reload", "reload domains")):
#         sub.add_parser(name, help=hlp)
#     sub.add_parser("tenant", help="tenant card").add_argument("slug", nargs="?")
#     sub.add_parser("ops", help="operations").add_argument("-q", "--query")
#     sub.add_parser("where", help="lookup").add_argument("key")
#     for name in ("status", "explain"):
#         x = sub.add_parser(name, help="statuses" if name == "status" else "glossary")
#         x.add_argument("key", nargs="?")
#         x.add_argument("-q", "--query")
#     sc = sub.add_parser("scan", help="scan paths")
#     sc.add_argument("paths", nargs="+")
#     sc.add_argument("-r", "--rule", action="append", dest="rules")
#     sc.add_argument("-s", "--min-severity", default="info",
#                     choices=("critical", "error", "warning", "info"))
#     sub.add_parser("ticket", help="ticket detail").add_argument("id")
#     sq = sub.add_parser("sql", help="print a script")
#     sq.add_argument("id")
#     sq.add_argument("script")
#     rn = sub.add_parser("run", help="execute a script")
#     rn.add_argument("id")
#     rn.add_argument("script")
#     rn.add_argument("--live", action="store_true", help="run on the real database (default: sandbox)")
#     rn.add_argument("--yes", action="store_true", help="confirm a destructive script")
#     rn.add_argument("--max-rows", type=int, default=200)
#     return p


# def dispatch(a: argparse.Namespace, b) -> tuple[Any, Callable[[Any], str], int]:
#     """Return (payload, human renderer, exit code)."""
#     t = a.tenant
#     c = a.cmd
#     if c == "health":
#         h = b.health()
#         return h, render.health, 0 if h["status"] == "ok" else 6
#     if c == "tenants":
#         return b.tenants(), render.tenants, 0
#     if c == "tenant":
#         return b.tenant(a.slug or t), render.tenant, 0
#     if c == "domain":
#         return b.domain(t), render.as_json, 0
#     if c == "ops":
#         return b.operations(t, a.query), render.operations, 0
#     if c == "where":
#         return b.where(t, a.key), render.where, 0
#     if c == "status":
#         items = b.statuses(t, a.query)
#         if a.key:
#             items = [s for s in items if s["code"] == a.key]
#             if not items:
#                 raise CliError("not_found", f"Status '{a.key}' not found in tenant '{t}'")
#         return items, render.statuses, 0
#     if c == "explain":
#         items = b.glossary(t, a.query)
#         if a.key:
#             items = [g for g in items if g["id"] == a.key] or [g for g in b.glossary(t, a.key)]
#             if not items:
#                 raise CliError("not_found", f"Term '{a.key}' not found in tenant '{t}'")
#         return items, render.glossary, 0
#     if c == "rules":
#         return b.rules(t), render.rules, 0
#     if c == "scan":
#         r = b.scan(t, a.paths, a.rules, a.min_severity)
#         return r, render.scan, int(r["exitCode"])
#     if c == "tickets":
#         return b.tickets(t), render.tickets, 0
#     if c == "ticket":
#         return b.ticket(t, a.id), render.ticket, 0
#     if c == "sql":
#         return b.script(t, a.id, a.script), lambda s: s["sql"], 0
#     if c == "run":
#         confirm = f"{a.id}/{a.script}" if a.yes else None
#         r = b.run(t, a.id, a.script, sandbox=not a.live, confirm=confirm, max_rows=a.max_rows)
#         return r, render.run, 0 if r["ok"] else 5
#     if c == "instances":
#         return b.instances(), render.instances, 0
#     if c == "reload":
#         return b.reload(), render.as_json, 0
#     raise CliError("bad_request", f"unknown command {c}")


# def main(argv: list[str] | None = None) -> int:
#     a = build_parser().parse_args(argv)
#     a.tenant = (a.tenant or default_tenant()).lower()
#     try:
#         b = pick_backend(a)
#         payload, human, code = dispatch(a, b)
#     except CliError as e:
#         if a.json:
#             print(json.dumps({"error": e.kind, "detail": e.message}))
#         else:
#             print(render.err(e.message), file=sys.stderr)
#             if e.kind == "confirm":
#                 print(render.dim("  re-run with --yes to confirm"), file=sys.stderr)
#         return EXIT.get(e.kind, 6)
#     except KeyboardInterrupt:
#         return 130
#     print(json.dumps(payload, indent=2, ensure_ascii=False) if a.json else human(payload))
#     if not a.json and os.environ.get("OB_ADMIN_VERBOSE"):
#         print(render.dim(f"[{b.name} · tenant {a.tenant}]"), file=sys.stderr)
#     return code


# if __name__ == "__main__":
#     sys.exit(main())
