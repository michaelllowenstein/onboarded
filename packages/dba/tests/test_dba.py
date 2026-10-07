from __future__ import annotations

import pytest

import dba
from dba.cli import main
from dba.connection import ConnectionConfig
from dba.models import Script, Ticket
from dba.registry import TenantRegistry
from dba.runner import Runner, find_psql_meta, split_batches
from dba.scaffold import fill_tokens, scaffold_ticket

from conftest import FakeDBError


def pg(**kw) -> ConnectionConfig:
    return ConnectionConfig(database=kw.pop("database", "ob_demo"), **kw)


# ── package imports cleanly (regression: stray 'Y' / 'odels · PY' lines) ─────
def test_package_imports():
    assert dba.__version__ == "1.0.0"


# ── batching ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("sql,n", [
    ("SELECT 1", 1),
    ("SELECT 1\nGO\nSELECT 2\nGO", 2),
    ("SELECT 1\n  go  \nSELECT 2", 2),
    ("SELECT 1\nGO 5\nSELECT 2", 2),
    ("SELECT 1\nGO -- next\nSELECT 2", 2),
    ("GO\nGO\nSELECT 1\nGO\n\nGO", 1),
    ("SELECT 'GOOD' AS x\nGO", 1),
])
def test_split_batches_mssql(sql, n):
    assert len(split_batches(sql, "mssql")) == n


@pytest.mark.parametrize("sql,n", [
    ("BEGIN; SELECT 1; ROLLBACK;", 1),
    ("SELECT 1;\nGO\nSELECT 2;", 1),             # GO means nothing to Postgres
    ("SELECT 1;\n-- @batch\nSELECT 2;", 2),
    ("SELECT 1;\n  -- @BATCH second half\nSELECT 2;", 2),
])
def test_split_batches_postgres(sql, n):
    assert len(split_batches(sql, "postgres")) == n


def test_psql_meta_detection():
    assert find_psql_meta("SELECT 1;\n\\set x 1\n") == 2
    assert find_psql_meta("SELECT E'\\\\n';") is None


# ── models / registry ────────────────────────────────────────────────────────
def test_destructive_detection(tmp_path):
    for name, destructive in [("fix", True), ("rollback", True), ("fix-109000", True),
                              ("diagnostic", False), ("dryrun", False), ("dryrun-109000", False)]:
        assert Script(name=name, path=tmp_path / f"{name}.sql").is_destructive is destructive


def test_registries(tmp_path):
    t = tmp_path / "tenants" / "demo" / "scripts" / "42"
    t.mkdir(parents=True)
    (t / "diagnostic.sql").write_text("SELECT 1")
    (tmp_path / "tenants" / "demo" / "scripts" / "empty").mkdir()
    (tmp_path / "tenants" / "noscripts").mkdir()
    reg = TenantRegistry(tmp_path / "tenants")
    assert reg.auto_discover() == ["demo"]
    assert [x.id for x in reg.get_registry("demo").all_tickets()] == ["42"]


# ── connection ───────────────────────────────────────────────────────────────
def test_postgres_from_domain(repo, monkeypatch):
    monkeypatch.setenv("OB_DB_USER", "ob_dba")
    monkeypatch.setenv("OB_DB_PASSWORD", "s3cret")
    cfg = ConnectionConfig.from_domain(repo / "packages/core/tenants/demo/domain/domain.json")
    kw = cfg.psycopg_kwargs()
    assert (cfg.dialect, kw["dbname"], kw["port"], kw["user"]) == ("postgres", "ob_demo", 5432, "ob_dba")
    assert "s3cret" not in cfg.summary() and "postgres://localhost:5432/ob_demo" in cfg.summary()


def test_env_beats_domain_beats_pg_env(repo, monkeypatch):
    dp = repo / "packages/core/tenants/demo/domain/domain.json"
    monkeypatch.setenv("PGDATABASE", "from_pg"); monkeypatch.setenv("PGPORT", "6543")
    assert ConnectionConfig.from_domain(dp).database == "ob_demo"          # domain beats PG*
    assert ConnectionConfig.from_domain(dp).effective_port == 5432
    monkeypatch.setenv("OB_DB_NAME", "from_ob")
    assert ConnectionConfig.from_domain(dp).database == "from_ob"          # OB_* beats domain
    assert ConnectionConfig.from_env().database == "from_ob"


def test_pg_env_only(monkeypatch):
    monkeypatch.setenv("PGDATABASE", "x"); monkeypatch.setenv("PGHOST", "db"); monkeypatch.setenv("PGPORT", "6543")
    cfg = ConnectionConfig.from_env()
    assert (cfg.host, cfg.effective_port, cfg.database) == ("db", 6543, "x")
    assert "password" not in cfg.psycopg_kwargs()      # leaves room for ~/.pgpass


def test_missing_config_raises():
    with pytest.raises(ValueError):
        ConnectionConfig.from_env()


def test_mssql_legacy(monkeypatch):
    monkeypatch.setenv("OB_DB_DIALECT", "mssql"); monkeypatch.setenv("OB_DB_NAME", "MSI")
    monkeypatch.setenv("OB_DB_USER", "sa"); monkeypatch.setenv("OB_DB_PASSWORD", "p;w}d")
    cs = ConnectionConfig.from_env().odbc_connection_string()
    assert "SERVER=localhost,1433" in cs and "PWD={p;w}}d}" in cs


def test_bad_dialect(monkeypatch):
    monkeypatch.setenv("OB_DB_DIALECT", "oracle"); monkeypatch.setenv("OB_DB_NAME", "x")
    with pytest.raises(ValueError):
        ConnectionConfig.from_env()


# ── runner ───────────────────────────────────────────────────────────────────
def test_destructive_gate(tmp_path, fake_db):
    f = tmp_path / "fix.sql"; f.write_text("BEGIN; UPDATE t SET x=1; COMMIT;")
    with Runner(pg()) as r:
        with pytest.raises(PermissionError):
            r.execute(Script("fix", f))
        assert fake_db.last.executed == []
        r.execute(Script("fix", f), confirm=True)
    assert fake_db.last.executed == ["BEGIN; UPDATE t SET x=1; COMMIT;"]
    assert fake_db.last.autocommit is True


def test_postgres_whole_script_one_batch_all_results(fake_db):
    fake_db.script = {"DRYRUN": [
        {"columns": [f"c{i}"], "rows": [[i]], "notices": ["DRY RUN COMPLETE"] if i == 3 else []}
        for i in range(1, 4)
    ]}
    with Runner(pg()) as r:
        res = r.execute_raw("-- DRYRUN\nBEGIN;\nSELECT 1;\nSELECT 2;\nSELECT 3;\nROLLBACK;")
    assert len(fake_db.last.executed) == 1
    assert [x.columns for x in res] == [["c1"], ["c2"], ["c3"]]
    assert res[-1].messages == ["DRY RUN COMPLETE"]


def test_psql_meta_rejected_before_sending(fake_db):
    with Runner(pg()) as r:
        res = r.execute_raw("SELECT 1;\n\\gexec\n")
    assert not res[0].ok and "line 2" in res[0].error and fake_db.last.executed == []


def test_error_rolls_back_and_logs(fake_db, monkeypatch):
    monkeypatch.setenv("OB_AUTHOR_NAME", "sara")
    fake_db.script = {"BAD": FakeDBError('column "nope" does not exist', "42703")}
    with Runner(pg(), label="demo:1001/fix") as r:
        res = r.execute_raw("BEGIN; SELECT BAD;\n-- @batch\nSELECT 3;")
    sent = fake_db.last.executed
    assert sent[0] == "BEGIN; SELECT BAD;"
    assert sent[1] == "ROLLBACK"
    sql, params = sent[2]
    assert sql.startswith("INSERT INTO err.db_exception_tank")
    assert params[0] == "sara" and params[1] == "42703" and params[3] == "demo:1001/fix"
    assert len(sent) == 3                                   # stop_on_error: batch 2 never ran
    assert res[-1].error.startswith("[42703]")


def test_continue_on_error_and_no_error_table(fake_db, monkeypatch):
    monkeypatch.setenv("OB_DB_ERROR_TABLE", "")
    fake_db.script = {"BAD": FakeDBError("boom")}
    with Runner(pg(), stop_on_error=False) as r:
        r.execute_raw("SELECT BAD;\n-- @batch\nSELECT 3;")
    assert fake_db.last.executed == ["SELECT BAD;", "ROLLBACK", "SELECT 3;"]


def test_mssql_go_and_print(fake_db):
    fake_db.script = {"PRINTME": [{"columns": ["a"], "rows": [[1]], "messages": ["hello"]}]}
    with Runner("DRIVER={x};") as r:
        res = r.execute_raw("SELECT 1 -- PRINTME\nGO\nSELECT 2\nGO")
    assert len(fake_db.last.executed) == 2 and res[0].messages == ["hello"]


def test_rowcount_result(fake_db):
    fake_db.script = {"UPDATE": [{"rowcount": 3}]}
    with Runner(pg()) as r:
        res = r.execute_raw("UPDATE t SET x = 1;")
    assert res[0].rows_affected == 3 and res[0].columns == []


# ── scaffold ─────────────────────────────────────────────────────────────────
def test_fill_tokens_leaves_unknown():
    assert fill_tokens("{{A}} {{B}}", {"A": "1"}) == "1 {{B}}"


def test_scaffold_uses_tenant_then_builtin(repo):
    root = repo / "packages/core/tenants/demo/scripts"
    report = scaffold_ticket(root, "42", repo / "templates/demo/scaffolds",
                             {"TARGET_TABLE": "demo.policy", "AUTHOR_NAME": "me"})
    assert sorted(report) == ["diagnostic.sql", "dryrun.sql", "fix.sql", "rollback.sql", "runbook.md"]
    assert (root / "42/diagnostic.sql").read_text().startswith("-- 42 on demo.policy")
    assert "Ticket 42 by me" in (root / "42/runbook.md").read_text()
    assert "ROLLBACK;  -- COMMIT;" in (root / "42/fix.sql").read_text()     # postgres built-in
    assert "GO" not in (root / "42/fix.sql").read_text()
    with pytest.raises(FileExistsError):
        scaffold_ticket(root, "42")
    t = Ticket("42", root / "42", "demo")
    assert t.has_runbook and t.script_names == ["diagnostic", "dryrun", "fix", "rollback"]


def test_scaffold_mssql_builtin(tmp_path):
    scaffold_ticket(tmp_path, "7", dialect="mssql")
    assert "GO" in (tmp_path / "7/fix.sql").read_text()


# ── CLI ──────────────────────────────────────────────────────────────────────
def test_cli_end_to_end(repo, monkeypatch, capsys, fake_db):
    monkeypatch.setenv("OB_DB_USER", "ob_dba")
    assert main(["--tenant", "demo", "scaffold", "42", "-t", "TARGET_TABLE=demo.policy"]) == 0
    assert main(["--tenant", "demo", "tickets"]) == 0
    assert "demo:42" in capsys.readouterr().out
    assert main(["--tenant", "demo", "run", "42", "fix"]) == 3            # gated, no connection made
    assert fake_db.connections == []
    fake_db.script = {"SELECT 1": [{"columns": ["one"], "rows": [[1]]}]}
    assert main(["--tenant", "demo", "run", "42", "diagnostic", "--csv", str(repo / "out")]) == 0
    assert list((repo / "out").glob("*.csv"))
    assert main(["--tenant", "demo", "config"]) == 0
    assert "postgres://localhost:5432/ob_demo" in capsys.readouterr().out


def test_cli_sandbox_clones_and_drops(repo, monkeypatch, fake_db):
    monkeypatch.setenv("OB_DB_USER", "ob_dba")
    main(["--tenant", "demo", "scaffold", "42"])
    assert main(["--tenant", "demo", "run", "42", "fix", "--yes", "--sandbox"]) == 0
    sql = fake_db.all_sql()
    create = next(s for s in sql if s.startswith("CREATE DATABASE"))
    assert 'TEMPLATE "ob_demo"' in create and '"ob_demo__sbx_' in create
    assert sql[-1].startswith("DROP DATABASE IF EXISTS") and "WITH (FORCE)" in sql[-1]
    # the script itself ran against the clone, not ob_demo
    script_conn = [c for c in fake_db.connections if c.kwargs.get("dbname", "").startswith("ob_demo__sbx_")]
    assert script_conn and script_conn[0].executed[0].startswith("-- Ticket 42 | Fix")
    assert not any(c.kwargs.get("dbname") == "ob_demo" for c in fake_db.connections)


def test_cli_import_shell_package(repo, monkeypatch, tmp_path, capsys):
    home = tmp_path / "home"
    pkg = home / ".onboarded/demo/tickets/77-package"
    pkg.mkdir(parents=True)
    (pkg / "README.md").write_text("# 77")
    (pkg / "dryrun-77.sql").write_text("BEGIN; ROLLBACK;")
    (pkg / "fix.sql").write_text("BEGIN; ROLLBACK;  -- COMMIT;")
    monkeypatch.setenv("HOME", str(home))
    assert main(["--tenant", "demo", "import", "77"]) == 0
    dest = repo / "packages/core/tenants/demo/scripts/77"
    assert sorted(p.name for p in dest.iterdir()) == ["dryrun.sql", "fix.sql", "runbook.md"]
    assert main(["--tenant", "demo", "import", "77"]) == 2          # no clobber without --force
