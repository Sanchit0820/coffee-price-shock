"""Section 1: matched-product price index per roaster.

Chained quarter to quarter over each roaster's observed quarters. A link uses
only items (product_key x pack size) present in BOTH quarters, and is the
geometric mean of their price-per-100 g ratios - so products entering or
leaving, missing pages and pack-size changes can't move it.

If the link to the previous quarter has fewer than MIN_LINK_ITEMS matched
items, the quarter links back to the most recent EARLIER quarter that does
share enough items (still like-for-like: the same products at the same pack
size, just skipping quarters where they weren't listed - e.g. Corridor
Seven's 2025 pages used other product IDs, and its 2024 products are live
again). Only if no earlier quarter qualifies does a new segment start. There
is never a unit-value bridge (decision D1). A segment with pre-shock quarters
is based on their average (= 100) and marked anchored; one without is shown
relative to its own first quarter and marked unanchored. The "main" segment
is the anchored one reaching furthest into the shock.
"""
import pandas as pd

from src.analysis.data import MIN_LINK_ITEMS, PRE, geo_mean_ratio


def _link(items_r: pd.DataFrame, qa: str, qb: str) -> tuple[int, float | None]:
    """(matched items, price relative) between two quarters."""
    m = items_r[items_r.quarter == qa].merge(items_r[items_r.quarter == qb],
                                             on=["product_key", "size_grams"], suffixes=("_a", "_b"))
    return len(m), (geo_mean_ratio(m.ppg_b.values, m.ppg_a.values) if len(m) else None)


def chain(items_r: pd.DataFrame, min_items: int = MIN_LINK_ITEMS) -> pd.DataFrame:
    """Raw chained levels for one roaster: quarter, segment, level, linked_from, link_items, link_change."""
    quarters = sorted(items_r.quarter.unique())
    rows, n_segments = [], 0
    for i, q in enumerate(quarters):
        link = None
        # Most recent earlier quarter with enough shared items (usually the previous one).
        for earlier in reversed(rows):
            n, rel = _link(items_r, earlier["quarter"], q)
            if n >= min_items:
                link = (earlier, n, rel)
                break
        if link is None:                                  # no like-for-like link: new segment
            n_segments += 1
            rows.append({"quarter": q, "segment": n_segments, "raw_level": 100.0,
                         "linked_from": None, "link_items": None, "link_change_pct": None})
        else:
            earlier, n, rel = link
            rows.append({"quarter": q, "segment": earlier["segment"],
                         "raw_level": earlier["raw_level"] * rel, "linked_from": earlier["quarter"],
                         "link_items": n, "link_change_pct": round((rel - 1) * 100, 2)})
    return pd.DataFrame(rows)


def normalise(c: pd.DataFrame) -> pd.DataFrame:
    """Base each segment: pre-shock average = 100 if it has pre quarters, else its first quarter."""
    out = []
    for seg, g in c.groupby("segment"):
        pre = g[g.quarter.isin(PRE)]
        anchored = len(pre) > 0
        base = pre.raw_level.mean() if anchored else g.raw_level.iloc[0]
        out.append(g.assign(index=g.raw_level / base * 100, anchored=anchored,
                            pre_quarters=len(pre)))
    c = pd.concat(out)
    # Main segment: anchored and reaching furthest into the shock.
    anchored = c[c.anchored]
    main = anchored.groupby("segment").quarter.max().idxmax() if len(anchored) else None
    c["main_segment"] = c.segment == main
    return c


def build(items: pd.DataFrame, roasters: list[str]) -> pd.DataFrame:
    out = []
    for r in roasters:
        g = items[items.roaster == r]
        if g.empty:
            continue
        c = normalise(chain(g))
        c.insert(0, "roaster", r)
        c.insert(1, "tier", g.tier.iloc[0])
        out.append(c)
    return pd.concat(out, ignore_index=True)


def cost_index(costs: pd.DataFrame) -> pd.DataFrame:
    """Arabica green-bean cost per 100 g roasted, pre-shock average = 100."""
    base = costs[costs.quarter.isin(PRE)].arabica_roasted_inr_100g.mean()
    return costs.assign(cost_index=costs.arabica_roasted_inr_100g / base * 100)
