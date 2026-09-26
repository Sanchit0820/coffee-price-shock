"""Phase 1 scout: how scrapeable and how well-archived is each candidate roaster?

For every row in data/roasters_candidates.csv this makes a handful of polite
requests (all through http_client, so they are rate-limited, robots-checked
and cached):
  1. robots.txt for the roaster's site (one request per host)
  2. <site>/products.json?limit=1 to see if it's a Shopify store (one product only)
  3. Wayback CDX queries: snapshot list for the shop page, and for
     /products.json if the store is Shopify

Results go to data/roasters_scout.csv, one row per roaster.

Run from the project root:
    python -m src.scout            # uses cached CDX responses if present
    python -m src.scout --refresh  # re-queries the CDX API
"""
import argparse
import csv
import json
from datetime import date, datetime, timezone
from urllib.parse import urlencode, urlsplit

import requests

from src import config, http_client
from src.quarters import quarter_labels, quarter_of  # noqa: F401 (quarter_labels re-exported)

CANDIDATES = config.DATA_DIR / "roasters_candidates.csv"
OUTPUT = config.DATA_DIR / "roasters_scout.csv"
CDX_ENDPOINT = "https://web.archive.org/cdx/search/cdx"
START_YEAR = 2023
# The CDX API can take over a minute on sites with few captures (Toise timed
# out twice at 30 s but answered "no snapshots" in a browser), so allow longer.
CDX_TIMEOUT_SECONDS = 120


# ---------- Wayback CDX ----------

def cdx_query_url(target: str, prefix: bool) -> str:
    """Build a CDX API URL listing successful (HTTP 200) captures since START_YEAR.

    `target` has no scheme or "www." requirement: the CDX index normalises
    URLs, so one query already matches http/https and www/non-www copies.
    prefix=True also matches the same path with any query string
    (products.json?page=2 etc.).
    """
    params = {
        "url": target,
        "from": str(START_YEAR),
        "output": "json",
        "fl": "timestamp,original",
        "filter": "statuscode:200",
    }
    if prefix:
        params["matchType"] = "prefix"
    return f"{CDX_ENDPOINT}?{urlencode(params)}"


def parse_cdx(body: bytes) -> dict[str, str]:
    """Turn a CDX JSON response into {timestamp: original_url}.

    The JSON is a list of rows whose first row is the header
    (["timestamp", "original"]). Keying by timestamp counts each capture
    once even if it was listed under two address variants.
    """
    text = body.decode("utf-8").strip()
    if not text:
        return {}
    rows = json.loads(text)
    return {ts: original for ts, original in rows[1:]}


def wayback_snapshots(target: str, prefix: bool, refresh: bool) -> dict[str, str]:
    body = http_client.fetch(cdx_query_url(target, prefix), refresh=refresh,
                             timeout=CDX_TIMEOUT_SECONDS)
    return parse_cdx(body)


def summarise(snapshots: dict[str, str], quarters: list[str], col: str) -> dict:
    """Per-quarter counts, number of covered quarters and earliest date, as CSV columns.

    Timestamps look like "20240523185941" (YYYYMMDDhhmmss).
    """
    counts = dict.fromkeys(quarters, 0)
    for ts in snapshots:
        q = quarter_of(int(ts[:4]), int(ts[4:6]))
        if q in counts:
            counts[q] += 1
    earliest = min(snapshots) if snapshots else ""
    out = {f"{col}_{q}": n for q, n in counts.items()}
    out[f"{col}_quarters_covered"] = sum(1 for n in counts.values() if n > 0)
    out[f"{col}_earliest"] = f"{earliest[:4]}-{earliest[4:6]}-{earliest[6:8]}" if earliest else ""
    return out


# ---------- Shopify ----------

def is_valid_products_json(body: bytes) -> bool:
    """True if body looks like Shopify's /products.json: products with priced variants."""
    try:
        data = json.loads(body)
    except ValueError:  # HTML page, empty body, etc.
        return False
    products = data.get("products") if isinstance(data, dict) else None
    if not isinstance(products, list) or not products:
        return False
    variants = products[0].get("variants")
    return isinstance(variants, list) and bool(variants) and "price" in variants[0]


def check_shopify(products_url: str) -> bool:
    try:
        body = http_client.fetch(products_url)
    except requests.HTTPError:  # e.g. 404: the endpoint doesn't exist
        return False
    return is_valid_products_json(body)


# ---------- one roaster ----------

def archive_snapshots(urls: list[str], refresh: bool) -> dict[str, str]:
    """Merge the snapshot lists of several URLs for the same listing page.

    Used when a roaster's beans page moved (e.g. Blue Tokai's /collections/coffee
    became /collections/roasted-and-ground-coffee-beans in 2024), so coverage
    counts the old and new addresses together.
    """
    merged: dict[str, str] = {}
    for url in urls:
        parts = urlsplit(url)
        merged.update(wayback_snapshots(parts.netloc + parts.path, prefix=False, refresh=refresh))
    return merged


def archive_urls(shop_url: str, extras: list[str], include_shop_url: bool) -> list[str]:
    """Which URLs count towards Wayback coverage.

    Normally the current shop page plus any older addresses. include_shop_url=False
    drops the current page, for roasters whose current page was not a product
    listing in the past (Subko's /pages/coffee was a brand-story page in 2023 and
    never carries embedded product data), so its snapshots would inflate coverage.
    """
    return ([shop_url] if include_shop_url else []) + extras


def scout_roaster(roaster: str, shop_url: str, quarters: list[str], refresh: bool,
                  extra_archive_urls: list[str] | None = None,
                  include_shop_url: bool = True) -> dict:
    parts = urlsplit(shop_url)
    origin = f"{parts.scheme}://{parts.netloc}"
    record = {
        "roaster": roaster,
        "shop_url": shop_url,
        "extra_archive_urls": " | ".join(extra_archive_urls or []),
        "domain": parts.netloc.removeprefix("www."),
        "terms_of_service_checked": "",  # filled in by hand
        "scouted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "error": "",
    }
    # Any failure (site down, bad response) is recorded and we move on,
    # so one broken site doesn't stop the whole run.
    try:
        products_url = f"{origin}/products.json?limit=1"
        shop_allowed, robots_status = http_client.robots_check(shop_url)
        products_allowed, _ = http_client.robots_check(products_url)
        record.update(robots_status=robots_status, shop_allowed=shop_allowed,
                      products_json_allowed=products_allowed)

        # Blank (unknown) if robots.txt forbids us from checking.
        is_shopify = check_shopify(products_url) if products_allowed else ""
        record["is_shopify"] = is_shopify

        # The Wayback checks hit archive.org, not the roaster, so they run
        # even if the roaster's own robots.txt blocks us.
        counted = archive_urls(shop_url, extra_archive_urls or [], include_shop_url)
        record["archive_urls_counted"] = " | ".join(counted)
        shop_snaps = archive_snapshots(counted, refresh)
        record.update(summarise(shop_snaps, quarters, "shop"))
        record["shop_variants_seen"] = " | ".join(sorted(set(shop_snaps.values())))

        if is_shopify:
            pj_snaps = wayback_snapshots(parts.netloc + "/products.json", prefix=True, refresh=refresh)
            record.update(summarise(pj_snaps, quarters, "pj"))
    except Exception as err:  # noqa: BLE001 - deliberately broad, see comment above
        record["error"] = f"{type(err).__name__}: {err}"
    return record


# ---------- CSV in / out ----------

def output_columns(quarters: list[str]) -> list[str]:
    cols = ["roaster", "shop_url", "extra_archive_urls", "url_switch_window", "domain", "robots_status", "shop_allowed",
            "products_json_allowed", "is_shopify", "terms_of_service_checked"]
    for prefix in ("shop", "pj"):
        cols += [f"{prefix}_{q}" for q in quarters]
        cols += [f"{prefix}_quarters_covered", f"{prefix}_earliest"]
    return cols + ["archive_urls_counted", "shop_variants_seen", "scouted_at", "error"]


def read_candidates() -> list[dict]:
    # utf-8-sig silently drops a byte-order mark if Excel added one.
    with CANDIDATES.open(encoding="utf-8-sig", newline="") as f:
        return [row for row in csv.DictReader(f) if row["shop_url"].strip()]


def write_results(records: list[dict], quarters: list[str]) -> None:
    # restval="" leaves columns blank when a roaster has no data for them
    # (e.g. pj_* for non-Shopify stores).
    with OUTPUT.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=output_columns(quarters), restval="")
        writer.writeheader()
        writer.writerows(records)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--refresh", action="store_true",
                        help="re-query the Wayback CDX API instead of using cached responses")
    args = parser.parse_args()

    quarters = quarter_labels(START_YEAR, date.today())
    records = []
    for row in read_candidates():
        print(f"Scouting {row['roaster']} ...", flush=True)
        # Optional column: older addresses of the same page, separated by "|".
        extras = [u.strip() for u in (row.get("extra_archive_urls") or "").split("|") if u.strip()]
        # Optional column: "no" = don't count the current shop page's snapshots
        # (see archive_urls). Blank or anything else = count it.
        include_shop = (row.get("archive_shop_url") or "").strip().lower() != "no"
        record = scout_roaster(row["roaster"], row["shop_url"].strip(), quarters, args.refresh,
                               extras, include_shop)
        # Copied through unchanged: when a stitched roaster moved from its old
        # URL/platform to the new one. A price or pack-size jump in this window
        # must be checked by hand before it counts as a real change.
        record["url_switch_window"] = row.get("url_switch_window") or ""
        if record["error"]:
            print(f"  error: {record['error']}")
        records.append(record)

    write_results(records, quarters)
    print(f"Wrote {len(records)} rows to {OUTPUT}")


if __name__ == "__main__":
    main()
