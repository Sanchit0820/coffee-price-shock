"""The one place the Phase 4 data rules are applied. Every section starts here.

Rules (docs/phase2.md, docs/phase3.md, decided with Sanchit):
  coffee only      LLM is_coffee == yes AND Phase 2 not non-coffee (drops drip
                   bags, concentrates, subscriptions) AND not a bundle
  excluded rows    served_outside_quarter, no pack size, inside a URL-switch window
  products         followed by product_keys_by_quarter.csv (split at page reuse)
  item             product_key x pack size x quarter; price per 100 g = median
                   across its grind/format variants (they share one price)

PERIODS were fixed from the input-cost series BEFORE looking at retail
results: green-coffee cost was flat at Rs 42-49 per 100 g roasted through
2024Q1 and rose from 2024Q2 (peak Rs 95 in 2025Q4).
"""
import numpy as np
import pandas as pd

from src import config

CLEAN = config.CLEAN_DIR
TABLES = config.OUTPUTS_DIR / "tables"
PRE = ["2023Q1", "2023Q2", "2023Q3", "2023Q4", "2024Q1"]
SHOCK_START = "2024Q2"
END = "2026Q3"            # the live products.json snapshot
MIN_LINK_ITEMS = 3        # a quarter-to-quarter link needs >= 3 matched items
NO_INDEX = {"Subko"}      # median 1 matched item per link: no usable index (D2)
PARTIAL = {"Corridor Seven": "catalogue rebuilt across the shock (2024Q3->2025Q1) with no "
                             "like-for-like link: index in separate segments (D1)"}


def is_pre(q: str) -> bool:
    return q in PRE


def load_variants() -> pd.DataFrame:
    """Variant rows with product keys and attributes attached, filters applied."""
    v = pd.read_csv(CLEAN / "variants_long.csv", dtype=str)
    keys = pd.read_csv(CLEAN / "product_keys_by_quarter.csv", dtype=str)
    attrs = pd.read_csv(CLEAN / "product_attributes.csv", dtype=str).fillna("")
    v = v.merge(keys[["roaster", "product_id", "quarter", "source_type", "product_key",
                      "attributes_valid", "title_changed"]],
                on=["roaster", "product_id", "quarter", "source_type"], how="left")
    v = v.merge(attrs[["roaster", "product_id", "is_coffee"]], on=["roaster", "product_id"], how="left")
    keep = ((v.is_coffee == "yes") & (v.is_coffee_guess != "False") & (v.is_bundle != "True")
            & (v.served_outside_quarter != "True") & v.size_grams.notna() & v.price_inr.notna()
            & (v.in_switch_window != "True"))
    v = v[keep].copy()
    v["price_inr"] = v.price_inr.astype(float)
    v["size_grams"] = v.size_grams.astype(float)
    v["ppg"] = v.price_inr / v.size_grams * 100          # rupees per 100 g
    return v


def items(v: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per product_key x pack size x quarter: median price per 100 g."""
    v = load_variants() if v is None else v
    return (v.groupby(["roaster", "tier", "quarter", "product_key", "size_grams"], as_index=False)
             .agg(ppg=("ppg", "median"), product_id=("product_id", "first"),
                  attributes_valid=("attributes_valid", "first"), n_variants=("ppg", "size")))


def cost_series(roast_loss: float) -> pd.DataFrame:
    """Quarterly green-coffee cost, rupees per 100 g roasted, at a given roast loss."""
    from src.costs import build
    return build(roast_loss)[["quarter", "months_in_quarter", "arabica_roasted_inr_100g",
                              "robusta_roasted_inr_100g"]]


def lagged_quarter(q: str, k: int) -> str:
    """The quarter k quarters before q: lagged_quarter("2025Q1", 2) == "2024Q3"."""
    year, n = int(q[:4]), int(q[-1])
    idx = year * 4 + (n - 1) - k
    return f"{idx // 4}Q{idx % 4 + 1}"


def geo_mean_ratio(new: np.ndarray, old: np.ndarray) -> float:
    """exp(mean(log(new/old))): the matched-item (Jevons) price relative."""
    return float(np.exp(np.mean(np.log(np.asarray(new) / np.asarray(old)))))
