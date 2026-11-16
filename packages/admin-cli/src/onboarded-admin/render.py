"""Human output. Plain text, ANSI colour only when stdout is a TTY and NO_COLOR is unset."""

from __future__ import annotations

import json
import os
import sys
from typing import Any

_COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
SEV_COLOR = {"critical": "31;1", "error": "31", "warning": "33", "info": "36"}


def _c(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m" if _COLOR else s


def bold(s): return _c("1", s)
def dim(s): return _c("2", s)
def err(s): return _c("31", f"✖ {s}")


def as_json(x: Any) -> str:
    return json.dumps(x, indent=2, ensure_ascii=False)


def _table(rows: list[list[str]], header: list[str] | None = None) -> str:
    if not rows:
        return dim("(none)")
    allr = ([header] if header else []) + rows
    w = [max(len(str(r[i])) for r in allr) for i in range(len(allr[0]))]
    fmt = lambda r: "  ".join(str(v).ljust(w[i]) for i, v in enumerate(r)).rstrip()  # noqa: E731
    out = [bold(fmt(header))] if header else []
    return "\n".join(out + [fmt(r) for r in rows])


def health(h):
    mark = _c("32", "✔ ok") if h["status"] == "ok" else _c("33", "▲ degraded")
    lines = [f"{mark}  v{h['version']}  tenants: {', '.join(h['tenants']) or '-'}"]
    lines += [err(f"{k}: {v}") for k, v in h.get("errors", {}).items()]
    f = h.get("features", {})
    lines.append(dim(f"dba: {'on' if f.get('dba') else 'off'} · exec: {'on' if f.get('dbaExec') else 'off'}"))
    return "\n".join(lines)


def tenants(items):
    return _table([[t["slug"], t["brandName"], t["version"], t["counts"]["operations"],
                    t["counts"]["scanRules"], t.get("database") or "-"] for t in items],
                  ["SLUG", "BRAND", "VERSION", "OPS", "RULES", "DATABASE"])


def tenant(t):
    rows = [["slug", t["slug"]], ["brand", t["brandName"]], ["cli", t["cliName"]],
            ["version", t["version"]], ["database", f"{t.get('dialect') or '-'}:{t.get('database') or '-'}"]]
    rows += [[k, str(v)] for k, v in t["counts"].items()]
    return _table(rows)


def operations(items):
    return _table([[o["id"], o["label"]] for o in items], ["ID", "LABEL"])


def _paths(title: str, items: list[str]) -> list[str]:
    return [bold(title)] + [f"  {p}" for p in items] if items else []


def where(r):
    if "operation" in r:
        o = r["operation"]
        out = [bold(f"{o['id']}  —  {o['label']}")]
        for t, k in (("Controllers", "controllers"), ("Services", "services"),
                     ("JavaScript", "js"), ("Queues", "queues"), ("Tables", "tables")):
            out += _paths(t, o.get(k) or [])
        if o.get("codePath"):
            out += [bold("Code path"), dim(f"  {o['codePath']}")]
        others = [m for m in r["matches"] if not (m["kind"] == "operation" and m["id"] == o["id"])]
        if others:
            out += ["", dim("also: " + ", ".join(f"{m['kind']}:{m['id']}" for m in others))]
        return "\n".join(out)
    return _table([[m["kind"], m["id"], m["label"], "exact" if m["exact"] else "~"] for m in r["matches"]],
                  ["KIND", "ID", "LABEL", ""])


def statuses(items):
    return _table([[s["code"], s["description"]] + ([dim(s["trigger"])] if s.get("trigger") else [""])
                   for s in items], ["CODE", "DESCRIPTION", "TRIGGER"])


def glossary(items):
    out = []
    for g in items:
        out.append(f"{bold(g['label'])} {dim('(' + g['id'] + ')')}")
        out.append(f"  {g['definition']}")
        if g.get("seeAlso"):
            out.append(dim(f"  see also: {', '.join(g['seeAlso'])}"))
    return "\n".join(out) or dim("(none)")


def rules(items):
    return _table([[r["id"], _c(SEV_COLOR.get(r["severity"], "0"), r["severity"]), r["category"],
                    ",".join(r.get("scope") or ["*"])] for r in items],
                  ["RULE", "SEVERITY", "CATEGORY", "SCOPE"])


def scan(r):
    out = []
    for f in r["findings"]:
        sev = _c(SEV_COLOR.get(f["severity"], "0"), f"{f['severity']:<8}")
        out.append(f"{sev} {f['file']}:{f['line']}  {bold(f['ruleId'])}  {dim(f['match'])}")
        if f.get("fixHint"):
            out.append(dim(f"         ↳ {f['fixHint']}"))
    s = r["summary"]
    tail = (f"{r['filesScanned']} file(s) · {s['total']} finding(s) — "
            f"{s['critical']} critical, {s['error']} error, {s['warning']} warning, {s['info']} info")
    out.append(("" if not out else "\n") + (_c("32", "✔ clean · ") + tail if not s["total"] else tail))
    return "\n".join(out)


def tickets(items):
    return _table([[t["label"], " ".join(("⚠" if s["destructive"] else "·") + s["name"] for s in t["scripts"]),
                    "runbook" if t["hasRunbook"] else ""] for t in items], ["TICKET", "SCRIPTS", ""])


def ticket(t):
    out = [bold(t["label"])] + [f"  {'⚠' if s['destructive'] else '·'} {s['label']}" for s in t["scripts"]]
    if t.get("runbook"):
        out += ["", t["runbook"].rstrip()]
    return "\n".join(out)


def run(r):
    out = [dim(f"→ {r['target']}  ·  {r['mode'].upper()}")]
    for rs in r["results"]:
        for m in rs["messages"]:
            out.append(dim(f"  {m}"))
        if rs["error"]:
            out.append(err(rs["error"]))
        elif rs["columns"]:
            out.append(_table([[("NULL" if v is None else str(v)) for v in row] for row in rs["rows"]],
                              rs["columns"]))
            out.append(dim(f"({len(rs['rows'])} row(s))"))
        elif rs["rowsAffected"] >= 0:
            out.append(dim(f"({rs['rowsAffected']} row(s) affected)"))
    out.append(_c("32", "✔ done") if r["ok"] else err("failed"))
    return "\n".join(out)


def instances(items):
    return _table([["▶" if i["active"] else " ", i["slug"], i["status"], i["classification"],
                    f"{i['db'].get('dialect') or '-'}:{i['db'].get('name') or '-'}", i["name"]] for i in items],
                  [" ", "SLUG", "STATUS", "CLASS", "DATABASE", "NAME"])
