"""Section 2: cost pass-through, in rupees (headline) and percent (secondary).

For a roaster at shock quarter t (main index segment only) and lag k:
  retail change   Rs = base price per 100 g x (index_t / 100 - 1)
  cost change     Rs = green cost per 100 g roasted at quarter t-k minus its
                  pre-shock average
  RUPEE pass-through   = retail Rs change / cost Rs change      (HEADLINE)
  percent pass-through = retail % change / cost % change        (secondary)
The pre-specified headline lag ("avg0-3") uses the mean cost of lags 0-3, i.e.
the cost over the preceding year, rather than picking the best-fitting lag.

Why rupees lead: green coffee is only part of the retail price, so a roaster
that passes on every rupee of the cost rise still shows a percent
pass-through well below 100%.

Roast loss scales every cost rupee by the same factor, so it changes rupee
pass-through but cancels out of percent pass-through (tested).
"""
import numpy as np
import pandas as pd

from src.analysis.data import PRE, SHOCK_START, lagged_quarter
from src.analysis.ols import Z95, dummies, ols

LAGS = [0, 1, 2, 3]
HEADLINE_LAG = "avg0-3"
# Below this cost rise (Rs per 100 g roasted) a ratio is too unstable to report:
# dividing by a tiny change turns noise into a large "pass-through".
MIN_COST_CHANGE_RS = 10.0


def base_price(items: pd.DataFrame, index_rows: pd.DataFrame) -> float:
    """Typical pre-shock price per 100 g: median over items in the main segment's pre quarters."""
    pre_q = index_rows[index_rows.main_segment & index_rows.quarter.isin(PRE)].quarter
    return float(items[items.quarter.isin(pre_q)].ppg.median())


def cost_at(costs: pd.Series, q: str, lag) -> float | None:
    """Cost for quarter q at a lag (int), or the mean of lags 0-3 ("avg0-3")."""
    if lag == HEADLINE_LAG:
        vals = [costs.get(lagged_quarter(q, k)) for k in LAGS]
        return None if any(v is None or np.isnan(v) for v in vals) else float(np.mean(vals))
    v = costs.get(lagged_quarter(q, lag))
    return None if v is None or np.isnan(v) else float(v)


def pass_through(index_df: pd.DataFrame, items: pd.DataFrame, costs: pd.DataFrame,
                 roast_loss: float) -> pd.DataFrame:
    """One row per roaster x shock quarter x lag."""
    c = costs.set_index("quarter").arabica_roasted_inr_100g
    pre_cost = float(c[c.index.isin(PRE)].mean())
    rows = []
    for r, g in index_df.groupby("roaster"):
        main = g[g.main_segment]
        base = base_price(items[items.roaster == r], g)
        for t in main[main.quarter >= SHOCK_START].itertuples():
            retail_pct = t.index / 100 - 1
            for lag in LAGS + [HEADLINE_LAG]:
                cost = cost_at(c, t.quarter, lag)
                if cost is None:
                    continue
                cost_rs, cost_pct = cost - pre_cost, cost / pre_cost - 1
                rows.append({
                    "roaster": r, "tier": t.tier, "quarter": t.quarter, "lag": str(lag),
                    "roast_loss": roast_loss, "base_price_100g": round(base, 1),
                    "retail_change_pct": round(retail_pct * 100, 1),
                    "retail_change_rs": round(base * retail_pct, 2),
                    "cost_change_rs": round(cost_rs, 2), "cost_change_pct": round(cost_pct * 100, 1),
                    "rupee_pass_through_pct": round(base * retail_pct / cost_rs * 100, 1),
                    "percent_pass_through_pct": round(retail_pct / cost_pct * 100, 1),
                    "reliable": cost_rs >= MIN_COST_CHANGE_RS,
                })
    return pd.DataFrame(rows)


def headline(pt: pd.DataFrame) -> pd.DataFrame:
    """Per roaster: the latest shock quarter of its main segment, headline lag."""
    h = pt[pt.lag == HEADLINE_LAG]
    return h.loc[h.groupby("roaster").quarter.idxmax()].reset_index(drop=True)


def distributed_lag(index_df: pd.DataFrame, costs: pd.DataFrame, roasters: list[str]) -> dict:
    """Pooled regression: log retail change over each index link on log cost
    change over the SAME span at lags 0-3, with roaster dummies; HC1 robust SEs.
    The sum of the lag coefficients is the long-run PERCENT pass-through.
    Small sample: supporting evidence only."""
    c = costs.set_index("quarter").arabica_roasted_inr_100g
    obs = []
    for r in roasters:
        g = index_df[index_df.roaster == r].sort_values("quarter")
        for seg, s in g.groupby("segment"):
            s = s.reset_index(drop=True)
            for a, b in zip(s.itertuples(), s.iloc[1:].itertuples()):
                row = {"roaster": r, "dy": np.log(b.raw_level / a.raw_level)}
                ok = True
                for k in LAGS:
                    ca, cb = c.get(lagged_quarter(a.quarter, k)), c.get(lagged_quarter(b.quarter, k))
                    if ca is None or cb is None:
                        ok = False
                        break
                    row[f"dcost_lag{k}"] = np.log(cb / ca)
                if ok:
                    obs.append(row)
    d = pd.DataFrame(obs)
    names = [f"dcost_lag{k}" for k in LAGS]
    X = pd.concat([pd.DataFrame({"const": 1.0}, index=d.index), d[names],
                   dummies(d.roaster, "roaster")], axis=1)
    fit = ols(d.dy, X, cov="HC1")
    w = np.ones(len(names))
    total = float(fit["params"][names] @ w)
    se = float(np.sqrt(w @ fit["cov"].loc[names, names].values @ w))
    rows = [{"term": n, "coef": fit["params"][n], "ci_low": fit["ci_low"][n],
             "ci_high": fit["ci_high"][n]} for n in names]
    rows.append({"term": "sum_lags_0_3 (long-run % pass-through)", "coef": total,
                 "ci_low": total - Z95 * se, "ci_high": total + Z95 * se})
    out = pd.DataFrame(rows)
    out["n_obs"], out["n_roasters"] = len(d), d.roaster.nunique()
    return {"table": out.round(3), "n": len(d)}
