"""
dba.runner — dialect-aware SQL executor.

Batching
--------
postgres  The whole script is sent as one simple-query batch, exactly like
          `psql -f` would run it, so BEGIN … ROLLBACK/COMMIT inside the
          script controls the transaction. Optional `-- @batch` lines split
          it into independent batches. psql meta-commands (\\set, \\gexec,
          \\connect …) are rejected with a clear error: they are psql
          features, not SQL.
mssql     Split on GO lines (T-SQL convention), as before.

Every result set of every batch is collected (dryrun scripts emit several),
together with server messages (RAISE NOTICE / PRINT).

Transactions
------------
Connections are autocommit: the script owns its transaction. That is the
only way an uncommented COMMIT in fix.sql actually persists.
Rehearsal ("sandbox") is handled one level up by dba.sandbox, because a
script's own COMMIT would escape any outer transaction on Postgres.

Errors
------
On a failed batch the runner rolls back any open transaction the script
left behind, and (if an error table is configured) records the failure in
it on a fresh transaction — so the log survives the rollback.
"""

from __future__ import annotations

import os
import re
from typing import Optional, Union

from dba.models import ResultSet, Script

_GO_PATTERN = re.compile(r"^\s*GO\s*(?:\d+)?\s*(?:--.*)?$", re.IGNORECASE | re.MULTILINE)
_PG_BATCH = re.compile(r"^\s*--\s*@batch\b.*$", re.IGNORECASE | re.MULTILINE)
_PSQL_META = re.compile(r"^\s*\\[a-zA-Z!]", re.MULTILINE)
_ODBC_PREFIX = re.compile(r"^(\[[^\]]*\])+")

DEFAULT_ERROR_TABLE = "err.db_exception_tank"


def split_batches(sql: str, dialect: str = "mssql") -> list[str]:
    """Split a script into non-empty batches for the given dialect.

    The default stays 'mssql' so existing callers keep GO semantics.
    """
    pattern = _GO_PATTERN if dialect == "mssql" else _PG_BATCH
    return [b.strip() for b in pattern.split(sql) if b.strip()]


def find_psql_meta(sql: str) -> Optional[int]:
    """1-based line number of the first psql meta-command, or None."""
    m = _PSQL_META.search(sql)
    return sql.count("\n", 0, m.start()) + 1 if m else None


class Runner:
    """Execute scripts against Postgres (psycopg 3) or SQL Server (pyodbc).

        with Runner(config) as r:
            results = r.execute(script, confirm=True)

    `config` is a dba.connection.ConnectionConfig. A plain ODBC string is
    still accepted for backward compatibility (mssql).
    """

    def __init__(self, config, stop_on_error: bool = True, timeout: int = 0,
                 error_table: Optional[str] = None, label: str = "adhoc",
                 mssql_outer_rollback: bool = False):
        if isinstance(config, str):
            self.dialect, self._odbc, self.config = "mssql", config, None
        else:
            self.config, self.dialect, self._odbc = config, config.dialect, None
        self.stop_on_error = stop_on_error
        self.timeout = timeout
        self.error_table = error_table if error_table is not None else os.environ.get(
            "OB_DB_ERROR_TABLE", DEFAULT_ERROR_TABLE if self.dialect == "postgres" else "")
        self.label = label
        # mssql sandbox: hold an outer transaction and always roll it back.
        self.mssql_outer_rollback = mssql_outer_rollback
        self._conn = None
        self._notices: list[str] = []

    # ── connection ──────────────────────────────────────────────────────────
    def __enter__(self) -> "Runner":
        if self.dialect == "postgres":
            import psycopg

            kw = self.config.psycopg_kwargs()
            if self.timeout:
                kw["connect_timeout"] = self.timeout
            self._conn = psycopg.connect(autocommit=True, **kw)
            self._conn.add_notice_handler(self._on_notice)
        else:
            import pyodbc

            cs = self._odbc or self.config.odbc_connection_string()
            self._conn = pyodbc.connect(cs, autocommit=not self.mssql_outer_rollback,
                                        timeout=self.timeout or 0)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._conn:
            try:
                if self.mssql_outer_rollback:
                    self._conn.rollback()
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def _on_notice(self, diag) -> None:
        msg = getattr(diag, "message_primary", None) or str(diag)
        self._notices.append(msg)

    # ── public API ──────────────────────────────────────────────────────────
    def execute(self, script: Script, confirm: bool = False) -> list[ResultSet]:
        if script.is_destructive and not confirm:
            raise PermissionError(
                f"Script '{script.qualified_label}' is destructive. "
                f"Pass confirm=True or --yes to execute."
            )
        self.label = script.qualified_label
        return self.execute_raw(script.read())

    def execute_raw(self, sql: str) -> list[ResultSet]:
        if not self._conn:
            raise RuntimeError("Runner not connected. Use 'with Runner(...) as r:'")
        if self.dialect == "postgres":
            line = find_psql_meta(sql)
            if line:
                return [ResultSet(error=f"psql meta-command on line {line} — not SQL. "
                                        f"Remove it, or run this file with psql -f.")]

        results: list[ResultSet] = []
        for i, batch in enumerate(split_batches(sql, self.dialect)):
            batch_results = self._execute_batch(batch, batch_index=i)
            results.extend(batch_results)
            failed = [r for r in batch_results if not r.ok]
            if failed:
                self._after_error(failed[0], batch)
                if self.stop_on_error:
                    break
        return results

    # ── internals ───────────────────────────────────────────────────────────
    def _take_messages(self, cursor) -> list[str]:
        msgs = self._notices
        self._notices = []
        for m in getattr(cursor, "messages", None) or []:      # pyodbc PRINT output
            text = m[1] if isinstance(m, (tuple, list)) and len(m) > 1 else str(m)
            msgs.append(_ODBC_PREFIX.sub("", str(text)).strip())
        return msgs

    def _collect(self, cursor, batch_index: int, idx: int) -> Optional[ResultSet]:
        msgs = self._take_messages(cursor)
        if cursor.description:
            columns = [getattr(c, "name", None) or c[0] for c in cursor.description]
            rows = [list(r) for r in cursor.fetchall()]
            return ResultSet(columns=columns, rows=rows, rows_affected=len(rows),
                             batch_index=batch_index, result_index=idx, messages=msgs)
        rc = getattr(cursor, "rowcount", -1)
        if rc is not None and rc >= 0:
            return ResultSet(rows_affected=rc, batch_index=batch_index, result_index=idx, messages=msgs)
        if msgs:
            return ResultSet(batch_index=batch_index, result_index=idx, messages=msgs)
        return None

    def _execute_batch(self, sql: str, batch_index: int = 0) -> list[ResultSet]:
        cursor = self._conn.cursor()
        out: list[ResultSet] = []
        try:
            cursor.execute(sql)
            if hasattr(cursor, "results"):                    # psycopg >= 3.3
                for cur in cursor.results():
                    rs = self._collect(cur, batch_index, len(out))
                    if rs:
                        out.append(rs)
            else:                                            # psycopg < 3.3, pyodbc
                while True:
                    rs = self._collect(cursor, batch_index, len(out))
                    if rs:
                        out.append(rs)
                    if not cursor.nextset():
                        break
            if not out:
                out.append(ResultSet(batch_index=batch_index))
        except Exception as e:
            out.append(ResultSet(error=_error_text(e), batch_index=batch_index,
                                 result_index=len(out), messages=self._take_messages(cursor)))
        finally:
            try:
                cursor.close()
            except Exception:
                pass
        return out

    def _after_error(self, failed: ResultSet, batch: str) -> None:
        """Leave the session clean and record the failure (best effort)."""
        try:
            if self.dialect == "postgres":
                self._conn.execute("ROLLBACK")   # no-op warning if nothing is open
            else:
                self._conn.execute("IF @@TRANCOUNT > 0 ROLLBACK")
        except Exception:
            pass
        if not self.error_table:
            return
        try:
            if self.dialect == "postgres":
                self._conn.execute(
                    f"INSERT INTO {self.error_table} (database_name, user_name, code_author, "
                    f"sqlstate, error_message, script_label, batch_index) "
                    f"VALUES (current_database(), session_user, %s, %s, %s, %s, %s)",
                    (os.environ.get("OB_AUTHOR_NAME"), _sqlstate(failed.error), failed.error,
                     self.label, failed.batch_index),
                )
        except Exception:
            self._notices.append(f"(could not write to {self.error_table})")


def _error_text(e: Exception) -> str:
    diag = getattr(e, "diag", None)
    state = getattr(e, "sqlstate", None) or getattr(diag, "sqlstate", None)
    primary = getattr(diag, "message_primary", None) or str(e).strip()
    detail = getattr(diag, "message_detail", None)
    text = f"[{state}] {primary}" if state else primary
    return f"{text} — {detail}" if detail else text


def _sqlstate(error: Optional[str]) -> Optional[str]:
    m = re.match(r"^\[([0-9A-Z]{5})\]", error or "")
    return m.group(1) if m else None
