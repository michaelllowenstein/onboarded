"""
Shared fixtures. psycopg and pyodbc are replaced by a scripted fake so the
suite runs anywhere. The fake records every statement and replays canned
result sets / errors keyed by a substring of the SQL.
"""
from __future__ import annotations

import sys
import types

import pytest


class FakeDiag:
    def __init__(self, msg, state=None, detail=None):
        self.message_primary, self.sqlstate, self.message_detail = msg, state, detail


class FakeDBError(Exception):
    def __init__(self, msg, state="42703", detail=None):
        super().__init__(msg)
        self.diag = FakeDiag(msg, state, detail)
        self.sqlstate = state


class FakeCursor:
    def __init__(self, conn):
        self.conn, self._sets, self._i = conn, [], 0
        self.description, self.rowcount, self.messages = None, -1, []

    def execute(self, sql, params=None):
        self.conn.executed.append(sql if params is None else (sql, params))
        for key, behaviour in self.conn.fake.script.items():
            if key in sql:
                if isinstance(behaviour, Exception):
                    raise behaviour
                self._sets = list(behaviour)
                break
        else:
            self._sets = [{"rowcount": -1}]
        self._i = 0
        self._load()
        return self

    def _load(self):
        cur = self._sets[self._i]
        self.description = [(c,) for c in cur["columns"]] if "columns" in cur else None
        self.rowcount = cur.get("rowcount", -1)
        for m in cur.get("notices", []):
            for h in self.conn.handlers:
                h(FakeDiag(m))
        self.messages = [("01000", f"[Microsoft][ODBC Driver 18 for SQL Server][SQL Server]{m}")
                         for m in cur.get("messages", [])]

    def fetchall(self):
        return [tuple(r) for r in self._sets[self._i].get("rows", [])]

    def nextset(self):
        if self._i + 1 < len(self._sets):
            self._i += 1
            self._load()
            return True
        return False

    def close(self):
        pass


class FakeConnection:
    def __init__(self, fake, autocommit, kwargs):
        self.fake, self.autocommit, self.kwargs = fake, autocommit, kwargs
        self.executed, self.handlers = [], []
        self.rolled_back = self.closed = False
        fake.connections.append(self)

    def cursor(self):
        return FakeCursor(self)

    def execute(self, sql, params=None):
        return self.cursor().execute(sql, params)

    def add_notice_handler(self, h):
        self.handlers.append(h)

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class Fake:
    def __init__(self):
        self.script, self.connections = {}, []

    @property
    def last(self):
        return self.connections[-1] if self.connections else None

    def all_sql(self):
        return [s if isinstance(s, str) else s[0] for c in self.connections for s in c.executed]


@pytest.fixture(autouse=True)
def fake_db(monkeypatch):
    fake = Fake()
    pg = types.ModuleType("psycopg")
    pg.connect = lambda autocommit=False, **kw: FakeConnection(fake, autocommit, kw)
    pg.Error = FakeDBError
    odbc = types.ModuleType("pyodbc")
    odbc.connect = lambda cs, autocommit=False, timeout=0: FakeConnection(fake, autocommit, {"cs": cs})
    monkeypatch.setitem(sys.modules, "psycopg", pg)
    monkeypatch.setitem(sys.modules, "pyodbc", odbc)
    yield fake


ENV_KEYS = ("OB_DB_DIALECT", "OB_DB_HOST", "OB_DB_SERVER", "OB_DB_PORT", "OB_DB_NAME", "OB_DB_USER",
            "OB_DB_PASSWORD", "OB_DB_SSLMODE", "OB_DB_AUTH", "OB_DB_TRUST_CERT", "OB_DB_DRIVER",
            "OB_DBA_TENANTS_ROOT", "OB_DB_ERROR_TABLE", "OB_AUTHOR_NAME", "OB_DB_ADMIN_DB",
            "PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD", "PGSSLMODE")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ENV_KEYS:
        monkeypatch.delenv(k, raising=False)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """Throwaway repo root: one postgres tenant 'demo', scaffolds, domain.json."""
    root = tmp_path / "repo"
    (root / "packages/core/tenants/demo/domain").mkdir(parents=True)
    (root / "packages/core/tenants/demo/domain/domain.json").write_text(
        '{"db_schema": {"dialect": "postgres", "host": "localhost", "port": 5432, "database": "ob_demo"}}')
    sd = root / "templates/demo/scaffolds"
    sd.mkdir(parents=True)
    (sd / "diagnostic.sql").write_text("-- {{TICKET_ID}} on {{TARGET_TABLE}}\nSELECT 1;\n")
    (sd / "README.md").write_text("# Ticket {{TICKET_ID}} by {{AUTHOR_NAME}}\n")
    monkeypatch.setenv("OB_REPO_ROOT", str(root))
    return root
