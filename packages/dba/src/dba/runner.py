"""
dba.runner — SQL executor with GO batch splitting.
 
The runner splits SQL scripts on GO separators (T-SQL convention),
executes each batch sequentially, and collects results. Destructive
scripts (fix.sql, rollback.sql) require explicit confirmation.
 
The GO splitter handles:
    - GO on its own line (case-insensitive)
    - GO followed by a comment (GO -- section header)
    - GO followed by a count (GO 5) — count is ignored, treated as separator
    - Leading/trailing whitespace around GO
    - Empty batches between consecutive GOs (filtered out)
    - Scripts with no GO at all (treated as a single batch)
"""
 
from __future__ import annotations
 
import re
from typing import Optional
 
from dba.models import ResultSet, Script
 
# GO separator: must be on its own line, optionally followed by
# whitespace, a count, or a comment.
_GO_PATTERN = re.compile(
    r"^\s*GO\s*(?:\d+)?\s*(?:--.*)?$",
    re.IGNORECASE | re.MULTILINE,
)
 
 
def split_batches(sql: str) -> list[str]:
    """Split a SQL script into batches on GO separators.
 
    Returns a list of non-empty batch strings. A script with no GO
    separators returns a single-element list.
    """
    batches = _GO_PATTERN.split(sql)
    return [b.strip() for b in batches if b.strip()]
 
class Runner:
    """Execute SQL batches against a pyodbc connection.
 
    Usage:
        with Runner(connection_string) as runner:
            results = runner.execute(script)
 
    The runner is a context manager that opens and closes the connection.
    Each batch is executed in its own cursor. Results are collected per-batch.
    """
 
    def __init__(self, connection_string: str, autocommit: bool = False):
        self.connection_string = connection_string
        self.autocommit = autocommit
        self._conn = None
 
    def __enter__(self) -> "Runner":
        import pyodbc
 
        self._conn = pyodbc.connect(
            self.connection_string,
            autocommit=self.autocommit,
        )
        return self
 
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._conn:
            try:
                if exc_type and not self.autocommit:
                    self._conn.rollback()
                self._conn.close()
            except Exception:
                pass
            self._conn = None
 
    def execute(self, script: Script, confirm: bool = False) -> list[ResultSet]:
        """Execute a script's SQL, returning results per batch.
 
        Args:
            script: The Script to execute.
            confirm: Must be True for destructive scripts (fix, rollback).
 
        Returns:
            List of ResultSet, one per GO-separated batch.
 
        Raises:
            PermissionError: If script is destructive and confirm is False.
            RuntimeError: If no connection is open.
        """
        if script.is_destructive and not confirm:
            raise PermissionError(
                f"Script '{script.qualified_label}' is destructive. "
                f"Pass confirm=True or --yes to execute."
            )
 
        if not self._conn:
            raise RuntimeError("Runner not connected. Use 'with Runner(...) as r:'")
 
        sql = script.read()
        batches = split_batches(sql)
        results: list[ResultSet] = []
 
        for i, batch in enumerate(batches):
            result = self._execute_batch(batch, batch_index=i)
            results.append(result)
 
        return results
 
    def execute_raw(self, sql: str) -> list[ResultSet]:
        """Execute raw SQL (no script model, no safety gate)."""
        if not self._conn:
            raise RuntimeError("Runner not connected.")
 
        batches = split_batches(sql)
        results: list[ResultSet] = []
 
        for i, batch in enumerate(batches):
            result = self._execute_batch(batch, batch_index=i)
            results.append(result)
 
        return results
 
    def _execute_batch(self, sql: str, batch_index: int = 0) -> ResultSet:
        """Execute a single batch and return a ResultSet."""
        cursor = self._conn.cursor()
        try:
            cursor.execute(sql)
 
            # Check if the batch produced a result set
            if cursor.description:
                columns = [col[0] for col in cursor.description]
                rows = [list(row) for row in cursor.fetchall()]
                return ResultSet(
                    columns=columns,
                    rows=rows,
                    rows_affected=len(rows),
                    batch_index=batch_index,
                )
            else:
                return ResultSet(
                    rows_affected=cursor.rowcount if cursor.rowcount >= 0 else 0,
                    batch_index=batch_index,
                )
        except Exception as e:
            return ResultSet(error=str(e), batch_index=batch_index)
        finally:
            cursor.close()