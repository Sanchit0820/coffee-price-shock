"""Section 4: hedonic regression of log price per 100 g on product attributes.

  log(ppg) ~ process + species + origin_type_analysis + roast_level + roaster
             + log(pack size) + quarter
Fitted separately before (2023Q1-2024Q1) and during the shock (2024Q2 on).
Unit: item-quarter (product key x pack size x quarter). The same product
appears in many quarters, so standard errors are clustered by product key.

Pack size is controlled because bigger packs are cheaper per gram. "unknown"
is its own category (species is unknown for most products). A category with
fewer than MIN_PRODUCTS products or MIN_OBS observations in a period is folded
into "too_few" and not reported as a finding. Coefficients are log points:
exp(coef) - 1 = % price difference vs the baseline category.

Only products whose attributes describe the product-quarter are used
(attributes_valid), and products awaiting re-extraction are left out.
"""
import numpy as np
import pandas as pd

from src.analysis.data import CLEAN, PRE, SHOCK_START
from src.analysis.ols import dummies, ols

ATTRS = ["process", "species", "origin_type_analysis", "roast_level"]
BASELINE = {"process": "washed", "species": "arabica", "origin_type_analysis": "single_origin",
            "roast_level": "medium"}
MIN_PRODUCTS, MIN_OBS = 5, 20


def pending_reextract() -> set[tuple[str, str]]:
    """Products flagged by the process/lot rule whose attributes haven't been re-extracted yet."""
    inp = pd.read_csv(CLEAN / "product_inputs.csv", dtype=str)
    att = pd.read_csv(CLEAN / "product_attributes.csv", dtype=str).fillna("")
    sim = pd.to_numeric(inp.title_similarity, errors="coerce")
    flagged = inp[(inp.title_changed == "True") & (sim >= 0.5)]
    done = set()
    if "reextracted" in att:
        fresh = att[att.reextracted == "True"]
        done = set(zip(fresh.roaster, fresh.product_id))
    return set(zip(flagged.roaster, flagged.product_id)) - done


def sample(items: pd.DataFrame) -> pd.DataFrame:
    att = pd.read_csv(CLEAN / "product_attributes.csv", dtype=str).fillna("")
    d = items[items.attributes_valid.astype(str) == "True"].merge(
        att[["roaster", "product_id"] + ATTRS], on=["roaster", "product_id"])
    pending = pending_reextract()
    d = d[[(r, p) not in pending for r, p in zip(d.roaster, d.product_id)]]
    for a in ATTRS:
        d[a] = d[a].replace("", "unknown").str.lower()
    d["period"] = np.where(d.quarter >= SHOCK_START, "shock", "pre")
    d.loc[d.quarter.isin(PRE), "period"] = "pre"
    return d


def fold_small(d: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fold thin categories into 'too_few'; return (data, category counts)."""
    counts = []
    d = d.copy()
    for a in ATTRS:
        g = d.groupby(a).agg(n_obs=("ppg", "size"), n_products=("product_key", "nunique")).reset_index()
        small = set(g[(g.n_products < MIN_PRODUCTS) | (g.n_obs < MIN_OBS)][a]) - {BASELINE[a]}
        d[a] = d[a].where(~d[a].isin(small), "too_few")
        counts += [{"attribute": a, "level": r[a], "n_obs": r.n_obs, "n_products": r.n_products,
                    "reported": r[a] not in small} for _, r in g.iterrows()]
    return d, pd.DataFrame(counts)


def design(d: pd.DataFrame, shock_shifts: bool = False) -> pd.DataFrame:
    """Constant, attribute dummies (baseline dropped), roaster and quarter dummies,
    log pack size; optionally each attribute dummy x shock-period indicator."""
    parts = [pd.DataFrame({"const": 1.0, "log_pack_size": np.log(d.size_grams)}, index=d.index)]
    attr_cols = []
    for a in ATTRS:
        dm = dummies(d[a], a, BASELINE[a])
        attr_cols.append(dm)
        parts.append(dm)
    parts += [dummies(d.roaster, "roaster"), dummies(d.quarter, "quarter")]
    if shock_shifts:
        shock = (d.period == "shock").astype(float)
        for dm in attr_cols:
            parts.append(dm.mul(shock, axis=0).add_suffix(":shock"))
    X = pd.concat(parts, axis=1)
    return X.loc[:, X.std() > 0].assign(const=1.0)     # drop columns with no variation


def _attr_rows(fit: dict, suffix: str = "") -> list[dict]:
    rows = []
    for col in fit["params"].index:
        name = col.removesuffix(suffix) if suffix else col
        if suffix and not col.endswith(suffix):
            continue
        if not suffix and col.endswith(":shock"):
            continue
        a = next((x for x in ATTRS if name.startswith(f"{x}[")), None)
        if a is None and name != "log_pack_size":
            continue
        rows.append({"attribute": a or "log_pack_size",
                     "level": name[len(a) + 1:-1] if a else "per 1 log unit",
                     "coef": fit["params"][col], "ci_low": fit["ci_low"][col],
                     "ci_high": fit["ci_high"][col], "p_value": fit["p"][col]})
    return rows


def fit(d: pd.DataFrame) -> pd.DataFrame:
    f = ols(np.log(d.ppg), design(d), cov="cluster", groups=d.product_key)
    out = pd.DataFrame(_attr_rows(f))
    # Report effects AND their intervals as % price differences (exp(log points) - 1).
    out["pct_effect"] = (np.exp(out.coef) - 1) * 100
    out["pct_ci_low"] = (np.exp(out.ci_low) - 1) * 100
    out["pct_ci_high"] = (np.exp(out.ci_high) - 1) * 100
    out["n_obs"], out["n_products"], out["r2"] = f["n"], d.product_key.nunique(), f["r2"]
    return out


def fit_change(d: pd.DataFrame) -> pd.DataFrame:
    """Did an attribute's premium change in the shock? One pooled model where each
    attribute level also gets a shock-period shift; the shift's CI answers it."""
    f = ols(np.log(d.ppg), design(d, shock_shifts=True), cov="cluster", groups=d.product_key)
    rows = _attr_rows(f, suffix=":shock")
    return (pd.DataFrame(rows).rename(columns={"coef": "shock_shift"})
            .drop(columns=[], errors="ignore").assign(n_obs=f["n"]))


def hedonic(items: pd.DataFrame, roasters: list[str]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(coefficients per period, category counts, shock-period shifts)."""
    d = sample(items[items.roaster.isin(roasters)])
    results, counts = [], []
    for period, g in d.groupby("period"):
        g, c = fold_small(g)
        r = fit(g)
        r.insert(0, "period", period)
        results.append(r)
        counts.append(c.assign(period=period))
    # For the change test, fold with counts from BOTH periods so levels line up.
    pooled, _ = fold_small(d)
    for a in ATTRS:   # a level must exist in both periods to have a shift
        both = pooled.groupby(a).period.nunique()
        pooled[a] = pooled[a].where(pooled[a].map(both) == 2, "too_few")
    return (pd.concat(results, ignore_index=True), pd.concat(counts, ignore_index=True),
            fit_change(pooled))
