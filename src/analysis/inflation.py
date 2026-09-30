"""Robustness: how much of rupee pass-through is just general inflation?

Input: India CPI files in data/external/ whose names contain "CPI": either one
CSV (date column + value column, e.g. FRED INDCPIALLMINMEI) or MOSPI exports
(All India, Combined, General index). If there are two MOSPI base years
(2012 and 2024), they are spliced into one monthly series in old-base units
with a link factor from the months both cover (see splice()).

Method (per roaster, same window as the headline):
  cpi_ratio         quarterly CPI / its pre-shock average
  nominal change    base Rs/100 g x (index / 100 - 1)          (as in the headline)
  inflation part    base Rs/100 g x (cpi_ratio - 1)            what general inflation alone gives
  real change       nominal change - inflation part
  real rupee pass-through = real change / green-coffee Rs change (the actual rupee rise)
The gap between nominal and real pass-through is the part explained by
general inflation. Real pass-through near 100% = costs passed on in full plus
inflation; well above 100% = retail rose faster than both (consistent with
margin expansion relative to green coffee).
"""
import pandas as pd

from src.analysis.data import PRE
from src.quarters import quarter_of
from src.costs import EXTERNAL


_MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july",
                                        "august", "september", "october", "november", "december"], 1)}


def cpi_file():
    """All CPI files in data/external (one CSV, or MOSPI workbooks - possibly one per base year)."""
    files = sorted(set(EXTERNAL.glob("*CPI*")) | set(EXTERNAL.glob("*cpi*")))
    return files or None


def load_mospi(path) -> pd.DataFrame:
    """One MOSPI export (All India, Combined, General) -> monthly [date, cpi, base_year].

    The 2012-base and 2024-base exports use different column names for the
    same things; columns are found by name, and the General index row is the
    one whose group/division/subgroup says "General".
    """
    raw = pd.read_excel(path)
    cols = {c.lower(): c for c in raw.columns}
    base_col = next(cols[c] for c in cols if c.startswith("base"))
    d = raw[(raw[cols["state"]] == "All India") & (raw[cols["sector"]] == "Combined")].copy()
    label_cols = [cols[c] for c in ("group", "division", "subgroup") if c in cols]
    is_general = d[label_cols].astype(str).apply(lambda r: r.str.contains("General").any(), axis=1)
    d = d[is_general]
    month = d[cols["month"]].astype(str).str.lower().map(_MONTHS)
    return pd.DataFrame({"date": pd.to_datetime(dict(year=d[cols["year"]], month=month, day=1)),
                         "cpi": pd.to_numeric(d[cols["index"]], errors="coerce"),
                         "base_year": d[base_col].astype(int)}).dropna().sort_values("date")


def splice(old: pd.DataFrame, new: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Join an old-base and a new-base series into one, in old-base units.

    Old-base values are kept wherever they exist. New-base months after the old
    series ends are multiplied by a LINK FACTOR = mean(old) / mean(new) over the
    months both cover. Returns (monthly series, splice details incl. how steady
    the month-by-month ratio was across the overlap).
    """
    overlap = old.merge(new, on="date", suffixes=("_old", "_new"))
    if overlap.empty:
        raise ValueError("the two CPI series share no months: can't splice")
    factor = overlap.cpi_old.mean() / overlap.cpi_new.mean()
    ratios = overlap.cpi_old / overlap.cpi_new
    tail = new[new.date > old.date.max()].assign(cpi=lambda d: d.cpi * factor, source="new base, linked")
    out = pd.concat([old.assign(source="old base"), tail], ignore_index=True)[["date", "cpi", "source"]]
    info = {"old_base": int(old.base_year.iloc[0]), "new_base": int(new.base_year.iloc[0]),
            "overlap_months": len(overlap), "overlap_from": overlap.date.min().strftime("%Y-%m"),
            "overlap_to": overlap.date.max().strftime("%Y-%m"), "link_factor": round(factor, 4),
            "ratio_min": round(ratios.min(), 4), "ratio_max": round(ratios.max(), 4),
            "linked_months": len(tail)}
    return out, info


def monthly_cpi(paths) -> tuple[pd.DataFrame, dict]:
    """Monthly CPI from a CSV (date + value column) or MOSPI workbooks (spliced if two bases)."""
    paths = list(paths)
    if len(paths) == 1 and str(paths[0]).lower().endswith(".csv"):
        raw = pd.read_csv(paths[0])
        date_col = next(c for c in raw.columns if "date" in c.lower())
        value_col = next(c for c in raw.columns if c != date_col)
        return pd.DataFrame({"date": pd.to_datetime(raw[date_col]),
                             "cpi": pd.to_numeric(raw[value_col], errors="coerce")}).dropna(), {}
    series = sorted((load_mospi(p) for p in paths if str(p).lower().endswith(".xlsx")),
                    key=lambda s: s.base_year.iloc[0])
    if len(series) == 1:
        return series[0][["date", "cpi"]], {"base": int(series[0].base_year.iloc[0])}
    if len(series) != 2:
        raise ValueError(f"expected 1 or 2 CPI workbooks, found {len(series)}")
    return splice(*series)


def load_cpi(paths) -> pd.DataFrame:
    """Monthly CPI -> quarterly mean, rebased so the pre-shock average = 100."""
    d, _ = monthly_cpi(paths if isinstance(paths, (list, tuple)) else [paths])
    d = d.copy()
    d["quarter"] = [quarter_of(x.year, x.month) for x in d.date]
    q = d.groupby("quarter").agg(cpi=("cpi", "mean"), cpi_months=("cpi", "size")).reset_index()
    base = q[q.quarter.isin(PRE)].cpi.mean()
    return q.assign(cpi_index=q.cpi / base * 100)


def deflate(headline: pd.DataFrame, cpi: pd.DataFrame) -> pd.DataFrame:
    """Add inflation / real columns to the headline pass-through table."""
    c = cpi.set_index("quarter")
    out = headline.copy()
    out["cpi_ratio"] = [c.cpi_index.get(q, float("nan")) / 100 for q in out.quarter]
    out["cpi_months"] = [c.cpi_months.get(q, 0) for q in out.quarter]
    out["inflation_part_rs"] = out.base_price_100g * (out.cpi_ratio - 1)
    out["real_change_rs"] = out.retail_change_rs - out.inflation_part_rs
    out["real_rupee_pass_through_pct"] = out.real_change_rs / out.cost_change_rs * 100
    out["pass_through_from_inflation_pts"] = out.rupee_pass_through_pct - out.real_rupee_pass_through_pct
    return out.round(2)
