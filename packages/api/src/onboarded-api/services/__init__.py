"""
Framework-free service layer. Nothing in this package may import FastAPI or
Starlette: the admin CLI's ``--local`` backend and the service tests import it
directly, without the web stack installed.

Modules:
    domain_store   DomainStore — loads every tenant's domain.json, serves the camelCase view
    lookup         operation / glossary / status search and the ``where`` resolver
    scanner        ScanEngine, sandboxed path resolution, exit-code contract
    scan_service   ScanRequest orchestration (content and/or paths → ScanReport)
    dba_service    DbaService (tickets, scripts, gated runs) and InstanceService
"""
