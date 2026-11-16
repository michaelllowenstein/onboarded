"""
Two interchangeable backends with one method per CLI command.

HttpBackend   stdlib urllib against the REST API (packages/api).
LocalBackend  imports the API's framework-free service layer and reads the
              repo directly — no server, same answers. Needs onboarded_api
              importable (pip install -e packages/api, or PYTHONPATH).

Both raise CliError(kind, message); cli.py maps `kind` to the exit code.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_API = "http://127.0.0.1:8000"


class CliError(Exception):
    """kind ∈ not_found | bad_request | unavailable | forbidden | confirm"""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind, self.message = kind, message


_STATUS_KIND = {400: "bad_request", 422: "bad_request", 404: "not_found", 403: "forbidden",
                428: "confirm", 503: "unavailable"}


# class HttpBackend:
#     name = "api"

#     def __init__(self, base: str, timeout: float = 30.0):
#         self.base, self.timeout = base.rstrip("/"), timeout

#     def _req(self, method: str, path: str, body: Any = None, headers: dict | None = None,
#              query: dict | None = None) -> Any:
#         url = self.base + path
#         if query:
#             q = {k: v for k, v in query.items() if v not in (None, "")}
#             if q:
#                 url += "?" + urllib.parse.urlencode(q)
#         data = json.dumps(body).encode() if body is not None else None
#         req = urllib.request.Request(url, data=data, method=method, headers={
#             "Accept": "application/json", **({"Content-Type": "application/json"} if data else {}),
#             **(headers or {})})
#         try:
#             with urllib.request.urlopen(req, timeout=self.timeout) as r:
#                 return json.loads(r.read() or b"null")
#         except urllib.error.HTTPError as e:
#             try:
#                 detail = json.loads(e.read()).get("detail", e.reason)
#             except Exception:  # noqa: BLE001
#                 detail = e.reason
#             raise CliError(_STATUS_KIND.get(e.code, "unavailable"), f"{detail} (HTTP {e.code})") from None
#         except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
#             raise CliError("unavailable", f"API not reachable at {self.base}: "
#                                           f"{getattr(e, 'reason', e)}") from None

#     def reachable(self) -> bool:
#         try:
#             with urllib.request.urlopen(self.base + "/health", timeout=0.5):
#                 return True
#         except Exception:  # noqa: BLE001
#             return False

#     # commands
#     def health(self): return self._req("GET", "/health")
#     def tenants(self): return self._req("GET", "/api/v1/tenants")
#     def tenant(self, t): return self._req("GET", f"/api/v1/tenants/{t}")
#     def domain(self, t): return self._req("GET", f"/api/v1/tenants/{t}/domain")
#     def operations(self, t, q=None): return self._req("GET", f"/api/v1/tenants/{t}/operations", query={"q": q})
#     def where(self, t, key): return self._req("GET", f"/api/v1/tenants/{t}/where/{urllib.parse.quote(key, safe='')}")
#     def statuses(self, t, q=None): return self._req("GET", f"/api/v1/tenants/{t}/statuses", query={"q": q})
#     def glossary(self, t, q=None): return self._req("GET", f"/api/v1/tenants/{t}/glossary", query={"q": q})
#     def rules(self, t): return self._req("GET", f"/api/v1/tenants/{t}/scan-rules")
#     def tickets(self, t): return self._req("GET", f"/api/v1/tenants/{t}/tickets")
#     def ticket(self, t, i): return self._req("GET", f"/api/v1/tenants/{t}/tickets/{i}")
#     def script(self, t, i, n): return self._req("GET", f"/api/v1/tenants/{t}/tickets/{i}/scripts/{n}")
#     def instances(self): return self._req("GET", "/api/v1/instances")
#     def reload(self): return self._req("POST", "/api/v1/admin/reload")

#     def scan(self, t, paths, rule_ids=None, min_severity="info"):
#         body = {"paths": [str(Path(p).resolve()) for p in paths], "minSeverity": min_severity}
#         if rule_ids:
#             body["ruleIds"] = rule_ids
#         return self._req("POST", f"/api/v1/tenants/{t}/scan", body=body)

#     def run(self, t, i, n, sandbox, confirm, max_rows):
#         return self._req("POST", f"/api/v1/tenants/{t}/tickets/{i}/scripts/{n}/run",
#                          body={"sandbox": sandbox, "maxRows": max_rows},
#                          headers={"X-Onboarded-Confirm": confirm} if confirm else None)


# class LocalBackend:
#     name = "local"

#     def __init__(self, repo_root: Path | None = None):
#         try:
#             from onboarded_api import errors
#             from onboarded_api.services import lookup, scanner
#             from onboarded_api.services.dba_service import DbaService, InstanceService
#             from onboarded_api.services.domain_store import DomainStore
#             from onboarded_api.settings import Settings, find_repo_root
#         except ImportError as e:
#             raise CliError("unavailable", f"--local needs the API package importable "
#                                           f"(pip install -e packages/api): {e}") from None
#         import dataclasses
#         root = repo_root or find_repo_root(Path.cwd())
#         base = Settings.from_env() if os.environ.get("OB_REPO_ROOT") else Settings(repo_root=root)
#         # Locally the operator owns the machine: SQL execution follows the CLI's own --yes gate.
#         self.settings = dataclasses.replace(base, repo_root=root, dba_exec=True)
#         self._errors, self._lookup, self._scanner = errors, lookup, scanner
#         self.store = DomainStore(self.settings.tenants_dir, self.settings.core_scripts).load()
#         self.dba, self.inst = DbaService(self.settings), InstanceService(self.settings)

#     def _wrap(self, fn, *a, **kw):
#         e = self._errors
#         try:
#             return fn(*a, **kw)
#         except e.NotFound as x:
#             raise CliError("not_found", x.detail) from None
#         except (e.BadRequest,) as x:
#             raise CliError("bad_request", x.detail) from None
#         except e.ConfirmationRequired as x:
#             raise CliError("confirm", x.detail) from None
#         except e.Forbidden as x:
#             raise CliError("forbidden", x.detail) from None
#         except e.Unavailable as x:
#             raise CliError("unavailable", x.detail) from None

#     def health(self):
#         return {"status": "ok" if self.store.slugs and not self.store.errors else "degraded",
#                 "version": "local", "tenants": self.store.slugs, "errors": self.store.errors,
#                 "features": {"dba": True, "dbaExec": True}}

#     def tenants(self): return self.store.summaries()
#     def tenant(self, t): return self._wrap(self.store.summary, t)
#     def domain(self, t): return self._wrap(self.store.view, t)
#     def operations(self, t, q=None): return self._wrap(lambda: self._lookup.search_operations(self.store.view(t), q))
#     def statuses(self, t, q=None): return self._wrap(lambda: self._lookup.list_statuses(self.store.view(t), q))
#     def glossary(self, t, q=None): return self._wrap(lambda: self._lookup.search_glossary(self.store.view(t), q))
#     def rules(self, t): return self._wrap(lambda: [{"id": k, **v} for k, v in self.store.collection(t, "scanRules").items()])
#     def tickets(self, t): return self._wrap(self.dba.tickets, t)
#     def ticket(self, t, i): return self._wrap(self.dba.ticket, t, i)
#     def script(self, t, i, n): return self._wrap(self.dba.script_source, t, i, n)
#     def instances(self): return self.inst.list()

#     def reload(self):
#         self.store.load()
#         return {"tenants": self.store.slugs, "errors": self.store.errors}

#     def where(self, t, key):
#         r = self._wrap(lambda: self._lookup.where(self.store.view(t), key))
#         if not r["matches"]:
#             raise CliError("not_found", f"Nothing matches '{key}' in tenant '{t}'")
#         return r

#     def scan(self, t, paths, rule_ids=None, min_severity="info"):
#         sc = self._scanner

#         def go():
#             engine = sc.ScanEngine(self.store.collection(t, "scanRules"), rule_ids, min_severity)
#             files, findings = 0, []
#             for p in paths:
#                 root = Path(p).resolve()
#                 base = root if root.is_dir() else root.parent    # your own disk: each path is its own root
#                 n, f = engine.scan_files(sc.resolve_scan_paths([str(root)], (base,), self.settings.max_scan_files),
#                                          self.settings.max_scan_bytes)
#                 files += n
#                 findings += f
#             return sc.report(t, files, findings)

#         return self._wrap(go)

#     def run(self, t, i, n, sandbox, confirm, max_rows):
#         return self._wrap(self.dba.run, t, i, n, sandbox=sandbox, confirm=confirm, max_rows=max_rows)
