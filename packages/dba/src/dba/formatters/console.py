"""dba.formatters.console — dependency-free table rendering for terminals."""
from __future__ import annotations

from typing import Iterable, TextIO
import sys

from dba.models import ResultSet

MAX_COL = 48


def _cell(v) -> str:
    s = "NULL" if v is None else str(v)
    s = s.replace("\n", " ")
    return s if len(s) <= MAX_COL else s[: MAX_COL - 1] + "…"


def render_console(results: Iterable[ResultSet], out: TextIO = sys.stdout, max_rows: int = 200) -> int:
    """Print every result set. Returns the number of failed batches."""
    errors = 0
    for rs in results:
        label = f"batch {rs.batch_index + 1} · result {rs.result_index + 1}"
        for m in rs.messages:
            print(f"  ℹ {m}", file=out)
        if not rs.ok:
            errors += 1
            print(f"✖ {label}: {rs.error}", file=out)
            continue
        if rs.columns:
            rows = [[_cell(v) for v in r] for r in rs.rows[:max_rows]]
            widths = [max([len(c)] + [len(r[i]) for r in rows]) for i, c in enumerate(rs.columns)]
            print(f"── {label} ({len(rs.rows)} rows)", file=out)
            print("  " + "  ".join(c.ljust(w) for c, w in zip(rs.columns, widths)), file=out)
            print("  " + "  ".join("─" * w for w in widths), file=out)
            for r in rows:
                print("  " + "  ".join(v.ljust(w) for v, w in zip(r, widths)), file=out)
            if len(rs.rows) > max_rows:
                print(f"  … {len(rs.rows) - max_rows} more rows (use --csv)", file=out)
        elif rs.rows_affected:
            print(f"── {label}: {rs.rows_affected} row(s) affected", file=out)
    return errors
