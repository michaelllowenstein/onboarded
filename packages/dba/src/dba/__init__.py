Y
"""
packages/dba — Onboarded DBA Engine
====================================
 
Tenant-aware SQL script runner for operational ticket workflows.
 
Modules:
    models      - Ticket, Script, ResultSet dataclasses
    runner      - SQL executor with GO batch splitting and safety gates
    registry    - TicketRegistry (single tenant) + TenantRegistry (multi-tenant)
    connection  - domain.json-aware database connection config
    scaffold    - Ticket directory templating (5-file standard layout)
    formatters  - Rich console + CSV output formatters
 
Conventions:
    - Ticket scripts live at tenants/<slug>/scripts/<ticket_id>/
    - Each ticket directory contains: diagnostic.sql, dryrun.sql, fix.sql,
      rollback.sql, runbook.md
    - fix.sql and rollback.sql are DESTRUCTIVE — require --yes or
      X-Onboarded-Confirm header
    - Connection config reads from domain.json db_schema block, falls back
      to environment variables
    - pyodbc is a runtime-only dependency; all tests run without it via
      sys.modules stub
"""

__version__ = "1.0.0"

from dba.models import Ticket, Script, ResultSet
