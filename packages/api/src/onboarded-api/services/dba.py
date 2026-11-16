"""
DBA tickets over HTTP — a thin adapter on packages/dba (same registry, runner
and sandbox the `ob-dba` CLI uses, so behaviour is identical).

Safety model (mirrors the CLI, plus one switch):
  * Reading tickets/scripts/runbooks is always allowed.
  * Executing SQL requires the server to be started with OB_API_DBA_EXEC=1.
  * Destructive scripts (fix*, rollback*) additionally require the request
    header  X-Onboarded-Confirm: <ticket>/<script>  — an exact echo, so a
    replayed or mistargeted request cannot run the wrong script.
  * `sandbox` defaults to true: postgres runs on a throwaway TEMPLATE clone,
    mssql inside an outer transaction that is always rolled back.
"""

from __future__ import annotations

import datetime as _dt
import decimal
import importlib.util
import uuid
from pathlib import Path
from typing import Any

from onboarded_api.errors import BadRequest, ConfirmationRequired, Forbidden, NotFound, Unavailable
from onboarded_api.settings import Settings

CONFIRM_HEADER = "X-Onboarded-Confirm"


def dba_available() -> bool:
    return importlib.util.find_spec("dba") is not None


def _json_safe(v: Any) -> Any:
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, decimal.Decimal):
        return str(v)
    if isinstance(v, (_dt.date, _dt.datetime, _dt.time)):
        return v.isoformat()
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, (bytes, bytearray, memoryview)):
        return f"<{len(bytes(v))} bytes>"
    return str(v)


class DbaService:
    def __init__(self, settings: Settings):
        self.settings = settings

    # ── helpers ────────────────────────────────────────────────────────────
    def _require(self) -> None:
        if not dba_available():
            raise Unavailable("DBA engine not installed: pip install -e packages/dba")

    def _registry(self, slug: str):
        self._require()
        from dba.registry import TicketRegistry
        root = self.settings.tenants_dir / slug / "scripts"
        if not (self.settings.tenants_dir / slug).is_dir():
            raise NotFound(f"Tenant '{slug}' not found")
        return TicketRegistry(scripts_root=root, tenant_slug=slug)

    def _ticket(self, slug: str, ticket_id: str):
        t = self._registry(slug).get(ticket_id)
        if not t:
            raise NotFound(f"No ticket '{ticket_id}' for tenant '{slug}'")
        return t

    def _script(self, slug: str, ticket_id: str, name: str):
        t = self._ticket(slug, ticket_id)
        s = t.get_script(name) or next(
            (t.get_script(n) for n in t.script_names if n.startswith(name + "-")), None)
        if not s:
            raise NotFound(f"No script '{name}' in {t.qualified_label} (have: {', '.join(t.script_names)})")
        return t, s

    @staticmethod
    def _summary(t) -> dict[str, Any]:
        return {
            "id": t.id, "label": t.qualified_label, "hasRunbook": t.has_runbook,
            "scripts": [{"name": n, "label": t.get_script(n).qualified_label,
                         "destructive": t.get_script(n).is_destructive} for n in t.script_names],
        }

    # ── reads ──────────────────────────────────────────────────────────────
    def tickets(self, slug: str) -> list[dict[str, Any]]:
        return [self._summary(t) for t in self._registry(slug).all_tickets()]

    def ticket(self, slug: str, ticket_id: str) -> dict[str, Any]:
        t = self._ticket(slug, ticket_id)
        rb = (t.path / "runbook.md").read_text(encoding="utf-8") if t.has_runbook else None
        return {**self._summary(t), "runbook": rb}

    def script_source(self, slug: str, ticket_id: str, name: str) -> dict[str, Any]:
        t, s = self._script(slug, ticket_id, name)
        return {"ticket": t.id, "name": s.name, "destructive": s.is_destructive, "sql": s.read()}

    # ── execution ──────────────────────────────────────────────────────────
    def run(self, slug: str, ticket_id: str, name: str, *, sandbox: bool, confirm: str | None,
            max_rows: int = 200, continue_on_error: bool = False) -> dict[str, Any]:
        if not self.settings.dba_exec:
            raise Forbidden("SQL execution is disabled on this server (start it with OB_API_DBA_EXEC=1).")
        t, s = self._script(slug, ticket_id, name)
        expected = f"{t.id}/{s.name}"
        if s.is_destructive and (confirm or "").strip() != expected:
            raise ConfirmationRequired(
                f"'{s.qualified_label}' is destructive. Resend with header {CONFIRM_HEADER}: {expected}")

        from dba.connection import ConnectionConfig
        from dba.runner import Runner

        domain = self.settings.tenants_dir / slug / "domain" / "domain.json"
        try:
            cfg = ConnectionConfig.from_domain(domain)
        except ValueError as e:
            raise BadRequest(str(e)) from e

        def go(target, outer_rollback=False):
            with Runner(target, stop_on_error=not continue_on_error, label=s.qualified_label,
                        mssql_outer_rollback=outer_rollback) as r:
                return r.execute(s, confirm=True)

        try:
            if sandbox and cfg.dialect == "postgres":
                from dba.sandbox import postgres_clone
                with postgres_clone(cfg) as clone:
                    target, results = clone.summary(), go(clone)
            else:
                target, results = cfg.summary(), go(cfg, outer_rollback=sandbox)
        except ImportError as e:
            raise Unavailable(f"{e}. Install the driver: pip install -e 'packages/dba[postgres]'") from e
        except RuntimeError as e:                       # sandbox: source DB busy
            raise BadRequest(str(e)) from e
        except Exception as e:                          # driver errors, matched by name
            if type(e).__name__ in ("OperationalError", "InterfaceError"):
                raise Unavailable(f"Cannot reach the database: {str(e).splitlines()[0]}") from e
            raise

        views = [{
            "columns": list(rs.columns),
            "rows": [[_json_safe(v) for v in row] for row in rs.rows[:max_rows]],
            "rowsAffected": rs.rows_affected, "error": rs.error,
            "batchIndex": rs.batch_index, "resultIndex": rs.result_index,
            "messages": list(rs.messages),
        } for rs in results]
        return {"label": s.qualified_label, "mode": "sandbox" if sandbox else "live",
                "target": target, "ok": all(v["error"] is None for v in views), "results": views}


class InstanceService:
    """Reads instances/<slug>/instance.json (see docs/development/instances.md)."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def _active(self) -> str:
        f = self.settings.home / "active"
        try:
            return f.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    @staticmethod
    def _summary(data: dict, active: str) -> dict[str, Any]:
        db = data.get("db") or {}
        return {
            "slug": data.get("slug", ""), "name": data.get("name") or data.get("slug", ""),
            "status": data.get("status") or "planned",
            "classification": data.get("classification") or "public",
            "industry": data.get("industry"),
            "repos": [{"key": r.get("key") or "", "url": r.get("url") or "", "ref": r.get("ref") or "main",
                       "commit": r.get("commit") or None} for r in data.get("repos") or []],
            "db": {"dialect": db.get("dialect"), "name": db.get("name")},
            "active": data.get("slug") == active,
        }

    def _load(self, path: Path) -> dict | None:
        import json
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def list(self) -> list[dict[str, Any]]:
        active, out = self._active(), []
        d = self.settings.instances_dir
        if d.is_dir():
            for f in sorted(d.glob("*/instance.json")):
                data = self._load(f)
                if data:
                    out.append(self._summary(data, active))
        return out

    def get(self, slug: str) -> dict[str, Any]:
        data = self._load(self.settings.instances_dir / slug / "instance.json")
        if not data:
            raise NotFound(f"Instance '{slug}' not found")
        return self._summary(data, self._active())
