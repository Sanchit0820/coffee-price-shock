"""Phase 2: collect historical and live prices for the roasters in roasters_final.csv.

    python -m src.collect stage1            # archived listings + live products.json
    python -m src.collect stage2 --dry-run  # count product-page requests stage 2 would make

Stage 1 writes:
  data/clean/variants_long.csv    one row per variant per roaster-quarter (+ live)
  data/clean/coverage_report.csv  one row per roaster-quarter (+ live)
  data/clean/product_handles.csv  product ID -> URL handle, needed for stage 2

Everything goes through http_client (robots, rate limit, cache), so re-running
rebuilds the outputs from the cache without new requests.
"""
import argparse
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from urllib.parse import urlsplit

import pandas as pd

from src import config, http_client, scout, wayback
from src.coffee_filter import is_coffee_guess
from src.flags import (ID_BREAK_BELOW, compare_live, completeness, id_carryover,
                       in_switch_window, mark_sales, uniform_listing_size)
from src.quarters import quarter_labels, quarter_of_date
from src.shopify_meta import extract_meta_products, variant_rows
from src.sizes import parse_size_grams

FINAL = config.DATA_DIR / "roasters_final.csv"
SCOUT = config.DATA_DIR / "roasters_scout.csv"
VARIANTS_OUT = config.CLEAN_DIR / "variants_long.csv"
COVERAGE_OUT = config.CLEAN_DIR / "coverage_report.csv"
HANDLES_OUT = config.CLEAN_DIR / "product_handles.csv"
PAGE_WINDOW_DAYS = 30   # extra pages must be captured within ±30 days of page 1
LIVE_MAX_PAGES = 5      # products.json pages of 250; no roaster has >1,250 products
# Black Baza's variant IDs changed when it moved platform in 2025, so IDs can't
# link old and new rows; Phase 3 matches those by product name instead. Other
# roasters are added automatically if a catalogue rebuild is detected (see id_carryover).
UNSTABLE_IDS = {"Black Baza"}
# Shops that sell ONE pack size and print it only on the page (not in variant
# data). Only for these may a size seen once on the listing fill every variant;
# elsewhere a lone size on the page doesn't prove which product it belongs to.
SINGLE_SIZE_ROASTERS = {"Dope Coffee"}

VARIANT_COLUMNS = [
    "roaster", "tier", "quarter", "source_type", "requested_ts", "served_ts",
    "served_outside_quarter", "source_url", "page", "product_id", "product_title",
    "product_type", "variant_id", "variant_title", "sku", "price_inr",
    "compare_at_price_inr", "size_grams", "multipack", "size_source", "is_coffee_guess",
    "in_switch_window", "variant_ids_stable", "sale_suspected",
]


@dataclass
class Handles:
    """What we learn about product URL handles while collecting (used by stage 2).

    live:  (roaster, product_id) -> handle, exact, from products.json
    links: host -> every /products/<handle> linked from that host's listings
    """
    live: dict = field(default_factory=dict)
    links: dict = field(default_factory=dict)


def with_retry(fn, *args):
    """The archive returns occasional 5xx errors and timeouts: try twice, then raise."""
    try:
        return fn(*args)
    except Exception:  # noqa: BLE001 - any failure gets exactly one retry
        return fn(*args)


# ---------- inputs ----------

def load_roasters() -> list[dict]:
    """Final list joined with the exact archive URLs the scout counted."""
    final = pd.read_csv(FINAL, dtype=str).fillna("")
    counted = pd.read_csv(SCOUT, dtype=str).set_index("roaster")["archive_urls_counted"]
    roasters = []
    for r in final.to_dict("records"):
        r["archive_urls"] = [u.strip() for u in counted[r["roaster"]].split("|") if u.strip()]
        # The last listing URL in roasters_final.csv is the current one (they're in date order).
        r["live_url"] = [u.strip() for u in r["archive_listing_urls"].split("|")][-1]
        roasters.append(r)
    return roasters


# ---------- sizes and coffee flag ----------

def resolve_size(variant_title: str, product_title: str, page_size) -> tuple:
    """(grams, multipack, source): variant title, then product title, then page-wide size."""
    for text, source in ((variant_title, "variant_title"), (product_title, "product_title")):
        s = parse_size_grams(text)
        if s:
            return s.grams, s.multipack, source
    if page_size:
        return page_size.grams, page_size.multipack, "listing_text"
    return None, None, ""


def finish_row(row: dict, page_size=None) -> dict:
    grams, multipack, source = resolve_size(row["variant_title"], row["product_title"], page_size)
    if grams is None and row.get("_live_grams"):
        # products.json "grams" is SHIPPING weight (can include packaging), so
        # it's only a last resort and labelled as such.
        grams, multipack, source = row["_live_grams"], False, "live_shipping_grams"
    row.pop("_live_grams", None)
    row.update(size_grams=grams, multipack=multipack, size_source=source,
               is_coffee_guess=is_coffee_guess(row["product_title"], row["product_type"],
                                               grams is not None))
    return row


# ---------- archived listings ----------

def fetch_listing_pages(page1_html: str, served_ts: str, listing_url: str,
                        paged: dict[int, list[tuple[str, str]]]) -> tuple[dict, set, set]:
    """Fetch pages 2+ nearest the page-1 date. Returns ({page: (html, ts, url)}, expected, found)."""
    path = urlsplit(listing_url).path
    expected = wayback.linked_pages(page1_html, path)
    pages, tried = {}, set()
    target = wayback.ts_date(served_ts)
    # Later pages can link to pages page 1 didn't (e.g. "1 2 3 ... 7"), so keep going
    # until every expected page has been tried once.
    while expected - tried:
        n = min(expected - tried)
        tried.add(n)
        candidates = {ts: orig for ts, orig in paged.get(n, [])}
        ts = wayback.nearest(candidates, target, max_days=PAGE_WINDOW_DAYS)
        if ts is None:
            continue
        try:
            html, served = with_retry(wayback.fetch_snapshot, ts, candidates[ts])
        except Exception:  # noqa: BLE001 - a failed page counts as missing
            continue
        pages[n] = (html, served, candidates[ts])
        expected |= wayback.linked_pages(html, path)
    return pages, expected, set(pages)


def rows_from_page(html, roaster, label, requested_ts, served_ts, url, page) -> list[dict]:
    products = extract_meta_products(html) or []
    page_size = uniform_listing_size(html) if roaster["roaster"] in SINGLE_SIZE_ROASTERS else None
    rows = []
    for v in variant_rows(products):
        v.update(roaster=roaster["roaster"], tier=roaster["tier"], quarter=label,
                 source_type="archive", requested_ts=requested_ts, served_ts=served_ts,
                 served_outside_quarter=wayback.ts_quarter(served_ts) != label,
                 source_url=url, page=page, compare_at_price_inr=None,
                 in_switch_window=in_switch_window(roaster["url_switch_window"],
                                                   wayback.ts_date(served_ts)),
                 variant_ids_stable=roaster["roaster"] not in UNSTABLE_IDS,
                 sale_suspected="")
        rows.append(finish_row(v, page_size))
    return rows


def collect_archive(roaster: dict, handles: Handles) -> tuple[list[dict], list[dict]]:
    snaps = scout.archive_snapshots(roaster["archive_urls"], refresh=False)
    paged = {}
    for url in roaster["archive_urls"]:
        for n, caps in with_retry(wayback.paged_snapshots, url).items():
            paged.setdefault(n, []).extend(caps)
    rows, coverage = [], []
    for label in quarter_labels(scout.START_YEAR, date.today()):
        ts = wayback.choose_mid_quarter(snaps, label)
        if ts is None:
            continue
        url = snaps[ts]
        try:
            html, served = with_retry(wayback.fetch_snapshot, ts, url)
        except Exception as err:  # noqa: BLE001 - record and move to the next quarter
            coverage.append(coverage_row(roaster, label, "archive", ts, "", url, [],
                                         error=f"{type(err).__name__}: {err}"[:200]))
            continue
        q_rows = rows_from_page(html, roaster, label, ts, served, url, 1)
        extra, expected, found = fetch_listing_pages(html, served, url, paged)
        for n, (p_html, p_served, p_url) in sorted(extra.items()):
            q_rows += rows_from_page(p_html, roaster, label, ts, p_served, p_url, n)
        collect_handles([html] + [p[0] for p in extra.values()], urlsplit(url).netloc, handles)
        flag, missing = completeness(expected, found)
        rows += q_rows
        coverage.append(coverage_row(roaster, label, "archive", ts, served, url, q_rows,
                                     pages_expected=1 + len(expected),
                                     pages_found=1 + len(found),
                                     missing_pages=" ".join(map(str, missing)),
                                     completeness=flag))
    return rows, coverage


# ---------- live products.json ----------

def collect_live(roaster: dict, handles: Handles) -> tuple[list[dict], dict]:
    """Current prices from the collection's products.json, labelled as today's quarter.

    The collection-scoped endpoint (/collections/<handle>/products.json) keeps the
    same product scope as the archived listing; /products.json would add equipment.
    """
    parts = urlsplit(roaster["live_url"])
    label = quarter_of_date(date.today())
    rows, fetched_at = [], ""
    for page in range(1, LIVE_MAX_PAGES + 1):
        url = f"{parts.scheme}://{parts.netloc}{parts.path}/products.json?limit=250&page={page}"
        products = json.loads(http_client.fetch(url)).get("products", [])
        fetched_at = fetched_at or (http_client.cached_meta(url) or {}).get("fetched_at", "")
        if not products:
            break
        for p in products:
            handles.live[(roaster["roaster"], str(p["id"]))] = p["handle"]
            for v in p["variants"]:
                title = "" if v.get("title") == "Default Title" else v.get("title", "")
                rows.append(finish_row({
                    "roaster": roaster["roaster"], "tier": roaster["tier"], "quarter": label,
                    "source_type": "live", "requested_ts": "", "served_ts": fetched_at,
                    "served_outside_quarter": False, "source_url": url, "page": page,
                    "product_id": p["id"], "product_title": p["title"],
                    "product_type": p.get("product_type") or "", "variant_id": v["id"],
                    "variant_title": title, "sku": v.get("sku") or "",
                    # products.json prices are rupee strings ("650.00"), not paise.
                    "price_inr": float(v["price"]) if v.get("price") else None,
                    "compare_at_price_inr": float(v["compare_at_price"]) if v.get("compare_at_price") else None,
                    "in_switch_window": False,
                    "variant_ids_stable": roaster["roaster"] not in UNSTABLE_IDS,
                    # The live snapshot shows the sale state directly: on sale if
                    # the compare-at ("was") price is above the price.
                    "sale_suspected": str(bool(v.get("compare_at_price") and v.get("price")
                                               and float(v["compare_at_price"]) > float(v["price"]))),
                    "_live_grams": v.get("grams") or None,
                }))
    served = fetched_at[:10].replace("-", "")
    cov = coverage_row(roaster, label, "live", "", served, roaster["live_url"], rows,
                       pages_expected="", pages_found="", missing_pages="", completeness="live")
    return rows, cov


# ---------- product handles (for stage 2) ----------

_PRODUCT_LINK = re.compile(r"/products/([a-z0-9][a-z0-9\-]*)", re.IGNORECASE)


def collect_handles(htmls: list[str], host: str, handles: Handles) -> None:
    """Remember every /products/<handle> linked from a listing, keyed by host."""
    found = handles.links.setdefault(host, set())
    for html in htmls:
        found.update(h.lower() for h in _PRODUCT_LINK.findall(html))


def slugify(title: str) -> str:
    """"Monsoon Malabar AA" -> "monsoon-malabar-aa" (how Shopify builds default handles)."""
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def map_handles(rows: list[dict], handles: Handles) -> pd.DataFrame:
    """Product ID -> handle: live products.json first (exact), then the title's slug
    if a listing linked to it. Anything else is "unmapped" and stage 2 skips it."""
    out = []
    seen = set()
    for r in rows:
        key = (r["roaster"], str(r["product_id"]))
        if r["source_type"] != "archive" or key in seen:
            continue
        seen.add(key)
        host = urlsplit(r["source_url"]).netloc
        if key in handles.live:
            handle, how = handles.live[key], "live"
        elif slugify(r["product_title"]) in handles.links.get(host, set()):
            handle, how = slugify(r["product_title"]), "title_slug"
        else:
            handle, how = "", "unmapped"
        out.append({"roaster": key[0], "product_id": key[1], "host": host,
                    "product_title": r["product_title"], "handle": handle, "handle_source": how})
    return pd.DataFrame(out)


# ---------- coverage ----------

def coverage_row(roaster, label, source_type, requested_ts, served_ts, url, rows, **pages) -> dict:
    n = len(rows)
    pct = lambda k: round(100 * k / n, 1) if n else None  # noqa: E731
    return {
        "roaster": roaster["roaster"], "tier": roaster["tier"], "quarter": label,
        "source_type": source_type, "requested_ts": requested_ts, "served_ts": served_ts,
        "snapshot_date": (datetime.strptime(served_ts[:8], "%Y%m%d").date().isoformat()
                          if served_ts else ""),
        "served_outside_quarter": (source_type == "archive" and bool(served_ts)
                                   and wayback.ts_quarter(served_ts) != label),
        "source_url": url, **pages, "variant_count": n,
        "pct_sized": pct(sum(r["size_grams"] is not None for r in rows)),
        "pct_non_coffee": pct(sum(r["is_coffee_guess"] is False for r in rows)),
        "pct_coffee_ambiguous": pct(sum(r["is_coffee_guess"] is None for r in rows)),
    }


# ---------- stages ----------

def mark_id_continuity(name: str, a_rows: list[dict], l_rows: list[dict], a_cov: list[dict]) -> None:
    """Add id_carryover / id_break to coverage rows; if the roaster has any break,
    mark all its rows variant_ids_stable = False (IDs can't link across the break)."""
    carry = id_carryover(a_rows)
    for c in a_cov:
        share = carry.get(c["quarter"])
        c["id_carryover"] = share
        c["id_break"] = share is not None and share < ID_BREAK_BELOW
    if name in UNSTABLE_IDS or any(c["id_break"] for c in a_cov):
        for r in a_rows + l_rows:
            r["variant_ids_stable"] = False


def live_or_error(roaster: dict, handles: Handles) -> tuple[list[dict], dict]:
    try:
        return collect_live(roaster, handles)
    except Exception as err:  # noqa: BLE001 - e.g. robots.txt disallows, site down
        return [], coverage_row(roaster, quarter_of_date(date.today()), "live", "", "",
                                roaster["live_url"], [], error=f"{type(err).__name__}: {err}"[:200])


def stage1() -> None:
    config.CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    rows, coverage, handles = [], [], Handles()
    for roaster in load_roasters():
        print(f"{roaster['roaster']}: archive ...", flush=True)
        a_rows, a_cov = collect_archive(roaster, handles)
        print(f"{roaster['roaster']}: live ...", flush=True)
        l_rows, l_cov = live_or_error(roaster, handles)
        # Compare live prices with the latest archived quarter that has data.
        observed = [c["quarter"] for c in a_cov if c["variant_count"]]
        if observed and l_rows:
            latest = observed[-1]
            l_cov.update(compare_live([r for r in a_rows if r["quarter"] == latest], l_rows),
                         live_compared_with=latest)
        mark_id_continuity(roaster["roaster"], a_rows, l_rows, a_cov)
        rows += a_rows + l_rows
        coverage += a_cov + [l_cov]
    mark_sales(rows)
    pd.DataFrame(rows, columns=VARIANT_COLUMNS).to_csv(VARIANTS_OUT, index=False)
    pd.DataFrame(coverage).to_csv(COVERAGE_OUT, index=False)
    map_handles(rows, handles).to_csv(HANDLES_OUT, index=False)
    print(f"Wrote {len(rows)} variant rows, {len(coverage)} coverage rows")


def stage2_dry_run() -> None:
    """Count the product-page requests stage 2 would make, from stage 1's outputs."""
    rows = pd.read_csv(VARIANTS_OUT, dtype={"product_id": str})
    handles = pd.read_csv(HANDLES_OUT, dtype={"product_id": str}).fillna("")
    archive = rows[rows.source_type == "archive"]
    # (a) sizes: coffee or ambiguous rows with no size
    need_size = archive[archive.size_grams.isna() & (archive.is_coffee_guess.astype(str) != "False")]
    # (b) sale candidates
    sales = archive[archive.sale_suspected == "candidate"]
    report = {}
    for name, df in (("sizes", need_size), ("sales", sales)):
        keys = df[["roaster", "product_id", "quarter"]].drop_duplicates()
        prods = keys[["roaster", "product_id"]].drop_duplicates().merge(handles, how="left")
        mapped = prods[prods.handle != ""]
        cdx_uncached = sum(
            http_client.cached_meta(scout.cdx_query_url(f"{h.host}/products/{h.handle}", False)) is None
            for h in mapped.itertuples())
        report[name] = dict(rows=len(df), product_quarters=len(keys), products=len(prods),
                            products_mapped=len(mapped), cdx_requests=cdx_uncached,
                            page_fetches_per_quarter=len(keys.merge(mapped[["roaster", "product_id"]])),
                            page_fetches_one_per_product=len(mapped))
        print(f"\n({name}) " + ", ".join(f"{k}={v}" for k, v in report[name].items()))
        print(prods.groupby("roaster").size().to_string())
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 2 price collection")
    parser.add_argument("stage", choices=["stage1", "stage2"])
    parser.add_argument("--dry-run", action="store_true", help="stage2: count requests only")
    args = parser.parse_args()
    if args.stage == "stage1":
        stage1()
    elif args.dry_run:
        stage2_dry_run()
    else:
        raise SystemExit("stage2 fetching isn't built yet; run with --dry-run")


if __name__ == "__main__":
    main()
