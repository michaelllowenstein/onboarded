"""DBA + instances services. The real dba.Runner runs against a scripted fake psycopg."""
from __future__ import annotations

import dataclasses
import datetime
import decimal
import json
import sys
import types

import pytest

from onboarded_api import schemas
from onboarded_api.errors import ConfirmationRequired, Forbidden, NotFound, Unavailable
from onboarded_api.services.dba_service import DbaService, InstanceService


class _Cur:
    def __init__(self, conn):
        self.conn, self.description, self.rowcount, self._rows = conn, None, -1, []

    def execute(self, sql, params=None):
        self.conn.fake.sql.append(sql)
        if self.conn.fake.fail and self.conn.fake.fail in sql:
            raise RuntimeError("boom")
        if "SELECT" in sql.upper():
            self.description = [("id",), ("amount",), ("at",)]
            self._rows = [(1, decimal.Decimal("9.50"), datetime.date(2026, 1, 2))]
        return self

    def fetchall(self):
        return self._rows

    def nextset(self):
        return False

    def close(self):
        pass


class _Conn:
    def __init__(self, fake, kw):
        self.fake, self.kw = fake, kw
        fake.conns.append(self)

    def cursor(self):
        return _Cur(self)

    def execute(self, sql, params=None):
        return self.cursor().execute(sql, params)

    def add_notice_handler(self, h):
        pass

    def rollback(self):
        pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


@pytest.fixture
def fake_pg(monkeypatch):
    fake = types.SimpleNamespace(conns=[], sql=[], fail=None)
    mod = types.ModuleType("psycopg")
    mod.connect = lambda autocommit=False, **kw: _Conn(fake, kw)
    monkeypatch.setitem(sys.modules, "psycopg", mod)
    for k in ("OB_DB_NAME", "OB_DB_DIALECT", "OB_DB_HOST", "PGDATABASE"):
        monkeypatch.delenv(k, raising=False)
    return fake


@pytest.fixture
def dba(settings):
    return DbaService(dataclasses.replace(settings, dba_exec=True))


def test_lists_real_tickets(dba):
    tickets = dba.tickets("flotilla")
    t = next(t for t in tickets if t["id"] == "2001")
    names = {s["name"]: s["destructive"] for s in t["scripts"]}
    assert names == {"diagnostic": False, "dryrun": False, "fix": True, "rollback": True}
    assert t["hasRunbook"]
    for x in tickets:
        schemas.TicketSummary.model_validate(x)


def test_ticket_detail_and_script_source(dba):
    d = dba.ticket("generic", "1001")
    assert d["runbook"] and d["label"] == "generic:1001"
    src = dba.script_source("generic", "1001", "fix")
    assert src["destructive"] and src["sql"].strip()
    schemas.ScriptSource.model_validate(src)


def test_not_found_paths(dba):
    with pytest.raises(NotFound):
        dba.tickets("nope")
    with pytest.raises(NotFound):
        dba.ticket("generic", "9999")
    with pytest.raises(NotFound, match="have:"):
        dba.script_source("generic", "1001", "nope")


def test_tenant_without_scripts_has_no_tickets(dba):
    assert dba.tickets("msi") == []


def test_exec_disabled_by_default(settings):
    with pytest.raises(Forbidden, match="OB_API_DBA_EXEC"):
        DbaService(settings).run("generic", "1001", "diagnostic", sandbox=False, confirm=None)


def test_destructive_requires_exact_confirmation(dba, fake_pg):
    with pytest.raises(ConfirmationRequired, match="1001/fix"):
        dba.run("generic", "1001", "fix", sandbox=True, confirm=None)
    with pytest.raises(ConfirmationRequired):
        dba.run("generic", "1001", "fix", sandbox=True, confirm="1001/rollback")
    assert fake_pg.conns == []          # nothing touched the database


def test_live_diagnostic_run_serializes_rows(dba, fake_pg):
    r = dba.run("generic", "1001", "diagnostic", sandbox=False, confirm=None)
    assert r["mode"] == "live" and r["ok"]
    rs = next(x for x in r["results"] if x["columns"])
    assert rs["rows"][0] == [1, "9.50", "2026-01-02"]
    schemas.RunResult.model_validate(r)
    json.dumps(r)                                   # fully JSON-serialisable


def test_sandbox_runs_on_a_clone_and_drops_it(dba, fake_pg):
    r = dba.run("flotilla", "2001", "fix", sandbox=True, confirm="2001/fix")
    assert r["mode"] == "sandbox" and "__sbx_" in r["target"]
    joined = "\n".join(fake_pg.sql)
    assert "CREATE DATABASE" in joined and "TEMPLATE \"ob_flotilla\"" in joined
    assert "DROP DATABASE IF EXISTS" in joined


def test_max_rows_truncates(dba, fake_pg):
    r = dba.run("generic", "1001", "diagnostic", sandbox=False, confirm=None, max_rows=1)
    assert all(len(x["rows"]) <= 1 for x in r["results"])


def test_missing_driver_is_unavailable(dba, monkeypatch):
    monkeypatch.setitem(sys.modules, "psycopg", None)        # import → ImportError
    with pytest.raises(Unavailable, match="driver"):
        dba.run("generic", "1001", "diagnostic", sandbox=False, confirm=None)


# ── instances ───────────────────────────────────────────────────────────────

def test_instances_list_marks_active(settings):
    settings.home.mkdir(parents=True)
    (settings.home / "active").write_text("flotilla\n")
    items = InstanceService(settings).list()
    by = {i["slug"]: i for i in items}
    assert by["flotilla"]["active"] and not by["generic"]["active"]
    assert by["flotilla"]["db"]["name"] == "ob_flotilla" and by["flotilla"]["repos"][0]["commit"]
    for i in items:
        schemas.InstanceSummary.model_validate(i)


def test_instance_not_found(settings):
    with pytest.raises(NotFound):
        InstanceService(settings).get("nope")
