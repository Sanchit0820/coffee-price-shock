"""Guard: the shops' own text (product descriptions, listing-card text) is never
in a committed data file. It lives in git-ignored data/local/ only.

Runs locally and in the monthly GitHub Actions job (before anything is
committed), so a regenerated file that brings the text back fails here.
"""
import io

import pandas as pd
import pytest

from src import config

SHOP_TEXT = {"card_text", "description"}
DATA_FILES = sorted(p for p in config.DATA_DIR.rglob("*.csv")
                    if "local" not in p.relative_to(config.DATA_DIR).parts
                    and "raw" not in p.relative_to(config.DATA_DIR).parts
                    and "cache" not in p.relative_to(config.DATA_DIR).parts)


def header(path) -> set[str]:
    with path.open(encoding="utf-8-sig") as f:
        for line in f:
            if not line.startswith("#"):
                return set(pd.read_csv(io.StringIO(line), dtype=str).columns) if line.strip() else set()
    return set()


@pytest.mark.parametrize("path", DATA_FILES, ids=lambda p: str(p.relative_to(config.DATA_DIR)))
def test_no_shop_text_columns_in_committed_csv(path):
    assert not header(path) & SHOP_TEXT


def test_committed_label_workbook_has_no_shop_text_and_set_author():
    """Saving the workbook in Excel would stamp the Office profile name into it;
    the committed copy's author fields are set on purpose."""
    from openpyxl import load_workbook
    xlsx = config.DATA_DIR / "labels" / "hand_labels.xlsx"
    if not xlsx.exists():
        pytest.skip("no committed workbook")
    wb = load_workbook(xlsx, read_only=True)
    assert not {c.value for c in next(wb["Labels"].iter_rows(max_row=1))} & SHOP_TEXT
    assert wb.properties.creator == wb.properties.lastModifiedBy == "Sanchit Dumir"
