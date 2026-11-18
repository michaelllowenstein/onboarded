"""
ScanEngine — runs a tenant's scan_rules over files or an inline snippet.

Same semantics as packages/cli/src/scan/ob_scan_engine.zsh:
  * a rule applies to a file when the file name matches one of its `scope` globs
    (an empty scope means every file) and no `exclude` glob matches its path;
  * findings are reported per line, worst severity first;
  * exit code contract shared with the CLI:
        0 clean · 1 any critical · 2 any error · 3 only warnings/info

Safety: only paths under Settings.scan_roots may be read (resolved, so `..` and
symlinks cannot escape). Inline `content` scanning never touches the disk —
that is what the portal's Live Scan uses.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Iterator

from onboarded_api.errors import BadRequest, Forbidden

SEVERITY_ORDER = {"critical": 0, "error": 1, "warning": 2, "info": 3}
SKIP_DIRS = {".git", "node_modules", "bin", "obj", "dist", ".venv", "__pycache__", ".nx"}


@dataclass
class ScanFinding:
    ruleId: str
    ruleLabel: str
    severity: str
    category: str
    file: str
    line: int
    match: str
    fixHint: str


@dataclass
class _Rule:
    id: str
    label: str
    regex: re.Pattern
    severity: str
    category: str
    scope: list[str]
    exclude: list[str]
    fix_hint: str

    def applies_to(self, rel_path: str) -> bool:
        name = PurePosixPath(rel_path).name
        if self.scope and not any(fnmatch.fnmatch(name, g) for g in self.scope):
            return False
        return not any(_glob_match(rel_path, g) for g in self.exclude)


def _glob_regex(pattern: str) -> re.Pattern:
    """Glob → regex with directory boundaries: `*` and `?` stay inside one segment,
    `**/` spans zero or more whole directories, a trailing `/**` spans the rest."""
    pat = pattern.lstrip("/")
    if not pat.startswith("**"):
        pat = "**/" + pat                   # unanchored patterns match at any depth
    out, i = [], 0
    while i < len(pat):
        if pat.startswith("**/", i):
            token, step = "(?:.*/)?", 3
        elif pat.startswith("**", i):
            token, step = ".*", 2
        elif pat[i] == "*":
            token, step = "[^/]*", 1
        elif pat[i] == "?":
            token, step = "[^/]", 1
        else:
            token, step = re.escape(pat[i]), 1
        out.append(token)
        i += step
    return re.compile("".join(out) + r"\Z")


def _glob_match(path: str, pattern: str) -> bool:
    return _glob_regex(pattern).match(path.lstrip("/")) is not None


def exit_code(findings: Iterable[ScanFinding | dict]) -> int:
    sev = {f["severity"] if isinstance(f, dict) else f.severity for f in findings}
    if "critical" in sev:
        return 1
    if "error" in sev:
        return 2
    if sev & {"warning", "info"}:
        return 3
    return 0


class ScanEngine:
    def __init__(self, scan_rules: dict[str, dict[str, Any]], rule_ids: list[str] | None = None,
                 min_severity: str = "info"):
        if min_severity not in SEVERITY_ORDER:
            raise BadRequest(f"minSeverity must be one of {', '.join(SEVERITY_ORDER)}")
        unknown = sorted(set(rule_ids or []) - set(scan_rules))
        if unknown:
            raise BadRequest(f"Unknown rule id(s): {', '.join(unknown)}")
        limit = SEVERITY_ORDER[min_severity]
        self.rules: list[_Rule] = []
        self.invalid: dict[str, str] = {}
        for rid, r in scan_rules.items():
            if rule_ids and rid not in rule_ids:
                continue
            if SEVERITY_ORDER.get(r.get("severity", "info"), 3) > limit:
                continue
            try:
                rx = re.compile(r.get("pattern", ""))
            except re.error as e:
                self.invalid[rid] = str(e)
                continue
            self.rules.append(_Rule(rid, r.get("label", rid), rx, r.get("severity", "info"),
                                    r.get("category", "convention"), list(r.get("scope") or []),
                                    list(r.get("exclude") or []), r.get("fixHint", "")))

    # ── scanning ───────────────────────────────────────────────────────────
    def scan_text(self, text: str, rel_path: str) -> list[ScanFinding]:
        rules = [r for r in self.rules if r.applies_to(rel_path)]
        out: list[ScanFinding] = []
        if not rules:
            return out
        for lineno, line in enumerate(text.splitlines(), 1):
            for r in rules:
                if r.regex.search(line):
                    out.append(ScanFinding(r.id, r.label, r.severity, r.category, rel_path,
                                           lineno, line.strip()[:200], r.fix_hint))
        return out

    def scan_files(self, files: Iterable[tuple[Path, str]], max_bytes: int) -> tuple[int, list[ScanFinding]]:
        n, findings = 0, []
        for path, rel in files:
            try:
                if path.stat().st_size > max_bytes:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            n += 1
            findings.extend(self.scan_text(text, rel))
        return n, findings


def sort_findings(findings: list[ScanFinding]) -> list[ScanFinding]:
    return sorted(findings, key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), f.file, f.line))


def resolve_scan_paths(paths: list[str], roots: tuple[Path, ...], max_files: int) -> Iterator[tuple[Path, str]]:
    """Yield (absolute file, display path) for every file under `paths`.

    Every requested path must resolve inside one of `roots`; otherwise Forbidden.
    """
    if not roots:
        raise Forbidden("Path scanning is disabled (no scan roots configured; set OB_API_SCAN_ROOTS).")
    resolved_roots = [r.resolve() for r in roots]
    count = 0
    for raw in paths:
        p = Path(raw).expanduser().resolve()
        root = next((r for r in resolved_roots if p == r or r in p.parents), None)
        if root is None:
            raise Forbidden(f"'{raw}' is outside the allowed scan roots.")
        if not p.exists():
            raise BadRequest(f"'{raw}' does not exist.")
        candidates = [p] if p.is_file() else (
            f for f in sorted(p.rglob("*"))
            if f.is_file() and not (SKIP_DIRS & set(f.relative_to(p).parts[:-1]))
        )
        for f in candidates:
            real = f.resolve()
            if not (real == root or root in real.parents):     # symlink escape
                continue
            count += 1
            if count > max_files:
                raise BadRequest(f"More than {max_files} files requested; narrow the paths.")
            yield real, str(real.relative_to(root)).replace("\\", "/")


def report(tenant: str, files_scanned: int, findings: list[ScanFinding]) -> dict[str, Any]:
    findings = sort_findings(findings)
    summary = {s: sum(1 for f in findings if f.severity == s) for s in SEVERITY_ORDER}
    summary["total"] = len(findings)
    return {"tenant": tenant, "filesScanned": files_scanned,
            "findings": [asdict(f) for f in findings], "summary": summary,
            "exitCode": exit_code(findings)}
