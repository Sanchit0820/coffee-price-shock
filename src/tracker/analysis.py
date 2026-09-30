"""Monthly tracker tables and chart (outputs/tracker/).

    tracker_index.csv    matched-product price index per roaster and month
                         (first tracker month = 100); same chained method as the
                         historical index (src/analysis/index.chain)
    tracker_changes.csv  latest month vs the roaster's previous month, one row per
                         change: price_up / price_down (same product, same pack
                         size), pack_size_change (same variant, new size), added,
                         dropped
    tracker_summary.csv  one row per roaster: counts of the above + index
    tracker_index.png    the index, one panel per roaster

Coffee = the LLM says is_coffee "yes"; for a product whose attributes are still
pending, Phase 2's rule-based guess stands in (and is counted in the summary).
Bundles and rows with no pack size or price are left out, as in Phase 4.
A product ID whose title changes to a different coffee (the Phase 3 rule)
starts a new product key, so a reused page never counts as a price change.
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from src import config  # noqa: E402
from src.analysis import charts  # noqa: E402  (palette and style)
from src.analysis.index import chain  # noqa: E402
from src.product_inputs import is_different_coffee  # noqa: E402

OUT = config.OUTPUTS_DIR / "tracker"
PRICE_MOVE = 0.005   # a same-product change under 0.5% is rounding, not a price change


def coffee_lookup(phase3: pd.DataFrame, tracker: pd.DataFrame) -> dict:
    """(roaster, product_id) -> is_coffee from the LLM; "" while pending."""
    out = dict(zip(zip(phase3.roaster, phase3.product_id), phase3.is_coffee)) if len(phase3) else {}
    if len(tracker):
        vals = np.where(tracker.status == "pending", "", tracker.is_coffee)
        out |= dict(zip(zip(tracker.roaster, tracker.product_id), vals))
    return out


def coffee_rows(monthly: pd.DataFrame, lookup: dict) -> pd.DataFrame:
    m = monthly.copy()
    llm = [lookup.get(k, "") for k in zip(m.roaster, m.product_id)]
    m["attributes_pending"] = [v == "" for v in llm]
    is_coffee = [(v == "yes") if v else (g == "True") for v, g in zip(llm, m.is_coffee_guess)]
    keep = (np.array(is_coffee) & (m.is_coffee_guess != "False") & (m.is_bundle != "True")
            & (m.size_grams != "") & m.size_grams.notna() & (m.price_inr != "") & m.price_inr.notna())
    m = m[keep].copy()
    m["price_inr"] = m.price_inr.astype(float)
    m["size_grams"] = m.size_grams.astype(float)
    m["ppg"] = m.price_inr / m.size_grams * 100
    return m


def add_product_keys(rows: pd.DataFrame) -> pd.DataFrame:
    """product_key = product_id, plus "#2", "#3"... after each change to a different coffee."""
    keys = {}
    for (roaster, pid), g in rows.groupby(["roaster", "product_id"]):
        titles = g.drop_duplicates("month").sort_values("month")[["month", "product_title"]]
        n, prev = 1, None
        for month, title in zip(titles.month, titles.product_title):
            if prev is not None and is_different_coffee(prev, title):
                n += 1
            keys[(roaster, pid, month)] = pid if n == 1 else f"{pid}#{n}"
            prev = title
    return rows.assign(product_key=[keys[k] for k in zip(rows.roaster, rows.product_id, rows.month)])


def items(rows: pd.DataFrame) -> pd.DataFrame:
    return (rows.groupby(["roaster", "tier", "month", "product_key", "size_grams"], as_index=False)
            .agg(ppg=("ppg", "median"), product_title=("product_title", "last")))


def monthly_index(it: pd.DataFrame) -> pd.DataFrame:
    """chain() works on any sortable period label; months are passed as its "quarter"."""
    out = []
    for r, g in it.groupby("roaster"):
        c = chain(g.rename(columns={"month": "quarter"})).rename(columns={"quarter": "month"})
        # Base each segment on its own first month; the "main" one is the latest.
        c["index"] = c.raw_level / c.groupby("segment").raw_level.transform("first") * 100
        c["main_segment"] = c.segment == c.segment.iloc[-1]
        c.insert(0, "roaster", r)
        c.insert(1, "tier", g.tier.iloc[0])
        out.append(c)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def changes(rows: pd.DataFrame, it: pd.DataFrame, month: str) -> pd.DataFrame:
    """Each roaster's changes from its previous month to `month`."""
    out = []
    for r, g in it.groupby("roaster"):
        months = sorted(g.month.unique())
        if month not in months or months.index(month) == 0:
            continue
        prev = months[months.index(month) - 1]
        a, b = g[g.month == prev], g[g.month == month]
        m = a.merge(b, on=["product_key", "size_grams"], suffixes=("_before", "_after"))
        for x in m.itertuples():
            ratio = x.ppg_after / x.ppg_before - 1
            if abs(ratio) >= PRICE_MOVE:
                out.append({"roaster": r, "from_month": prev, "to_month": month,
                            "change": "price_up" if ratio > 0 else "price_down",
                            "product_key": x.product_key, "product_title": x.product_title_after,
                            "grams_before": x.size_grams, "grams_after": x.size_grams,
                            "ppg_before": round(x.ppg_before, 1), "ppg_after": round(x.ppg_after, 1),
                            "ppg_change_pct": round(ratio * 100, 1)})
        for kind, keys, src in (("added", set(b.product_key) - set(a.product_key), b),
                                ("dropped", set(a.product_key) - set(b.product_key), a)):
            for k in sorted(keys):
                s = src[src.product_key == k]
                out.append({"roaster": r, "from_month": prev, "to_month": month, "change": kind,
                            "product_key": k, "product_title": s.product_title.iloc[0],
                            "ppg_before" if kind == "dropped" else "ppg_after": round(s.ppg.median(), 1)})
        out += pack_size_changes(rows[rows.roaster == r], prev, month)
    return pd.DataFrame(out)


def pack_size_changes(rows_r: pd.DataFrame, prev: str, month: str) -> list[dict]:
    """Same variant ID, same coffee (product key), different pack size."""
    a = rows_r[rows_r.month == prev].drop_duplicates("variant_id")
    b = rows_r[rows_r.month == month].drop_duplicates("variant_id")
    m = a.merge(b, on=["variant_id", "product_key"], suffixes=("_before", "_after"))
    m = m[m.size_grams_before != m.size_grams_after]
    return [{"roaster": x.roaster_before, "from_month": prev, "to_month": month,
             "change": "pack_size_change", "product_key": x.product_key,
             "product_title": x.product_title_after,
             "grams_before": x.size_grams_before, "grams_after": x.size_grams_after,
             "price_before": x.price_inr_before, "price_after": x.price_inr_after,
             "ppg_before": round(x.ppg_before, 1), "ppg_after": round(x.ppg_after, 1),
             "ppg_change_pct": round((x.ppg_after / x.ppg_before - 1) * 100, 1)}
            for x in m.itertuples()]


def summary(status: pd.DataFrame, idx: pd.DataFrame, ch: pd.DataFrame,
            rows: pd.DataFrame, month: str) -> pd.DataFrame:
    out = []
    for s in status.itertuples():
        c = ch[ch.roaster == s.roaster] if len(ch) else ch
        i = idx[(idx.roaster == s.roaster) & (idx.month == month)] if len(idx) else idx
        now = rows[(rows.roaster == s.roaster) & (rows.month == month)]
        count = (lambda kind: int((c.change == kind).sum()) if len(c) else 0)  # noqa: E731
        out.append({"month": month, "roaster": s.roaster, "tier": s.tier, "status": s.status,
                    "coffee_products": now.product_key.nunique(),
                    "attributes_pending": now[now.attributes_pending].product_id.nunique(),
                    "price_up": count("price_up"), "price_down": count("price_down"),
                    "pack_size_change": count("pack_size_change"),
                    "added": count("added"), "dropped": count("dropped"),
                    "same_product_change_pct": i.link_change_pct.iloc[0] if len(i) else None,
                    "index": round(i["index"].iloc[0], 1) if len(i) else None,
                    "big_drop": s.big_drop})
    return pd.DataFrame(out)


def chart(idx: pd.DataFrame, path) -> None:
    roasters = sorted(idx.roaster.unique())
    months = sorted(idx.month.unique())
    pos = {m: i for i, m in enumerate(months)}
    cols = 4
    fig, axes = plt.subplots(int(np.ceil(len(roasters) / cols)), cols, figsize=(11, 5.6),
                             sharex=True, sharey=True, squeeze=False)
    axes = axes.ravel()
    for ax, r in zip(axes, roasters):
        g = idx[(idx.roaster == r) & idx.main_segment].sort_values("month")
        ax.plot([pos[m] for m in g.month], g["index"], color=charts.BLUE, marker="o", ms=4)
        ax.axhline(100, color=charts.AXIS, lw=0.8)
        ax.set_title(r, fontsize=9, loc="left")
    for ax in axes[len(roasters):]:
        ax.axis("off")
    step = max(1, len(months) // 6)
    for ax in axes[:len(roasters)]:
        ax.set_xticks(range(0, len(months), step), months[::step], rotation=45)
        ax.tick_params(labelbottom=True)   # also under panels with an empty slot below
    fig.suptitle(f"Live tracker: same-product price index by month, to {months[-1]} "
                 f"(first tracker month = 100)", x=0.01, ha="left", fontsize=11)
    note = ("Chained index of the same coffees at the same pack size, from each roaster's live "
            "products.json. Table: outputs/tracker/tracker_index.csv")
    if len(months) == 1:
        note = "First tracker month: changes appear from the second monthly run. " + note
    charts._save(fig, path, note)


def build(monthly: pd.DataFrame, lookup: dict, status: pd.DataFrame, month: str) -> dict:
    rows = add_product_keys(coffee_rows(monthly, lookup))
    it = items(rows)
    idx = monthly_index(it)
    ch = changes(rows, it, month)
    return {"index": idx, "changes": ch, "summary": summary(status, idx, ch, rows, month)}
