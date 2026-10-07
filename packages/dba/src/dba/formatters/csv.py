"""dba.formatters.csv — one CSV per result set: <prefix>_b<batch>_r<result>.csv"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from dba.models import ResultSet


def write_csv(results: Iterable[ResultSet], out_dir: Path, prefix: str = "result") -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for rs in results:
        if not rs.ok or not rs.columns:
            continue
        path = out_dir / f"{prefix}_b{rs.batch_index + 1}_r{rs.result_index + 1}.csv"
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(rs.columns)
            w.writerows(["" if v is None else v for v in row] for row in rs.rows)
        written.append(path)
    return written
