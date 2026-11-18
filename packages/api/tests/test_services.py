"""Service layer — framework-free, runs without FastAPI installed."""
from __future__ import annotations

import json
import re

import pytest

from onboarded_api import schemas
from onboarded_api.errors import BadRequest, Forbidden, NotFound
from onboarded_api.services.scan_service import run_scan as run_scan_core
from onboarded_api.services import lookup, scanner
from onboarded_api.services.domain_store import DomainStore

from conftest import REPO

TENANTS = ("generic", "msi", "flotilla")


# ── DomainStore ─────────────────────────────────────────────────────────────

def test_loads_every_committed_tenant(store):
    assert set(TENANTS) <= set(store.slugs)
    assert store.errors == {}


@pytest.mark.parametrize("slug", TENANTS)
def test_view_has_every_required_collection(store, slug):
    v = store.view(slug)
    for k in ("operations", "statuses", "products", "portals", "queues", "glossary", "scanRules"):
        assert isinstance(v[k], dict), k
    assert v["tenant"]["brandName"] and v["tenant"]["slug"] == slug


@pytest.mark.parametrize("slug", TENANTS)
def test_api_view_equals_generated_ts_snapshot(store, slug):
    """Portal build-time data and API runtime data must be the same object."""
    ts = (REPO / "packages/shared/src/lib/tenants" / f"{slug}.ts").read_text(encoding="utf-8")
    body = re.search(r"TENANT_DOMAIN: TenantDomain = (\{.*\});\s*$", ts, re.S).group(1)
    assert json.loads(body) == store.view(slug), \
        "stale snapshot — run: npm run generate:ts"


def test_unknown_tenant_is_not_found(store):
    with pytest.raises(NotFound, match="loaded:"):
        store.view("nope")


def test_broken_domain_is_reported_not_fatal(tmp_path, settings):
    (tmp_path / "t" / "good" / "domain").mkdir(parents=True)
    (tmp_path / "t" / "bad" / "domain").mkdir(parents=True)
    (tmp_path / "t" / "good" / "domain" / "domain.json").write_text(
        json.dumps({"version": "1", "tenant": {"slug": "good"}}))
    (tmp_path / "t" / "bad" / "domain" / "domain.json").write_text("{not json")
    s = DomainStore(tmp_path / "t", settings.core_scripts).load()
    assert s.slugs == ["good"] and "bad" in s.errors
    assert s.view("good")["queues"] == {}


@pytest.mark.parametrize("slug", TENANTS)
def test_summaries_validate_against_schema(store, slug):
    schemas.TenantSummary.model_validate(store.summary(slug))


# ── lookups ─────────────────────────────────────────────────────────────────

def test_where_exact_operation_includes_code_path(store):
    r = lookup.where(store.view("msi"), "bind")
    assert r["matches"][0] == {"kind": "operation", "id": "bind", "label": r["matches"][0]["label"], "exact": True}
    assert r["operation"]["codePath"].startswith("Code path")
    schemas.WhereResult.model_validate(r)


def test_where_fuzzy_falls_back_to_substring(store):
    r = lookup.where(store.view("flotilla"), "mission")
    assert r["matches"] and not any(m["exact"] for m in r["matches"])
    assert all(m["kind"] in ("operation", "product") for m in r["matches"])


def test_where_no_match(store):
    assert lookup.where(store.view("generic"), "zzzz")["matches"] == []


def test_search_operations_matches_paths(store):
    hits = lookup.search_operations(store.view("generic"), "CreateController")
    assert [h["id"] for h in hits] == ["create"]
    for h in lookup.search_operations(store.view("msi"), None):
        schemas.Operation.model_validate(h)


def test_statuses_sorted_numerically_with_triggers(store):
    codes = [s["code"] for s in lookup.list_statuses(store.view("msi"))]
    assert codes == sorted(codes, key=int)
    assert any(s["trigger"] for s in lookup.list_statuses(store.view("msi")))


def test_statuses_non_numeric_codes(store):
    items = lookup.list_statuses(store.view("flotilla"), "pending")
    assert items and all("pending" in (s["code"] + s["description"]).lower() for s in items)


def test_glossary_search_and_schema(store):
    hits = lookup.search_glossary(store.view("msi"), "quote")
    assert any(h["id"] == "bind" for h in hits)
    for h in hits:
        schemas.GlossaryTerm.model_validate(h)


# ── scanner ─────────────────────────────────────────────────────────────────

def _scan(store, settings, **body):
    return run_scan_core("generic", schemas.ScanRequest(**body), store, settings)


def test_scan_inline_content_finds_violations(store, settings):
    text = (REPO / "packages/cli/tests/fixtures/scan_fixtures/ViolationService.cs").read_text()
    r = _scan(store, settings, content={"filename": "src/ViolationService.cs", "text": text})
    ids = {f["ruleId"] for f in r["findings"]}
    assert {"hardcoded_secret", "direct_db_connection", "missing_cancellation_token", "todo_comment"} <= ids
    assert r["exitCode"] == 1 and r["findings"][0]["severity"] == "critical"
    schemas.ScanReport.model_validate(r)


def test_scan_paths_respects_scope_and_exclude(store, settings, scan_root):
    r = _scan(store, settings, paths=[str(scan_root)])
    files = {f["file"] for f in r["findings"]}
    assert "app/ViolationService.cs" in files
    # **/tests/** excludes every rule that declares it; todo_comment declares no excludes
    assert {f["ruleId"] for f in r["findings"] if f["file"].startswith("app/tests/")} == {"todo_comment"}
    assert not any(f.endswith("PolicyService.clean.cs") for f in files)


def test_scan_clean_file_exit_zero(store, settings, scan_root):
    r = _scan(store, settings, paths=[str(scan_root / "app" / "PolicyService.clean.cs")])
    assert r["summary"]["total"] == 0 and r["exitCode"] == 0 and r["filesScanned"] == 1


def test_scan_min_severity_and_rule_filter(store, settings, scan_root):
    r = _scan(store, settings, paths=[str(scan_root / "app")], minSeverity="error")
    assert {f["severity"] for f in r["findings"]} <= {"critical", "error"}
    r = _scan(store, settings, paths=[str(scan_root / "app")], ruleIds=["todo_comment"])
    assert {f["ruleId"] for f in r["findings"]} == {"todo_comment"} and r["exitCode"] == 3


def test_scan_refuses_paths_outside_roots(store, settings, scan_root):
    for bad in ("/etc/passwd", str(scan_root / ".." / "elsewhere")):
        with pytest.raises(Forbidden):
            _scan(store, settings, paths=[bad])


def test_scan_refuses_symlink_escape(store, settings, scan_root, tmp_path):
    secret = tmp_path / "secret.cs"
    secret.write_text('string password = "hunter22";')
    (scan_root / "app" / "link.cs").symlink_to(secret)
    r = _scan(store, settings, paths=[str(scan_root / "app")])
    assert not any("link.cs" in f["file"] for f in r["findings"])


def test_scan_requires_input_and_known_rules(store, settings):
    with pytest.raises(BadRequest):
        _scan(store, settings)
    with pytest.raises(BadRequest, match="Unknown rule"):
        _scan(store, settings, content={"filename": "a.cs", "text": ""}, ruleIds=["nope"])


@pytest.mark.parametrize("sev,code", [([], 0), (["critical", "info"], 1), (["error", "warning"], 2),
                                      (["warning"], 3), (["info"], 3)])
def test_exit_code_contract(sev, code):
    assert scanner.exit_code([{"severity": s} for s in sev]) == code


@pytest.mark.parametrize("path,pat,hit", [
    ("tests/a.cs", "**/tests/**", True), ("x/tests/a.cs", "**/tests/**", True),
    ("x/testsuite/a.cs", "**/tests/**", False), ("db/migrations/1.cs", "**/migrations/**", True),
    # directory boundaries: a folder that merely ends in the name must not match
    ("scan_fixtures/a.cs", "**/fixtures/**", False), ("unit_tests/a.cs", "**/tests/**", False),
    ("fixtures/a.cs", "**/fixtures/**", True), ("a/b/fixtures/c/d.cs", "**/fixtures/**", True),
    ("src/a.spec.ts", "*.spec.ts", True), ("src/a/b.ts", "src/*.ts", False), ("x/src/b.ts", "src/*.ts", True),
])
def test_exclude_globs(path, pat, hit):
    assert scanner._glob_match(path, pat) is hit
