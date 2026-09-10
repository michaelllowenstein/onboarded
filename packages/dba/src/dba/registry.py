"""
dba.registry — Ticket and tenant discovery from the filesystem.
 
TicketRegistry scans a single tenant's scripts/ directory for ticket
subdirectories. TenantRegistry wraps multiple TicketRegistries for
cross-tenant discovery.
 
Directory convention:
    tenants/<slug>/scripts/<ticket_id>/
        diagnostic.sql
        dryrun.sql
        fix.sql
        rollback.sql
        runbook.md
"""
 
from __future__ import annotations
 
from pathlib import Path
from typing import Optional
 
from dba.models import Ticket

class TicketRegistry:
    """Registry of tickets for a single tenant."""
 
    def __init__(self, scripts_root: Path, tenant_slug: str = ""):
        self.scripts_root = scripts_root
        self.tenant_slug = tenant_slug
        self._tickets: dict[str, Ticket] = {}
 
    def scan(self) -> list[Ticket]:
        """Discover ticket directories under scripts_root.
 
        A valid ticket directory is any subdirectory that contains at
        least one .sql file. The directory name is the ticket ID.
        """
        self._tickets.clear()
 
        if not self.scripts_root.is_dir():
            return []
 
        for entry in sorted(self.scripts_root.iterdir()):
            if not entry.is_dir():
                continue
 
            # A ticket directory must contain at least one .sql file
            sql_files = list(entry.glob("*.sql"))
            if not sql_files:
                continue
 
            ticket = Ticket(
                id=entry.name,
                path=entry,
                tenant_slug=self.tenant_slug,
            )
            self._tickets[ticket.id] = ticket
 
        return list(self._tickets.values())
 
    def get(self, ticket_id: str) -> Optional[Ticket]:
        """Get a ticket by ID. Scans if not yet populated."""
        if not self._tickets:
            self.scan()
        return self._tickets.get(ticket_id)
 
    def all_tickets(self) -> list[Ticket]:
        """Return all discovered tickets."""
        if not self._tickets:
            self.scan()
        return list(self._tickets.values())
 
    @property
    def count(self) -> int:
        if not self._tickets:
            self.scan()
        return len(self._tickets)

class TenantRegistry:
    """
    Multi-tenant registry that wraps per-tenant TicketRegistries.
    Auto-discovers tenants by scanning tenants_root for directories
    that contain a scripts/ subdirectory.
    """
 
    def __init__(self, tenants_root: Path):
        self.tenants_root = tenants_root
        self._registries: dict[str, TicketRegistry] = {}
 
    def auto_discover(self) -> list[str]:
        """Scan tenants_root for tenant directories with scripts/ subdirs.
 
        Returns list of discovered tenant slugs.
        """
        self._registries.clear()
 
        if not self.tenants_root.is_dir():
            return []
 
        for entry in sorted(self.tenants_root.iterdir()):
            if not entry.is_dir():
                continue
 
            scripts_dir = entry / "scripts"
            if scripts_dir.is_dir():
                slug = entry.name
                self._registries[slug] = TicketRegistry(
                    scripts_root=scripts_dir,
                    tenant_slug=slug,
                )
 
        return self.all_tenants()
 
    def get_registry(self, tenant_slug: str) -> Optional[TicketRegistry]:
        """Get the TicketRegistry for a specific tenant."""
        if not self._registries:
            self.auto_discover()
        return self._registries.get(tenant_slug)
 
    def all_tenants(self) -> list[str]:
        """Return all discovered tenant slugs."""
        return sorted(self._registries.keys())
 
    def scan_all(self) -> dict[str, list[Ticket]]:
        """Scan all tenants and return a dict of slug → ticket list."""
        if not self._registries:
            self.auto_discover()
 
        result: dict[str, list[Ticket]] = {}
        for slug, registry in sorted(self._registries.items()):
            tickets = registry.scan()
            if tickets:
                result[slug] = tickets
 
        return result
