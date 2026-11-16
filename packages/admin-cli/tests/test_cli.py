"""ob-admin end to end. Local backend runs against the real repo; HTTP backend against a stub API."""
from __future__ import annotations

import json
import shutil
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from onboarded_admin.cli import main

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "packages/cli/tests/fixtures/scan_fixtures"


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    for k in ("OB_TENANT", "OB_API_URL", "OB_REPO_ROOT", "OB_DB_NAME"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("OB_HOME", str(tmp_path / "home"))
    monkeypatch.chdir(REPO)


def run(capsys, *args):
    code = main(["--local", *args])
    out = capsys.readouterr()
    return code, out.out, out.err


def jrun(capsys, *args):
    code, out, _ = run(capsys, "--json", *args)
    return code, json.loads(out)


# ── local backend ───────────────────────────────────────────────────────────

def test_health_and_tenants(capsys):
    code, h = jrun(capsys, "health")
    assert code == 0 and {"generic", "msi", "flotilla"} <= set(h["tenants"])
    code, out, _ = run(capsys, "tenants")
    assert code == 0 and "flotilla" in out and "SLUG" in out


def test_default_tenant_from_active_marker(capsys, tmp_path):
    (tmp_path / "home").mkdir()
    (tmp_path / "home" / "active").write_text("flotilla")
    code, t = jrun(capsys, "tenant")
    assert t["slug"] == "flotilla"


def test_where_human_output(capsys):
    code, out, _ = run(capsys, "-t", "msi", "where", "bind")
    assert code == 0 and "Controllers" in out and "Code path" in out


def test_where_not_found_exit_4(capsys):
    code, _, err = run(capsys, "where", "zzzz")
    assert code == 4 and "Nothing matches" in err


def test_unknown_tenant_exit_4(capsys):
    assert run(capsys, "-t", "nope", "ops")[0] == 4


def test_status_explain_ops(capsys):
    code, items = jrun(capsys, "-t", "msi", "status", "13")
    assert code == 0 and items[0]["code"] == "13"
    assert run(capsys, "-t", "msi", "status", "999")[0] == 4
    code, items = jrun(capsys, "-t", "msi", "explain", "bind")
    assert items[0]["id"] == "bind"
    code, items = jrun(capsys, "ops", "-q", "create")
    assert [o["id"] for o in items] == ["create"]


def test_domain_is_camel_case(capsys):
    code, d = jrun(capsys, "-t", "flotilla", "domain")
    assert "scanRules" in d and d["tenant"]["brandName"].startswith("Equinor")


@pytest.mark.parametrize("fixture,expected", [
    ("ViolationService.cs", 1), ("PolicyService.clean.cs", 0)])
def test_scan_exit_codes(capsys, tmp_path, fixture, expected):
    shutil.copy2(FIXTURES / fixture, tmp_path / fixture)
    code, out, _ = run(capsys, "scan", str(tmp_path / fixture))
    assert code == expected
    assert ("clean" in out) == (expected == 0)


def test_scan_directory_with_rule_filter(capsys, tmp_path):
    for f in FIXTURES.iterdir():
        shutil.copy2(f, tmp_path / f.name)
    code, r = jrun(capsys, "scan", str(tmp_path), "-r", "todo_comment")
    assert code == 3 and {f["ruleId"] for f in r["findings"]} == {"todo_comment"}


def test_scan_unknown_rule_exit_5(capsys, tmp_path):
    (tmp_path / "a.cs").write_text("")
    assert run(capsys, "scan", str(tmp_path), "-r", "nope")[0] == 5


def test_tickets_ticket_sql(capsys):
    code, out, _ = run(capsys, "-t", "flotilla", "tickets")
    assert code == 0 and "flotilla:2001" in out and "⚠fix" in out
    code, out, _ = run(capsys, "-t", "flotilla", "ticket", "2001")
    assert "runbook" not in out.lower() or "#" in out
    code, out, _ = run(capsys, "-t", "generic", "sql", "1001", "diagnostic")
    assert code == 0 and "select" in out.lower()


def test_run_destructive_without_yes_exit_7(capsys):
    code, _, err = run(capsys, "-t", "generic", "run", "1001", "fix")
    assert code == 7 and "--yes" in err


def test_instances(capsys):
    code, items = jrun(capsys, "instances")
    assert code == 0 and any(i["slug"] == "flotilla" for i in items)


def test_json_error_envelope(capsys):
    code, out, _ = run(capsys, "--json", "where", "zzzz")
    assert code == 4 and json.loads(out)["error"] == "not_found"


# ── HTTP backend (stub API) ─────────────────────────────────────────────────

class _Stub(BaseHTTPRequestHandler):
    seen: list = []

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        _Stub.seen.append(("GET", self.path, dict(self.headers)))
        if self.path == "/health":
            return self._send(200, {"status": "ok", "version": "0.1.0", "tenants": ["generic"],
                                    "errors": {}, "features": {"dba": True, "dbaExec": False}})
        if self.path.startswith("/api/v1/tenants/generic/operations?q=cre"):
            return self._send(200, [{"id": "create", "label": "Create"}])
        self._send(404, {"type": "about:blank", "title": "Not found", "status": 404, "detail": "nope here"},
                   "application/problem+json")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        _Stub.seen.append(("POST", self.path, dict(self.headers), body))
        if self.path.endswith("/run"):
            if self.headers.get("X-Onboarded-Confirm") != "1001/fix":
                return self._send(428, {"title": "Confirmation required", "status": 428, "detail": "confirm"})
            return self._send(200, {"label": "generic:1001/fix", "mode": "sandbox", "target": "x",
                                    "ok": True, "results": []})
        self._send(403, {"title": "Forbidden", "status": 403, "detail": "outside roots"})


@pytest.fixture
def api():
    srv = HTTPServer(("127.0.0.1", 0), _Stub)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    _Stub.seen = []
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_http_health_and_query(api, capsys):
    assert main(["--api", api, "health"]) == 0
    assert "✔ ok" in capsys.readouterr().out
    assert main(["--api", api, "--json", "ops", "-q", "cre"]) == 0
    assert json.loads(capsys.readouterr().out) == [{"id": "create", "label": "Create"}]
    assert any(s[1] == "/api/v1/tenants/generic/operations?q=cre" for s in _Stub.seen)


def test_http_problem_maps_to_exit_codes(api, capsys):
    assert main(["--api", api, "where", "x"]) == 4
    assert "nope here (HTTP 404)" in capsys.readouterr().err
    assert main(["--api", api, "scan", "/etc"]) == 7


def test_http_confirm_header_sent_only_with_yes(api, capsys):
    assert main(["--api", api, "run", "1001", "fix"]) == 7
    assert main(["--api", api, "run", "1001", "fix", "--yes"]) == 0
    posts = [s for s in _Stub.seen if s[0] == "POST"]
    assert "X-Onboarded-Confirm" not in posts[0][2] and posts[1][3] == {"sandbox": True, "maxRows": 200}


def test_http_unreachable_exit_6(capsys):
    assert main(["--api", "http://127.0.0.1:9", "health"]) == 6
