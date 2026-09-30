"""Section 5: positioning - price level vs how much each roaster repriced.

x = pre-shock price per 100 g (median over the main segment's pre-shock items)
y = like-for-like repricing to the end of the main index segment (%) - the
    same number as the index chart and the levers chart
Roasters without an index (Subko) get no y value. Corridor Seven's main segment ends before the shock peak (D1), so it
is plotted hollow and flagged as partial evidence.
"""
import pandas as pd

from src.analysis.data import NO_INDEX, PARTIAL, PRE


def positioning(items: pd.DataFrame, index_df: pd.DataFrame, lev: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for r, g in items.groupby("roaster"):
        idx = index_df[(index_df.roaster == r) & index_df.main_segment]
        pre_q = idx[idx.quarter.isin(PRE)].quarter if len(idx) else g[g.quarter.isin(PRE)].quarter
        level = g[g.quarter.isin(pre_q)].ppg.median()
        if r not in NO_INDEX and len(idx):
            last = idx.sort_values("quarter").iloc[-1]
            reprice, to_q, source = last["index"] - 100, last.quarter, "index main segment"
        else:
            # No index (Subko): no like-for-like measure. The levers use the
            # same index, so there is nothing else consistent to plot.
            reprice, to_q, source = None, None, "no price index"
        rows.append({"roaster": r, "tier": g.tier.iloc[0], "pre_price_100g": round(level, 1),
                     "repricing_pct": None if reprice is None else round(reprice, 1),
                     "to_quarter": to_q, "source": source, "n_items": len(g),
                     "partial": r in PARTIAL})
    return pd.DataFrame(rows)
