"""
dba.sandbox — rehearse a script without touching the real database.

postgres  CREATE DATABASE <db>__sbx_<pid> TEMPLATE <db>, run there, DROP it.
          A full copy, so even a script that COMMITs cannot reach the real
          database. Needs CREATEDB on the login and no other open sessions
          on the source database (Postgres requires that for TEMPLATE copies).
mssql     Outer transaction that is always rolled back (SQL Server nests
          BEGIN/COMMIT under an outer transaction, so this is safe there).
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

from dba.connection import ConnectionConfig


def _ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def clone_name(database: str) -> str:
    return f"{database}__sbx_{os.getpid()}"[:63]


@contextmanager
def postgres_clone(config: ConnectionConfig) -> Iterator[ConnectionConfig]:
    import psycopg

    admin = config.with_database(os.environ.get("OB_DB_ADMIN_DB", "postgres"))
    name = clone_name(config.database)
    with psycopg.connect(autocommit=True, **admin.psycopg_kwargs()) as c:
        try:
            c.execute(f"CREATE DATABASE {_ident(name)} TEMPLATE {_ident(config.database)}")
        except Exception as e:
            if "being accessed by other users" in str(e):
                raise RuntimeError(
                    f"Sandbox needs exclusive access to '{config.database}' to copy it. "
                    f"Close other sessions (psql, IDE, app) on it and retry."
                ) from e
            raise
    try:
        yield config.with_database(name)
    finally:
        with psycopg.connect(autocommit=True, **admin.psycopg_kwargs()) as c:
            c.execute(f"DROP DATABASE IF EXISTS {_ident(name)} WITH (FORCE)")
