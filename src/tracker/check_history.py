"""Check that the historical 2023-2026Q3 analysis still reproduces exactly.

    python -m src.tracker.check_history

Re-runs src.analysis.run into a temporary folder (charts included, so they're
known to still build) and compares every table with the committed one in
outputs/tables/. Numbers must match to 1e-9 (relative), text exactly. Nothing
in outputs/ is written: the historical charts and tables are fixed, and fonts
differ between Windows and the Linux runner, so regenerated PNGs would show
up as changes every month without any real difference.

Exit code 1 (and an error line per difference) if anything changed.
"""
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from src import config
from src.analysis import data, run
from src.tracker.log import error


def same_table(a: pd.DataFrame, b: pd.DataFrame) -> str | None:
    """None if equal; otherwise a short description of the first difference."""
    if list(a.columns) != list(b.columns):
        return "columns differ"
    if len(a) != len(b):
        return f"{len(b)} rows, expected {len(a)}"
    for col in a.columns:
        x, y = a[col], b[col]
        if pd.api.types.is_numeric_dtype(x) and pd.api.types.is_numeric_dtype(y):
            if not np.allclose(x.to_numpy(float), y.to_numpy(float), rtol=1e-9, atol=1e-12, equal_nan=True):
                return f"column {col}: numbers differ"
        elif not x.fillna("").astype(str).equals(y.fillna("").astype(str)):
            return f"column {col}: values differ"
    return None


def main() -> int:
    committed = config.OUTPUTS_DIR / "tables"
    with tempfile.TemporaryDirectory(prefix="history_check_") as tmp:
        tmp = Path(tmp)
        data.TABLES, run.OUT = tmp / "tables", tmp      # redirect every write
        run.main()
        problems = []
        for new in sorted((tmp / "tables").glob("*.csv")):
            old = committed / new.name
            if not old.exists():
                problems.append(f"{new.name}: not in outputs/tables/")
                continue
            diff = same_table(pd.read_csv(old), pd.read_csv(new))
            if diff:
                problems.append(f"{new.name}: {diff}")
    for p in problems:
        error(f"historical analysis changed - {p}")
    print("historical analysis reproduces exactly" if not problems else
          f"{len(problems)} historical table(s) changed")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
