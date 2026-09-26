"""Quarterly input costs: global green-coffee prices converted to rupees per 100 g roasted.

    python -m src.costs [--roast-loss 0.18]  ->  data/clean/input_costs_quarterly.csv

Sources (data/external/, filename carries the download date):
  World Bank Pink Sheet  "Coffee, Arabica" and "Coffee, Robusta", US$/kg,
                         monthly (ICO indicator prices, ex-dock)
  FRED DEXINUS           Indian rupees per US dollar, daily (noon buying rates, New York)

This is the GREEN-BEAN cost of a bag only: no roasting, packaging, labour or
margin. And ICO prices are global benchmarks, which Indian estate coffee only
partly follows.
"""
import argparse

import pandas as pd

from src import config
from src.quarters import quarter_of

EXTERNAL = config.DATA_DIR / "external"
OUT = config.CLEAN_DIR / "input_costs_quarterly.csv"
DEFAULT_ROAST_LOSS = 0.18   # ASSUMPTION: roasting typically loses 15-20% of green weight
START_QUARTER = "2022Q1"    # first full quarter of the FX series (starts 2021-09-20)
LAGS = (1, 2, 3)
SERIES = {"arabica": "Coffee, Arabica", "robusta": "Coffee, Robusta"}


# ---------- loading ----------

def latest(pattern: str):
    """Newest matching file in data/external (dates in names sort correctly)."""
    files = sorted(EXTERNAL.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No {pattern} in {EXTERNAL}")
    return files[-1]


def load_pink_sheet(path) -> pd.DataFrame:
    """Monthly arabica/robusta in US$/kg: columns month (Timestamp), arabica_usd_kg, robusta_usd_kg.

    Columns are found by their header text, not position, so a new edition
    with extra commodities still loads. Month labels look like "2026M08".
    """
    raw = pd.read_excel(path, sheet_name="Monthly Prices", header=None)
    header_row = raw.index[raw.apply(lambda r: SERIES["arabica"] in r.values, axis=1)][0]
    cols = {}
    for key, title in SERIES.items():
        col = raw.columns[raw.loc[header_row] == title][0]
        unit = str(raw.loc[header_row + 1, col])
        if unit != "($/kg)":   # guard: fail loudly if the Bank changes units
            raise ValueError(f"{title}: expected ($/kg), found {unit}")
        cols[col] = f"{key}_usd_kg"
    labels = raw[0].astype(str)
    rows = raw[labels.str.fullmatch(r"\d{4}M\d{2}")]
    out = rows[list(cols)].rename(columns=cols).apply(pd.to_numeric, errors="coerce")
    out.insert(0, "month", pd.to_datetime(rows[0].str.replace("M", "-") + "-01"))
    return out.reset_index(drop=True)


def monthly_fx(daily: pd.DataFrame) -> pd.DataFrame:
    """Daily INR/USD -> monthly mean. Blank days (holidays) are ignored, not zeros.

    Input columns: observation_date, DEXINUS. Output: month, inr_per_usd, fx_days.
    """
    d = daily.assign(date=pd.to_datetime(daily["observation_date"]),
                     rate=pd.to_numeric(daily["DEXINUS"], errors="coerce")).dropna(subset=["rate"])
    g = d.groupby(d.date.dt.to_period("M")).rate
    out = pd.DataFrame({"inr_per_usd": g.mean(), "fx_days": g.size()}).reset_index()
    out["month"] = out.pop("date").dt.to_timestamp()
    return out[["month", "inr_per_usd", "fx_days"]]


# ---------- conversions ----------

def green_inr_per_kg(usd_per_kg, inr_per_usd):
    return usd_per_kg * inr_per_usd


def roasted_inr_per_100g(green_inr_kg, roast_loss: float = DEFAULT_ROAST_LOSS):
    """Green-bean cost of 100 g of ROASTED coffee.

    Roasting loses `roast_loss` of the weight, so 1 kg roasted needs
    1 / (1 - roast_loss) kg green (1.22 kg at 18%). Then /10 for 100 g.
    """
    if not 0 <= roast_loss < 1:
        raise ValueError(f"roast_loss must be in [0, 1), got {roast_loss}")
    return green_inr_kg / (1 - roast_loss) / 10


def monthly_costs(prices: pd.DataFrame, fx: pd.DataFrame, roast_loss: float) -> pd.DataFrame:
    """Join prices and FX by month (only months with both) and convert."""
    m = prices.merge(fx, on="month", how="inner")
    for key in SERIES:
        m[f"{key}_green_inr_kg"] = green_inr_per_kg(m[f"{key}_usd_kg"], m.inr_per_usd)
        m[f"{key}_roasted_inr_100g"] = roasted_inr_per_100g(m[f"{key}_green_inr_kg"], roast_loss)
    return m


# ---------- quarters and lags ----------

def to_quarters(monthly: pd.DataFrame) -> pd.DataFrame:
    """Mean of each quarter's months, labelled like variants_long.csv ("2024Q3").

    The rupee series are averaged month by month (each month's price at that
    month's rate), not as average-price x average-rate. months_in_quarter < 3
    marks a partial quarter (e.g. the latest, before the Bank publishes it all).
    """
    m = monthly.assign(quarter=[quarter_of(d.year, d.month) for d in monthly.month])
    value_cols = [c for c in m.columns if c not in ("month", "quarter", "fx_days")]
    q = m.groupby("quarter")[value_cols].mean()
    q.insert(0, "months_in_quarter", m.groupby("quarter").size())
    return q.reset_index()


def add_lags(q: pd.DataFrame, cols: list[str], lags=LAGS) -> pd.DataFrame:
    """col_lagN = the value N quarters earlier (rows must be consecutive quarters)."""
    q = q.sort_values("quarter").reset_index(drop=True)
    for col in cols:
        for n in lags:
            q[f"{col}_lag{n}"] = q[col].shift(n)
    return q


def build(roast_loss: float = DEFAULT_ROAST_LOSS) -> pd.DataFrame:
    prices = load_pink_sheet(latest("CMO-Historical-Data-Monthly_*.xlsx"))
    fx = monthly_fx(pd.read_csv(latest("DEXINUS_*.csv")))
    q = to_quarters(monthly_costs(prices, fx, roast_loss))
    # Lags are computed on the full history first, so 2022Q1 onward has real lags.
    q = add_lags(q, [f"{k}_roasted_inr_100g" for k in SERIES])
    q = q[q.quarter >= START_QUARTER].reset_index(drop=True)
    q["roast_loss"] = roast_loss   # the assumption travels with the numbers
    return q.round(4)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--roast-loss", type=float, default=DEFAULT_ROAST_LOSS,
                        help="share of green weight lost in roasting (default 0.18)")
    args = parser.parse_args()
    q = build(args.roast_loss)
    q.to_csv(OUT, index=False)
    print(f"Wrote {len(q)} quarters ({q.quarter.iloc[0]}..{q.quarter.iloc[-1]}) to {OUT}")


if __name__ == "__main__":
    main()
