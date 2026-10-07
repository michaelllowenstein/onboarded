"""
dba.scaffold — Ticket directory templating (5-file standard layout).

    <scripts_root>/<ticket_id>/
        diagnostic.sql  dryrun.sql  fix.sql  rollback.sql  runbook.md

Templates come from the tenant's scaffold directory
(templates/<slug>/scaffolds/ by convention). A scaffold README.md becomes
the ticket's runbook.md. When a tenant has no scaffold for a file, a
minimal built-in skeleton in the tenant's dialect is written instead, so a brand-new tenant
can still produce a usable ticket directory.

Tokens use the same {{TOKEN}} syntax as the shell engine. Unfilled tokens
are left in place and reported, never silently blanked.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from dba.models import STANDARD_SCRIPTS

_TOKEN = re.compile(r"\{\{([A-Z_]+)\}\}")

_RUNBOOK = ("# Ticket {{TICKET_ID}}\n\n**Target table:** {{TARGET_TABLE}}\n\n"
            "1. diagnostic\n2. dryrun (all gates PASS)\n3. fix --sandbox, then fix --yes\n4. rollback if needed\n")

_BUILTIN = {
    "postgres": {
        "diagnostic": (
            "-- Ticket {{TICKET_ID}} | Diagnostic (read only)\n"
            "-- Target: {{TARGET_TABLE}}\n"
            "SELECT column_name, data_type, is_nullable\n"
            "FROM   information_schema.columns\n"
            "WHERE  table_schema = split_part('{{TARGET_TABLE}}', '.', 1)\n"
            "  AND  table_name   = split_part('{{TARGET_TABLE}}', '.', 2)\n"
            "ORDER  BY ordinal_position;\n"
        ),
        "dryrun": (
            "-- Ticket {{TICKET_ID}} | Dry run — always rolls back\n"
            "BEGIN;\n-- RS1: before\n-- simulated change\n-- RS2: after\n-- RS3: gates (all PASS)\n"
            "ROLLBACK;\n"
        ),
        "fix": (
            "-- Ticket {{TICKET_ID}} | Fix — ships with ROLLBACK active.\n"
            "-- To apply: swap the last line to COMMIT, then run with --yes.\n"
            "BEGIN;\n-- guard (DO $$ ... RAISE EXCEPTION ... $$;)\n-- change\n-- verification\n"
            "ROLLBACK;  -- COMMIT;\n"
        ),
        "rollback": (
            "-- Ticket {{TICKET_ID}} | Rollback — restore values captured in dryrun RS1\n"
            "BEGIN;\n-- restore\nROLLBACK;  -- COMMIT;\n"
        ),
        "runbook": _RUNBOOK,
    },
    "mssql": {
        "diagnostic": (
            "-- Ticket {{TICKET_ID}} | Diagnostic (read only)\n"
            "-- Target: {{TARGET_TABLE}}\n"
            "SELECT c.column_id, c.name AS ColumnName, t.name AS TypeName, c.is_nullable\n"
            "FROM   sys.columns c JOIN sys.types t ON t.user_type_id = c.user_type_id\n"
            "WHERE  c.object_id = OBJECT_ID(N'{{TARGET_TABLE}}')\nORDER  BY c.column_id;\nGO\n"
        ),
        "dryrun": (
            "-- Ticket {{TICKET_ID}} | Dry run — always rolls back\n"
            "SET XACT_ABORT ON;\nBEGIN TRANSACTION;\n"
            "    -- RS1: before\n    -- simulated change\n    -- RS2: after\n"
            "ROLLBACK TRANSACTION;\nPRINT N'DRY RUN COMPLETE — database unchanged.';\nGO\n"
        ),
        "fix": (
            "-- Ticket {{TICKET_ID}} | Fix — ROLLBACK active, COMMIT commented out\n"
            "SET XACT_ABORT ON;\nBEGIN TRANSACTION;\n    -- change goes here\n"
            "-- COMMIT TRANSACTION;\nROLLBACK TRANSACTION;\nGO\n"
        ),
        "rollback": (
            "-- Ticket {{TICKET_ID}} | Rollback — restore values captured in dryrun RS1\n"
            "SET XACT_ABORT ON;\nBEGIN TRANSACTION;\n    -- restore goes here\n"
            "-- COMMIT TRANSACTION;\nROLLBACK TRANSACTION;\nGO\n"
        ),
        "runbook": _RUNBOOK,
    },
}


def fill_tokens(text: str, tokens: dict[str, str]) -> str:
    def sub(m: re.Match) -> str:
        val = tokens.get(m.group(1))
        return m.group(0) if val in (None, "") else str(val)
    return _TOKEN.sub(sub, text)


def unfilled_tokens(text: str) -> list[str]:
    return sorted(set(_TOKEN.findall(text)))


def scaffold_ticket(
    scripts_root: Path,
    ticket_id: str,
    scaffold_dir: Optional[Path] = None,
    tokens: Optional[dict[str, str]] = None,
    overwrite: bool = False,
    dialect: str = "postgres",
) -> dict[str, list[str]]:
    """Create <scripts_root>/<ticket_id>/ with the 5 standard files.

    Returns {relative_filename: [unfilled tokens]} for every file written.
    Raises FileExistsError if the ticket dir exists and overwrite is False.
    """
    tokens = {"TICKET_ID": ticket_id, **(tokens or {})}
    ticket_dir = Path(scripts_root) / ticket_id
    if ticket_dir.exists() and any(ticket_dir.iterdir()) and not overwrite:
        raise FileExistsError(f"{ticket_dir} already exists (use overwrite=True / --force)")
    ticket_dir.mkdir(parents=True, exist_ok=True)

    report: dict[str, list[str]] = {}
    for name in (*STANDARD_SCRIPTS, "runbook"):
        src_text = None
        if scaffold_dir:
            candidates = [Path(scaffold_dir) / ("README.md" if name == "runbook" else f"{name}.sql")]
            if name == "runbook":
                candidates.insert(0, Path(scaffold_dir) / "runbook.md")
            for c in candidates:
                if c.is_file():
                    src_text = c.read_text(encoding="utf-8")
                    break
        if src_text is None:
            src_text = _BUILTIN.get(dialect, _BUILTIN["postgres"])[name]
        out_name = "runbook.md" if name == "runbook" else f"{name}.sql"
        filled = fill_tokens(src_text, tokens)
        (ticket_dir / out_name).write_text(filled, encoding="utf-8")
        report[out_name] = unfilled_tokens(filled)
    return report
