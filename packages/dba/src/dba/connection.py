"""
dba.connection — Database connection configuration.

Dialects
--------
postgres (default)  psycopg 3. Standard libpq env vars (PGHOST, PGPORT,
                    PGDATABASE, PGUSER, PGPASSWORD, PGSSLMODE) and
                    ~/.pgpass all work as usual.
mssql (legacy)      pyodbc + ODBC Driver 18. Kept so T-SQL tenants
                    (e.g. the MSI scaffolds) still run.

Resolution order (first hit wins), per field:
    OB_DB_*  env var  →  domain.json db_schema block  →  libpq PG* env var  →  default

    OB_DB_DIALECT   postgres | mssql
    OB_DB_HOST      (alias: OB_DB_SERVER)     default: localhost
    OB_DB_PORT                                default: 5432 / 1433
    OB_DB_NAME                                required
    OB_DB_USER
    OB_DB_PASSWORD  (env only — never read from domain.json)
    OB_DB_SSLMODE   postgres sslmode          default: prefer
    OB_DB_AUTH      mssql only: sql | windows | entra
    OB_DB_TRUST_CERT, OB_DB_DRIVER            mssql only

Credentials never appear in summary() output.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

DIALECTS = ("postgres", "mssql")
DEFAULT_MSSQL_DRIVER = "ODBC Driver 18 for SQL Server"
_TRUE = {"1", "true", "yes", "y", "on"}


def _env(*names: str) -> Optional[str]:
    for n in names:
        v = os.environ.get(n)
        if v not in (None, ""):
            return v
    return None


@dataclass
class ConnectionConfig:
    database: str
    dialect: str = "postgres"
    host: str = "localhost"
    port: Optional[int] = None
    user: Optional[str] = None
    password: Optional[str] = None
    sslmode: Optional[str] = None
    # mssql only
    driver: str = DEFAULT_MSSQL_DRIVER
    auth: str = "sql"
    trust_server_certificate: bool = False
    source: str = "env"

    # ── Construction ────────────────────────────────────────────────────────
    @classmethod
    def from_domain(cls, domain_path: Optional[Path]) -> "ConnectionConfig":
        block: dict = {}
        if domain_path and Path(domain_path).is_file():
            data = json.loads(Path(domain_path).read_text(encoding="utf-8"))
            block = data.get("db_schema") or {}

        dialect = (_env("OB_DB_DIALECT") or block.get("dialect") or "postgres").lower()
        if dialect not in DIALECTS:
            raise ValueError(f"Unknown dialect '{dialect}' (expected one of {', '.join(DIALECTS)})")
        pg = dialect == "postgres"

        database = _env("OB_DB_NAME") or block.get("database") or (_env("PGDATABASE") if pg else None)
        if not database:
            raise ValueError(
                "No database configured. Set OB_DB_NAME (or activate an instance with "
                "`ob-instance use <slug>`), or add db_schema.database to the tenant's domain.json."
            )
        host = (_env("OB_DB_HOST", "OB_DB_SERVER") or block.get("host") or block.get("server")
                or (_env("PGHOST") if pg else None) or "localhost")
        port_raw = _env("OB_DB_PORT") or block.get("port") or (_env("PGPORT") if pg else None)
        user = _env("OB_DB_USER") or (_env("PGUSER") if pg else None)
        password = _env("OB_DB_PASSWORD") or (_env("PGPASSWORD") if pg else None)

        auth = (_env("OB_DB_AUTH") or ("windows" if block.get("trusted_connection") else "sql")).lower()
        src = "env"
        if block:
            src = f"domain:{Path(domain_path).parent.parent.name}"
            if _env("OB_DB_NAME", "OB_DB_HOST", "OB_DB_SERVER", "OB_DB_PORT"):
                src = "env+" + src

        return cls(
            database=database,
            dialect=dialect,
            host=host,
            port=int(port_raw) if port_raw else None,
            user=user,
            password=password,
            sslmode=_env("OB_DB_SSLMODE") or block.get("sslmode") or (_env("PGSSLMODE") if pg else None),
            driver=_env("OB_DB_DRIVER") or block.get("driver") or DEFAULT_MSSQL_DRIVER,
            auth=auth,
            trust_server_certificate=(_env("OB_DB_TRUST_CERT") or "0").lower() in _TRUE,
            source=src,
        )

    @classmethod
    def from_env(cls) -> "ConnectionConfig":
        return cls.from_domain(None)

    def with_database(self, database: str) -> "ConnectionConfig":
        """Same server/credentials, different database (sandbox clones, admin db)."""
        from dataclasses import replace
        return replace(self, database=database)

    # ── Output ──────────────────────────────────────────────────────────────
    @property
    def effective_port(self) -> int:
        return self.port or (5432 if self.dialect == "postgres" else 1433)

    def psycopg_kwargs(self) -> dict:
        """Keyword args for psycopg.connect(). Password omitted when unset so
        libpq can fall back to ~/.pgpass."""
        if self.dialect != "postgres":
            raise ValueError("psycopg_kwargs() is only valid for the postgres dialect")
        kw = {"host": self.host, "port": self.effective_port, "dbname": self.database,
              "application_name": "onboarded-dba"}
        if self.user:
            kw["user"] = self.user
        if self.password:
            kw["password"] = self.password
        if self.sslmode:
            kw["sslmode"] = self.sslmode
        return kw

    def odbc_connection_string(self) -> str:
        if self.dialect != "mssql":
            raise ValueError("odbc_connection_string() is only valid for the mssql dialect")
        parts = [f"DRIVER={{{self.driver}}}", f"SERVER={self.host},{self.effective_port}",
                 f"DATABASE={self.database}"]
        if self.auth == "windows":
            parts.append("Trusted_Connection=yes")
        elif self.auth == "entra":
            parts.append("Authentication=ActiveDirectoryInteractive")
            if self.user:
                parts.append(f"UID={self.user}")
        else:
            if not self.user or self.password is None:
                raise ValueError("SQL auth needs OB_DB_USER and OB_DB_PASSWORD in the environment.")
            parts += [f"UID={self.user}", "PWD={" + self.password.replace("}", "}}") + "}"]
        parts.append("Encrypt=yes")
        if self.trust_server_certificate:
            parts.append("TrustServerCertificate=yes")
        return ";".join(parts) + ";"

    def summary(self) -> str:
        who = self.user or "(libpq default)" if self.dialect == "postgres" else (
            {"windows": "integrated", "entra": f"entra:{self.user or '?'}"}.get(self.auth, f"sql:{self.user or '?'}"))
        extra = f" sslmode={self.sslmode}" if self.sslmode else ""
        return (f"{self.dialect}://{self.host}:{self.effective_port}/{self.database} "
                f"as {who}{extra} ({self.source})")
