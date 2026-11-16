"""HTTP layer — needs fastapi + httpx (pip install -e '.[test]'). Skipped otherwise."""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from onboarded_api.main import create_app  # noqa: E402


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and {"generic", "msi", "flotilla"} <= set(body["tenants"])


def test_tenants_list_and_detail(client):
    slugs = [t["slug"] for t in client.get("/api/v1/tenants").json()]
    assert "flotilla" in slugs
    assert client.get("/api/v1/tenants/msi").json()["brandName"] == "Onboarded.MSI"


def test_domain_view_is_camel_case(client):
    d = client.get("/api/v1/tenants/generic/domain").json()
    assert "scanRules" in d and "scan_rules" not in d and d["queues"] == {}


def test_unknown_tenant_problem_json(client):
    r = client.get("/api/v1/tenants/nope/operations")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["title"] == "Not found"


def test_operations_query_and_detail(client):
    assert [o["id"] for o in client.get("/api/v1/tenants/generic/operations?q=create").json()] == ["create"]
    assert client.get("/api/v1/tenants/msi/operations/bind").json()["id"] == "bind"
    assert client.get("/api/v1/tenants/msi/operations/zzz").status_code == 404


def test_where_status_glossary(client):
    assert client.get("/api/v1/tenants/msi/where/bind").json()["operation"]["id"] == "bind"
    assert client.get("/api/v1/tenants/msi/where/zzzz").status_code == 404
    assert client.get("/api/v1/tenants/msi/statuses/13").json()["code"] == "13"
    assert client.get("/api/v1/tenants/msi/glossary/bind").json()["seeAlso"] is not None


def test_scan_rules_filter(client):
    rules = client.get("/api/v1/tenants/generic/scan-rules?severity=critical").json()
    assert rules and all(r["severity"] == "critical" for r in rules)


def test_scan_inline(client):
    r = client.post("/api/v1/tenants/generic/scan",
                    json={"content": {"filename": "a.cs", "text": 'var password = "hunter22";'}})
    assert r.status_code == 200 and r.json()["exitCode"] == 1


def test_scan_forbidden_path(client):
    r = client.post("/api/v1/tenants/generic/scan", json={"paths": ["/etc"]})
    assert r.status_code == 403


def test_validation_error_is_problem_json(client):
    r = client.post("/api/v1/tenants/generic/scan", json={"minSeverity": "loud"})
    assert r.status_code == 422 and r.json()["title"] == "Invalid request"


def test_reload(client):
    assert "msi" in client.post("/api/v1/admin/reload").json()["tenants"]


# ── DBA (PR-10) ──────────────────────────────────────────────────────────────

def test_tickets_and_script(client):
    ids = [t["id"] for t in client.get("/api/v1/tenants/flotilla/tickets").json()]
    assert "2001" in ids
    assert client.get("/api/v1/tenants/flotilla/tickets/2001").json()["runbook"]
    assert client.get("/api/v1/tenants/flotilla/tickets/2001/scripts/dryrun").json()["sql"]


def test_run_forbidden_when_exec_disabled(client):
    r = client.post("/api/v1/tenants/generic/tickets/1001/scripts/diagnostic/run", json={})
    assert r.status_code == 403


def test_run_destructive_needs_confirm_header(settings):
    import dataclasses
    app = create_app(dataclasses.replace(settings, dba_exec=True))
    with TestClient(app) as c:
        r = c.post("/api/v1/tenants/generic/tickets/1001/scripts/fix/run", json={})
        assert r.status_code == 428 and "1001/fix" in r.json()["detail"]


def test_instances(client):
    assert any(i["slug"] == "flotilla" for i in client.get("/api/v1/instances").json())
    assert client.get("/api/v1/instances/nope").status_code == 404
