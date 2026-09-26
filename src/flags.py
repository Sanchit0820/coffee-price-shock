"""Row-level flags for the collected price data. All pure functions (no network)."""
import re
import statistics
from datetime import date

from bs4 import BeautifulSoup

from src.quarters import next_quarter, quarter_of_date
from src.sizes import Size, parse_size_grams

SALE_DROP = 0.90     # price below 90% of the previous quarter = a drop
SALE_REVERT = 0.95   # back to at least 95% of the pre-drop price = reverted


# ---------- pagination ----------

def completeness(expected: set[int], found: set[int]) -> tuple[str, list[int]]:
    """("single_page" | "complete" | "partial", missing page numbers).

    `expected` = page numbers 2+ that the listing links to; `found` = those we
    have archived copies of. A partial quarter must not be read as a smaller
    product range.
    """
    if not expected:
        return "single_page", []
    missing = sorted(expected - found)
    return ("partial" if missing else "complete"), missing


# ---------- URL switch windows ----------

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_AFTER_Q = re.compile(r"after (\d{4})-Q([1-4])")


def in_switch_window(window: str, served: date) -> bool:
    """Is a snapshot served on `served` inside a roaster's URL/platform switch window?

    Handles the three forms used in roasters_final.csv:
      "2024-04-18 to 2024-05-23 (...)"  -> between the two dates
      "2026-03-07 (...)"                -> in the same quarter as that date
      "after 2024-Q2 (...)"             -> in the quarter right after 2024-Q2
    """
    if not window:
        return False
    after = _AFTER_Q.search(window)
    if after:
        return quarter_of_date(served) == next_quarter(f"{after.group(1)}Q{after.group(2)}")
    dates = [date.fromisoformat(d) for d in _DATE.findall(window)]
    if len(dates) >= 2:
        return dates[0] <= served <= dates[1]
    if len(dates) == 1:
        return quarter_of_date(served) == quarter_of_date(dates[0])
    return False


# ---------- sales ----------

def sale_status(prev: float | None, price: float | None, nxt: float | None) -> str:
    """"candidate", "False" or "not_checkable" for one variant in one quarter.

    A candidate is a drop of more than 10% from the previous observed quarter
    that is back to within 5% of the old price in the next observed quarter.
    Stage 2 confirms or rejects candidates using the product page's compare-at price.
    """
    if prev is None or price is None or nxt is None:
        return "not_checkable"
    if price < SALE_DROP * prev and nxt >= SALE_REVERT * prev:
        return "candidate"
    return "False"


def mark_sales(rows: list[dict]) -> None:
    """Fill rows[i]["sale_suspected"] for archived rows, one roaster at a time.

    "Previous/next quarter" means the roaster's previous/next OBSERVED quarter,
    so gaps in the archive don't break the comparison. Rows in a roaster's first
    or last observed quarter, and variants missing from either neighbour, get
    "not_checkable". Variants are matched by variant ID.
    """
    by_roaster: dict[str, list[dict]] = {}
    for r in rows:
        if r["source_type"] != "archive":
            continue
        if r.get("served_outside_quarter"):
            # Its capture belongs to another quarter, so it can't be anyone's
            # neighbour and can't be checked itself.
            r["sale_suspected"] = "not_checkable"
            continue
        by_roaster.setdefault(r["roaster"], []).append(r)
    for roaster_rows in by_roaster.values():
        quarters = sorted({r["quarter"] for r in roaster_rows})
        price = {(r["variant_id"], r["quarter"]): r["price_inr"] for r in roaster_rows}
        for r in roaster_rows:
            i = quarters.index(r["quarter"])
            if i == 0 or i == len(quarters) - 1:
                r["sale_suspected"] = "not_checkable"
                continue
            r["sale_suspected"] = sale_status(price.get((r["variant_id"], quarters[i - 1])),
                                              r["price_inr"],
                                              price.get((r["variant_id"], quarters[i + 1])))


# ---------- variant ID continuity ----------

ID_BREAK_BELOW = 0.10  # under 10% of IDs carried over = the catalogue was rebuilt


def id_carryover(rows: list[dict]) -> dict[str, float | None]:
    """{quarter: share of the previous observed quarter's variant IDs still present}.

    Low carryover with the same products means the shop re-created its catalogue
    (e.g. Devans renamed every product in 2024 and all IDs changed), so variant
    IDs can't link rows across that point. The first quarter has no previous
    one and gets None.
    """
    ids: dict[str, set] = {}
    for r in rows:
        ids.setdefault(r["quarter"], set()).add(r["variant_id"])
    quarters = sorted(ids)
    out = {quarters[0]: None} if quarters else {}
    for prev, cur in zip(quarters, quarters[1:]):
        out[cur] = round(len(ids[prev] & ids[cur]) / len(ids[prev]), 3)
    return out


# ---------- live vs latest archive ----------

def compare_live(archive_latest: list[dict], live: list[dict]) -> dict:
    """Compare live prices with the latest archived quarter, variant by variant.

    Returns matched count, median % difference (live vs archive), and the share
    of matched variants that are higher / lower by more than 1%. A consistent
    gap (e.g. every live price ~18% higher) points to a systematic difference,
    such as GST-inclusive vs exclusive prices, rather than normal price changes.
    """
    archived = {r["variant_id"]: r["price_inr"] for r in archive_latest if r["price_inr"]}
    diffs = [(r["price_inr"] / archived[r["variant_id"]] - 1) * 100
             for r in live if r["variant_id"] in archived and r["price_inr"]]
    if not diffs:
        return {"live_matched": 0, "live_median_pct_diff": None,
                "live_share_higher": None, "live_share_lower": None}
    return {
        "live_matched": len(diffs),
        "live_median_pct_diff": round(statistics.median(diffs), 2),
        "live_share_higher": round(sum(d > 1 for d in diffs) / len(diffs), 3),
        "live_share_lower": round(sum(d < -1 for d in diffs) / len(diffs), 3),
    }


# ---------- page-wide size (Dope) ----------

def uniform_listing_size(html: str) -> Size | None:
    """The pack size if the listing's visible text shows exactly one distinct size.

    For shops that sell a single pack size and only print it on the page
    (Dope: "250 gm"). If two different sizes appear, we can't tell which
    product is which, so return None.
    """
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    sizes = set()
    for chunk in re.findall(r"\d+(?:\.\d+)?\s*[a-zA-Z]+", soup.get_text(" ")):
        s = parse_size_grams(chunk)
        if s:
            sizes.add(s)
    return sizes.pop() if len(sizes) == 1 else None
