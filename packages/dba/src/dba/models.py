odels · PY
"""
dba.models — Core data structures for ticket-based SQL scripts.
 
Every script belongs to a ticket, every ticket belongs to a tenant.
The qualified_label encodes the full path: tenant:ticket_id/script_name.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Scripts in the DESTRUCTIVE set require explicit confirmation before execution.
DESTRUCTIVE_SCRIPTS = frozenset({"fix", "rollback"})
 
# Standard file set created by scaffold_ticket().
STANDARD_SCRIPTS = ("diagnostic", "dryrun", "fix", "rollback")

@dataclass
class Script:
    """A single SQL script file within a directory."""

    name: str
    path: Path
    tenant_slug: str = ""
    ticket_id: str = ""
 
    @property
    def qualified_label(self) -> str:
        """Tenant-qualified label: msi:109000/diagnostic"""
        parts = []
        if self.tenant_slug:
            parts.append(f"{self.tenant_slug}:")
        if self.ticket_id:
            parts.append(f"{self.ticket_id}/")
        parts.append(self.name)
        return "".join(parts)
 
    def read(self) -> str:
        """Read the script content from disk."""
        return self.path.read_text(encoding="utf-8")

@dataclass
class Ticket:
    """A ticket directory containing SQL scripts and an optional runbook."""
 
    id: str
    path: Path
    tenant_slug: str = ""
    scripts: dict[str, Script] = field(default_factory=dict)
 
    def __post_init__(self) -> None:
        if not self.scripts:
            self._discover_scripts()
 
    def _discover_scripts(self) -> None:
        """Scan the ticket directory for .sql files and runbook.md."""
        if not self.path.is_dir():
            return
        for f in sorted(self.path.iterdir()):
            if f.suffix == ".sql":
                name = f.stem
                self.scripts[name] = Script(
                    name=name,
                    path=f,
                    tenant_slug=self.tenant_slug,
                    ticket_id=self.id,
                )
 
    def get_script(self, name: str) -> Optional[Script]:
        return self.scripts.get(name)
 
    @property
    def has_runbook(self) -> bool:
        return (self.path / "runbook.md").exists()
 
    @property
    def script_names(self) -> list[str]:
        return sorted(self.scripts.keys())
 
    @property
    def qualified_label(self) -> str:
        prefix = f"{self.tenant_slug}:" if self.tenant_slug else ""
        return f"{prefix}{self.id}"

@dataclass
class ResultSet:
    """Result of executing a SQL batch."""
 
    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)
    rows_affected: int = 0
    error: Optional[str] = None
    batch_index: int = 0
 
    @property
    def ok(self) -> bool:
        return self.error is None
 
    @property
    def has_data(self) -> bool:
        return len(self.rows) > 0
 
    def to_dicts(self) -> list[dict]:
        """Convert rows to list of dicts keyed by column name."""
        return [dict(zip(self.columns, row)) for row in self.rows]
