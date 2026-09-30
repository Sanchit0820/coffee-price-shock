"""Monthly snapshot of every roaster's live products.json.

    data/clean/live_monthly.csv         one row per variant per month (append-only)
    data/clean/live_monthly_status.csv  one row per roaster per month: what happened

Rules
- robots.txt is re-read on every run (http_client keeps it in memory only). A
  roaster whose products.json it disallows, or whose robots.txt can't be read
  (which, by our rules, means "treat as off-limits"), is skipped and logged.
- A roaster already fetched this month is not fetched again (never re-fetch).
- A roaster that fails keeps the rows it already has: nothing is overwritten.
- The first month (2026-09) is seeded from Phase 2's live snapshot (fetched
  2026-09-26), so the tracker starts where the historical analysis ends.
"""
import json
from datetime import date

import pandas as pd

from src import collect, config, http_client
from src.product_inputs import clean_text

MONTHLY = config.CLEAN_DIR / "live_monthly.csv"
STATUS = config.CLEAN_DIR / "live_monthly_status.csv"
SETTINGS = config.DATA_DIR / "tracker_settings.csv"
COLUMNS = ["month", "fetched_at", "roaster", "tier", "product_id", "product_title", "product_type",
           "variant_id", "variant_title", "sku", "price_inr", "compare_at_price_inr", "size_grams",
           "multipack", "size_source", "is_coffee_guess", "is_bundle", "sale_suspected", "source_url"]
BIG_DROP = 0.5   # flag a roaster whose product count falls below half of last month's


def month_label(d: date | None = None) -> str:
    return (d or date.today()).strftime("%Y-%m")


def tracker_roasters() -> list[dict]:
    """roasters_final.csv rows with their live URL and the tracker_enabled switch
    (data/tracker_settings.csv: set a roaster to False by hand, e.g. if its
    terms change; robots.txt is checked automatically, terms can't be)."""
    final = pd.read_csv(collect.FINAL, dtype=str).fillna("")
    enabled = pd.read_csv(SETTINGS, dtype=str).fillna("").set_index("roaster").tracker_enabled
    out = []
    for r in final.to_dict("records"):
        # Same rule as collect.load_roasters: the last listing URL is the current one.
        r["live_url"] = [u.strip() for u in r["archive_listing_urls"].split("|")][-1]
        r["enabled"] = enabled.get(r["roaster"], "True") == "True"
        out.append(r)
    return out


# ---------- stored data ----------

def seed_from_phase2() -> pd.DataFrame:
    """The Phase 2 live snapshot as the tracker's first month."""
    v = pd.read_csv(collect.VARIANTS_OUT, dtype=str)
    live = v[v.source_type == "live"].copy()
    live["month"] = live.served_ts.str[:7]
    live["fetched_at"] = live.served_ts
    return live[COLUMNS].reset_index(drop=True)


def load_monthly() -> pd.DataFrame:
    return pd.read_csv(MONTHLY, dtype=str) if MONTHLY.exists() else seed_from_phase2()


def load_status() -> pd.DataFrame:
    try:
        return pd.read_csv(STATUS, dtype=str).fillna("")
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return pd.DataFrame()


# ---------- fetching ----------

def check_robots(roaster: dict) -> tuple[bool, str]:
    return http_client.robots_check(collect.live_page_url(roaster["live_url"], 1))


def fetch_roaster(roaster: dict, month: str) -> pd.DataFrame:
    """This month's variant rows for one roaster (Phase 2's parsing, sizes and flags)."""
    rows, _ = collect.collect_live(roaster, collect.Handles(), snapshot=month)
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=COLUMNS)
    df["month"], df["fetched_at"] = month, df.served_ts
    return df.reindex(columns=COLUMNS).astype(str).replace({"None": "", "nan": ""})


def descriptions(roaster: dict, month: str) -> dict[str, str]:
    """product_id -> description text, from this month's cached products.json.
    Reads the cache only (no request); empty if the pages aren't cached."""
    out = {}
    for page in range(1, collect.LIVE_MAX_PAGES + 1):
        body = http_client.cached_body(collect.live_page_url(roaster["live_url"], page), month)
        if body is None:
            break
        items = json.loads(body).get("products", [])
        if not items:
            break
        out |= {str(p["id"]): clean_text(p.get("body_html")) for p in items}
    return out


def take_snapshot(month: str, monthly: pd.DataFrame, roasters: list[dict],
                  fetch=fetch_roaster, robots=check_robots) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fetch every enabled roaster not yet fetched this month.

    Returns (monthly with the new rows appended, one status row per roaster).
    fetch and robots are parameters so tests can fake the network.
    """
    new_parts, status = [monthly], []
    for r in roasters:
        row = {"month": month, "roaster": r["roaster"], "tier": r["tier"], "status": "",
               "robots": "", "n_products": 0, "prev_products": "", "big_drop": False, "error": ""}
        have = monthly[(monthly.month == month) & (monthly.roaster == r["roaster"])]
        if not r["enabled"]:
            row["status"] = "skipped_disabled"
        elif len(have):
            row.update(status="already_fetched", n_products=have.product_id.nunique())
        else:
            allowed, robots_status = robots(r)
            row["robots"] = robots_status
            if not allowed:
                row["status"] = "skipped_robots"
            else:
                try:
                    df = fetch(r, month)
                    if df.empty:
                        raise ValueError("products.json returned no products")
                    new_parts.append(df)
                    row.update(status="fetched", n_products=df.product_id.nunique())
                except Exception as err:  # noqa: BLE001 - any failure is logged, not fatal here
                    row.update(status="error", error=f"{type(err).__name__}: {err}"[:200])
        # Big drop: fewer than half of the products seen in this roaster's previous month.
        prev = monthly[(monthly.roaster == r["roaster"]) & (monthly.month < month)]
        if len(prev) and row["n_products"]:
            n_prev = prev[prev.month == prev.month.max()].product_id.nunique()
            row.update(prev_products=n_prev, big_drop=row["n_products"] < BIG_DROP * n_prev)
        status.append(row)
    return pd.concat(new_parts, ignore_index=True)[COLUMNS], pd.DataFrame(status)


def merge_status(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """Add this run's status rows. "already_fetched" adds nothing (the row from the
    run that fetched stays); any other status replaces an earlier row for the same
    roaster and month (e.g. an error last run, fetched now)."""
    new = new[new.status != "already_fetched"].astype(str)
    if old.empty:
        return new.reset_index(drop=True)
    keys = set(zip(new.month, new.roaster))
    keep = old[[(m, r) not in keys for m, r in zip(old.month, old.roaster)]]
    return pd.concat([keep, new], ignore_index=True).sort_values(["month", "roaster"], kind="stable")
