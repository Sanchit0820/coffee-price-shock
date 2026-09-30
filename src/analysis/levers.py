"""Section 3: how each roaster responded - price, pack size, range.

Same baseline and definition as the index (sections 1, 2 and 5):
  start = the pre-shock average, over the main index segment's pre-shock
          quarters whose listing was complete (or a single page), so archive
          gaps can't pose as dropped products
  end   = the last quarter of the main index segment (2026Q3 for most;
          Grey Soul 2025Q4)

All in percent / percentage points of the average price per 100 g:
  total_pct          % change in the average price per 100 g of ALL coffee items
                     (geometric mean), pre-shock average -> end
  like_for_like_pct  the price index change (index at end - 100): same products,
                     same pack size - identical to the positioning chart
  pack_size_pp       confirmed same-coffee size cuts (data/review/confirmed_size_cuts.csv;
                     high confidence, not crossing a product split, by the end
                     quarter): share of the end line-up's products cut x the
                     average % change in price per 100 g per cut
  range_mix_pp       total - like-for-like - pack size: products added or dropped
                     and shifts in size mix. A REMAINDER, not measured directly.
"""
import numpy as np
import pandas as pd

from src.analysis.data import CLEAN, PRE, SHOCK_START

CONFIRMED_CUTS = CLEAN.parent / "review" / "confirmed_size_cuts.csv"


def complete_pre_quarters(items_r: pd.DataFrame, coverage_r: pd.DataFrame, main_q: set) -> list[str]:
    ok = set(coverage_r[(coverage_r.source_type == "archive")
                        & coverage_r.completeness.isin(["complete", "single_page"])].quarter)
    return sorted(q for q in set(items_r.quarter) & ok & main_q if q in PRE)


def size_cuts(roaster: str, variants: pd.DataFrame, end: str | None = None) -> pd.DataFrame:
    """Confirmed same-coffee size cuts in the shock period (up to `end`), with the
    implied change in price per 100 g (uses each variant's actual prices).

    Only products listed in data/review/confirmed_size_cuts.csv count: the
    Phase 3 re-check confirmed 3 Grey Soul products as the same coffee across
    the cut. Other same-variant "cuts" (Badra 500->250 g, Biccode 250->150 g)
    are variant IDs reassigned between sizes - relabels, not cuts - and no
    automatic rule separates them reliably, so the decision is recorded by hand.
    """
    confirmed = set(pd.read_csv(CONFIRMED_CUTS, dtype=str).product_id)
    c = pd.read_csv(CLEAN / "size_changes.csv", dtype=str)
    c = c[(c.roaster == roaster) & (c.level == "variant") & (c.confidence == "high")
          & (c.crosses_product_split != "True") & (c.to_quarter >= SHOCK_START)
          & c.product_id.isin(confirmed)]
    if end:
        c = c[c.to_quarter <= end]
    c = c[c.sizes_after.astype(float) < c.sizes_before.astype(float)]
    if c.empty:
        return c.assign(ppg_change_log=[])
    v = variants[variants.roaster == roaster].set_index(["variant_id", "quarter"]).ppg
    v = v[~v.index.duplicated()]
    c = c.assign(ppg_change_log=[np.log(v.get((r.variant_id, r.to_quarter), np.nan)
                                        / v.get((r.variant_id, r.from_quarter), np.nan))
                                 for r in c.itertuples()])
    return c.dropna(subset=["ppg_change_log"])


def levers(items: pd.DataFrame, variants: pd.DataFrame, coverage: pd.DataFrame,
           index_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for r, g in items.groupby("roaster"):
        base = {"roaster": r, "tier": g.tier.iloc[0]}
        main = index_df[(index_df.roaster == r) & index_df.main_segment].sort_values("quarter")
        if main.empty:
            rows.append(base | {"note": "no price index (too few matched products)"})
            continue
        pre_q = complete_pre_quarters(g, coverage[coverage.roaster == r], set(main.quarter))
        if not pre_q:
            rows.append(base | {"note": "no complete pre-shock page in the index segment"})
            continue
        end = main.quarter.iloc[-1]
        pre_items, end_items = g[g.quarter.isin(pre_q)], g[g.quarter == end]
        # Geometric mean price per 100 g: pre-shock = average of its quarters' log means.
        pre_log = pre_items.groupby("quarter").ppg.apply(lambda s: np.log(s).mean()).mean()
        total_pct = (np.exp(np.log(end_items.ppg).mean() - pre_log) - 1) * 100
        lfl_pct = main["index"].iloc[-1] - 100
        cuts = size_cuts(r, variants, end)
        cut_products = cuts.product_id.nunique() if len(cuts) else 0
        per_cut_pct = (np.exp(cuts.groupby("product_id").ppg_change_log.mean().mean()) - 1) * 100 \
            if cut_products else 0.0
        share = cut_products / end_items.product_key.nunique()
        pack_pp = share * per_cut_pct
        keys_pre, keys_end = set(pre_items.product_key), set(end_items.product_key)
        added, dropped = keys_end - keys_pre, keys_pre - keys_end
        rows.append(base | {
            "pre_quarters": " ".join(pre_q), "end": end,
            "total_pct": round(total_pct, 1), "like_for_like_pct": round(lfl_pct, 1),
            "pack_size_pp": round(pack_pp, 1),
            "range_mix_pp": round(total_pct - lfl_pct - pack_pp, 1),
            "size_cut_products": cut_products,
            "size_cut_ppg_change_pct": round(per_cut_pct, 1) if cut_products else None,
            "products_continuing": len(keys_pre & keys_end), "products_added": len(added),
            "products_dropped": len(dropped),
            "median_ppg_added": round(end_items[end_items.product_key.isin(added)].ppg.median(), 1)
            if added else None,
            "median_ppg_dropped": round(pre_items[pre_items.product_key.isin(dropped)].ppg.median(), 1)
            if dropped else None,
            "note": "",
        })
    return pd.DataFrame(rows)
