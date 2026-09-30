"""One static chart per Phase 4 question (PNG in outputs/).

Colours are the dataviz skill's documented, pre-validated reference palette,
used unchanged (its validator needs Node.js, which isn't installed here):
at most the first three categorical slots, which validate for every pair, and
the blue ramp (from step 250) for ordered series. Text is always ink, never a
series colour. The CSV in outputs/tables/ is each chart's table view.
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

SURFACE, INK, INK2, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
GRID, AXIS = "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"          # categorical slots 1-3
RAMP = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab"]             # ordinal blue: lag 0..3

plt.rcParams.update({
    "font.family": ["Segoe UI", "DejaVu Sans"], "font.size": 9,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "text.color": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.titlecolor": INK,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "grid.linestyle": "-",
    "axes.spines.top": False, "axes.spines.right": False, "lines.linewidth": 2,
})


def _save(fig, path, note: str | None = None):
    if note:
        # Below the figure (y < 0): bbox_inches="tight" grows the canvas to fit it,
        # so it can never overprint the x-axis label.
        fig.text(0.01, -0.02, note, fontsize=7.5, color=INK2, ha="left", va="top", wrap=True)
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


# ---------- 1. price index ----------

def index_chart(index_df: pd.DataFrame, cost_idx: pd.DataFrame, roasters: list[str],
                quarters: list[str], partial: set, path) -> None:
    n = len(roasters)
    cols = 4
    fig, axes = plt.subplots(int(np.ceil((n + 1) / cols)), cols, figsize=(11, 5.6), sharex=True, sharey=True)
    axes = axes.ravel()
    pos = {q: i for i, q in enumerate(quarters)}
    cq = cost_idx[cost_idx.quarter.isin(quarters)]
    for ax, r in zip(axes, roasters):
        g = index_df[(index_df.roaster == r) & index_df.main_segment].sort_values("quarter")
        ax.plot([pos[q] for q in cq.quarter], cq.cost_index, color=MUTED, lw=1.6)
        ax.plot([pos[q] for q in g.quarter], g["index"], color=BLUE, marker="o", ms=4)
        ax.axhline(100, color=AXIS, lw=0.8)
        end = g.iloc[-1]
        ax.annotate(f"{end['index']:.0f}", (pos[end.quarter], end["index"]), xytext=(4, 0),
                    textcoords="offset points", fontsize=8, color=INK, va="center")
        ax.set_title(r + (" (partial)" if r in partial else ""), fontsize=9, loc="left")
    for ax in axes[n:]:
        ax.axis("off")
    legend_ax = axes[n]
    legend_ax.plot([], [], color=BLUE, marker="o", ms=4, label="retail price index\n(matched products)")
    legend_ax.plot([], [], color=MUTED, lw=1.6, label="green-coffee cost\n(arabica, Rs/100 g roasted)")
    legend_ax.legend(loc="center", frameon=False, fontsize=8.5)
    ticks = [pos[q] for q in quarters if q.endswith("Q1")]
    for ax in axes[:n]:
        ax.set_xticks(ticks, [q[:4] for q in quarters if q.endswith("Q1")])
    fig.suptitle("Most roasters held prices for a year, then raised them in sudden steps as costs doubled "
                 "(core roasters; pre-shock average = 100)", x=0.01, ha="left", fontsize=11)
    _save(fig, path, "Chained index of the same products at the same pack size. Grey Soul's chain ends in 2025Q4 "
                     "(too few products carry into the live snapshot). Table: outputs/tables/1_price_index.csv")


# ---------- 2. pass-through ----------

def pass_through_chart(pt: pd.DataFrame, headline: pd.DataFrame, partial: set, path) -> None:
    h = headline.sort_values("rupee_pass_through_pct")
    fig, ax = plt.subplots(figsize=(9, 0.45 * len(h) + 1.6))
    for y, r in enumerate(h.itertuples()):
        lags = pt[(pt.roaster == r.roaster) & (pt.quarter == r.quarter) & (pt.lag.isin(["0", "1", "2", "3"]))]
        for lag, color in zip(["0", "1", "2", "3"], RAMP):
            v = lags[lags.lag == lag].rupee_pass_through_pct
            if len(v):
                ax.scatter(v, y, s=36, color=color, zorder=3, edgecolor=SURFACE, linewidth=1.5,
                           label=f"cost lag {lag} q" if y == 0 else None)
        ax.scatter(r.rupee_pass_through_pct, y, s=90, marker="D", color=INK, zorder=4,
                   label="headline (cost averaged over lags 0-3)" if y == 0 else None)
        ax.annotate(f"{r.rupee_pass_through_pct:.0f}%", (r.rupee_pass_through_pct, y), xytext=(8, 0),
                    textcoords="offset points", va="center", fontsize=8.5)
        ax.text(1.02, y, f"{r.percent_pass_through_pct:.0f}%", transform=ax.get_yaxis_transform(),
                va="center", fontsize=8.5, color=INK2)
    ax.axvline(100, color=AXIS, lw=1)
    # Label ON the reference line, running along it.
    ax.text(100, -0.45, "every rupee of the cost rise passed on", rotation=90, fontsize=7.5,
            color=INK2, ha="right", va="bottom")
    ax.set_yticks(range(len(h)), [r + (" (partial)" if r in partial else "") + f"  ({q})"
                                  for r, q in zip(h.roaster, h.quarter)])
    ax.text(1.02, len(h) - 0.4, "% pass-\nthrough", transform=ax.get_yaxis_transform(), fontsize=7.5,
            color=INK2, va="bottom")
    ax.set_xlabel("Rupee pass-through: retail Rs increase per 100 g / green-coffee Rs increase per 100 g roasted")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower right", frameon=False, fontsize=7.5)
    fig.suptitle("Every core roaster except Grey Soul raised retail prices by more rupees than "
                 "green coffee rose", x=0.01, ha="left", fontsize=11)
    _save(fig, path, "Right column: percent pass-through (retail % / cost %). Green coffee is only part of the "
                     "retail price, so percent pass-through understates how much of the cost rise was passed on. "
                     "Roast loss 18%; see table for 15% and 20%. Table: outputs/tables/2_pass_through_headline.csv")


# ---------- 3. levers ----------

def levers_chart(lev: pd.DataFrame, path) -> None:
    d = lev.dropna(subset=["total_pct"]).copy()
    d = d.sort_values(["tier", "total_pct"], ascending=[True, True])
    parts = [("like_for_like_pct", "price rises, same products (= price index)", BLUE),
             ("pack_size_pp", "pack-size cuts (confirmed, same coffee)", ORANGE),
             ("range_mix_pp", "range & mix (remainder)", AQUA)]
    parts = [p for p in parts if d[p[0]].abs().sum() > 0]     # no legend entry for an empty lever
    fig, ax = plt.subplots(figsize=(9, 0.55 * len(d) + 1.8))
    labelled = set()
    for y, r in enumerate(d.itertuples()):
        left_pos, left_neg = 0.0, 0.0
        for col, label, color in parts:
            v = getattr(r, col) or 0.0
            if v == 0:
                continue
            start = left_pos if v >= 0 else left_neg + v
            ax.barh(y, abs(v), left=start, height=0.55, color=color, edgecolor=SURFACE, linewidth=2,
                    label=label if label not in labelled else None)
            labelled.add(label)
            if v >= 0:
                left_pos += v
            else:
                left_neg += v
        ax.scatter(r.total_pct, y, marker="|", s=300, color=INK, zorder=4,
                   label="total change in average price per 100 g" if y == 0 else None)
        # Total label sits on its marker, just above the bar.
        ax.annotate(f"total {r.total_pct:+.0f}%", (r.total_pct, y + 0.3), ha="center", va="bottom",
                    fontsize=8, color=INK)
    ax.axvline(0, color=AXIS, lw=1)
    ax.set_yticks(range(len(d)), [f"{r}  ({t}, to {e})" for r, t, e in zip(d.roaster, d.tier, d.end)])
    ax.set_ylim(-0.6, len(d) - 0.2)
    ax.set_xlabel("% change in average price per 100 g since the pre-shock average "
                  "(segments in percentage points)")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower right", frameon=False, fontsize=7.5)
    fig.suptitle("Price rises did most of the work; Grey Soul leaned on new, pricier products and "
                 "pack cuts,\nwhile Devans' cheaper additions pulled its average down",
                 x=0.01, ha="left", fontsize=11)
    _save(fig, path, "Same baseline as the price index: pre-shock average (complete-page quarters) to the end of "
                     "each roaster's index. Range & mix = total - like-for-like - pack size. Not shown: Black Baza, "
                     "Bloom (no complete pre-shock page), Subko (no price index). Table: outputs/tables/3_levers.csv")


# ---------- 4. hedonic ----------

def hedonic_chart(res: pd.DataFrame, counts: pd.DataFrame, path, sample_note: str) -> None:
    rep = counts[counts.reported][["period", "attribute", "level"]]
    d = res.merge(rep, on=["period", "attribute", "level"])
    d = d[(d.level != "unknown") & (d.attribute != "log_pack_size")]
    rows = d[["attribute", "level"]].drop_duplicates().sort_values(["attribute", "level"])
    fig, ax = plt.subplots(figsize=(8.5, 0.42 * len(rows) + 1.8))
    for y, (a, lv) in enumerate(rows.itertuples(index=False)):
        for period, color, off in (("pre", BLUE, -0.15), ("shock", ORANGE, 0.15)):
            x = d[(d.attribute == a) & (d.level == lv) & (d.period == period)]
            if len(x):
                x = x.iloc[0]
                ax.plot([x.pct_ci_low, x.pct_ci_high], [y + off] * 2, color=color, lw=2)
                ax.scatter(x.pct_effect, y + off, color=color, s=40, zorder=3, edgecolor=SURFACE,
                           linewidth=1.5, label=("before the shock (2023Q1-2024Q1)" if period == "pre"
                                                 else "during the shock (2024Q2 on)") if y == 0 else None)
    ax.axvline(0, color=AXIS, lw=1)
    ax.set_yticks(range(len(rows)), [f"{a.replace('_analysis', '')}: {lv}" for a, lv in rows.itertuples(index=False)])
    ax.invert_yaxis()
    ax.set_xlabel("% price per 100 g vs baseline (washed / arabica / single origin / medium roast), 95% CI")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower right", frameon=False, fontsize=7.5)
    fig.suptitle("Natural and experimental processes carried a premium before the shock; the estimates "
                 "shrank during it,\nbut none of the before-vs-during changes is statistically clear",
                 x=0.01, ha="left", fontsize=11)
    _save(fig, path, sample_note + " Categories with < 5 products or < 20 observations and 'unknown' "
                                   "are not shown. Table: outputs/tables/4_hedonic_coefficients.csv")


# ---------- 5. positioning ----------

def positioning_chart(pos: pd.DataFrame, cost_change_pct: float, path, cost_change_rs: float = None) -> None:
    d = pos.dropna(subset=["repricing_pct"])
    fig, ax = plt.subplots(figsize=(8, 5.2))
    if cost_change_rs:
        # The % rise that equals the green-coffee rupee rise at each starting price:
        # a cheaper coffee needs a bigger % rise to pass on the same rupees.
        xs = np.linspace(d.pre_price_100g.min() * 0.92, d.pre_price_100g.max() * 1.15, 200)
        ax.plot(xs, cost_change_rs / xs * 100, color=MUTED, lw=1.4, zorder=1)
        # Label inside the plot, near the right end of the curve (outside the axis it would be clipped).
        xl = d.pre_price_100g.max() + 0.12 * (d.pre_price_100g.max() - d.pre_price_100g.min())
        ax.annotate(f"% rise = Rs {cost_change_rs:.0f} per 100 g\n(the green-coffee rise)",
                    (xl, cost_change_rs / xl * 100), xytext=(0, 8), textcoords="offset points",
                    ha="center", va="bottom", fontsize=7.5, color=INK2)
    for tier, color in (("core", BLUE), ("secondary", ORANGE)):
        g = d[d.tier == tier]
        solid = g[~g.partial]
        ax.scatter(solid.pre_price_100g, solid.repricing_pct, s=70, color=color, edgecolor=SURFACE,
                   linewidth=2, zorder=3, label=f"{tier} roaster")
        hollow = g[g.partial]
        ax.scatter(hollow.pre_price_100g, hollow.repricing_pct, s=70, facecolor=SURFACE, edgecolor=color,
                   linewidth=2, zorder=3, label=f"{tier}, partial evidence" if len(hollow) else None)
    x_span = d.pre_price_100g.max() - d.pre_price_100g.min()
    def near(r, side: int) -> bool:
        """Another point within 20% of the x-range on this side (+1 right, -1 left), similar height."""
        dx = (d.pre_price_100g - r.pre_price_100g) * side
        return ((dx > 0) & (dx < 0.2 * x_span) & ((d.repricing_pct - r.repricing_pct).abs() < 4)).any()

    for r in d.itertuples():
        # Default right; left if a neighbour is close on the right; below if on both sides.
        if near(r, +1) and near(r, -1):
            offset, ha, va = (6, -6), "left", "top"
        elif near(r, +1):
            offset, ha, va = (-6, 4), "right", "baseline"
        else:
            offset, ha, va = (6, 4), "left", "baseline"
        ax.annotate(r.roaster + ("" if r.to_quarter == "2026Q3" else f" (to {r.to_quarter})"),
                    (r.pre_price_100g, r.repricing_pct), xytext=offset, ha=ha, va=va,
                    textcoords="offset points", fontsize=8)
    ax.set_xlabel("Pre-shock price, Rs per 100 g (median product)")
    ax.set_ylabel("Like-for-like repricing to the latest quarter (%)")
    ax.legend(loc="lower left", frameon=False, fontsize=8)
    ax.set_xlim(d.pre_price_100g.min() - 0.08 * x_span, d.pre_price_100g.max() + 0.2 * x_span)
    fig.suptitle("The cheapest roaster repriced most and the two priciest least; the middle is mixed",
                 x=0.01, ha="left", fontsize=11)
    ax.set_title(f"Green-coffee cost over the same period: +{cost_change_pct:.0f}%  (10 roasters: a pattern, "
                 f"not a tested relationship)", loc="left", fontsize=8.5, color=INK2)
    _save(fig, path, "Cheaper coffee needs a bigger % rise for the same rupee increase, because green coffee is a "
                     "larger share of its price. The grey curve is the % rise that equals the green-coffee rupee "
                     "rise; a roaster above it passed on more rupees than green coffee rose. Like-for-like = the "
                     "price index (same as charts 1 and 3). Subko: no price index. "
                     "Table: outputs/tables/5_positioning.csv")
