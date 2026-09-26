"""Stage 2: archived product pages, only to fill pack sizes missing from listings.

For every (roaster, product, quarter) where a coffee (or ambiguous) row has no
size, fetch the product page's snapshot from THAT quarter, so a size change
over time is captured rather than assumed away. If the product page has no
snapshot in that quarter, the size stays empty and the status says why.

Output: data/clean/product_page_sizes.csv, applied to variants_long.csv when
stage 1 is rebuilt (collect.stage1 reads it).
"""
import json
import re
from urllib.parse import urlencode, urlsplit

import pandas as pd

from src import config, http_client, scout, wayback
from src.product_pages import variant_sizes

SIZES_OUT = config.CLEAN_DIR / "product_page_sizes.csv"


# ---------- handle discovery ----------

def discovery_url(host: str) -> str:
    """CDX query listing each distinct archived /products/ URL on a host (one row per URL)."""
    params = {"url": f"{host}/products/", "matchType": "prefix", "from": str(scout.START_YEAR),
              "output": "json", "fl": "original", "collapse": "urlkey",
              "filter": "statuscode:200"}
    return f"{scout.CDX_ENDPOINT}?{urlencode(params)}"


def archived_handles(host: str) -> set[str]:
    body = http_client.fetch(discovery_url(host), timeout=scout.CDX_TIMEOUT_SECONDS)
    text = body.decode("utf-8").strip()
    rows = json.loads(text)[1:] if text else []
    handles = set()
    for (original,) in rows:
        m = re.match(r"/products/([^/?#]+)/?$", urlsplit(original).path)
        if m:
            handles.add(m.group(1).lower())
    return handles


def match_handle(slug: str, handles: set[str]) -> tuple[str, str]:
    """(handle, how) for a product-title slug among archived handles, or ("", "unmapped").

    Exact slug first; then a UNIQUE handle that extends the slug (Shopify adds
    "-1" for duplicates) or that the slug extends (titles often gain words
    like "coffee" later). Ambiguous matches are not guessed.
    """
    if slug in handles:
        return slug, "cdx_exact"
    near = [h for h in handles if h.startswith(slug + "-") or slug.startswith(h + "-")]
    return (near[0], "cdx_prefix") if len(near) == 1 else ("", "unmapped")


# ---------- work list ----------

def targets(variants: pd.DataFrame) -> pd.DataFrame:
    """One row per (roaster, product, quarter) needing a size, with the listing's date.

    Rows served from outside their quarter are skipped (they're excluded from
    quarter-level use anyway). Rows already filled by an earlier stage 2 run
    count as still needing a product page, so re-running rebuilds the same
    work list instead of shrinking it (and dropping those sizes).
    """
    no_listing_size = (variants.size_grams.isna()
                       | variants.size_source.fillna("").str.startswith("product_page"))
    a = variants[(variants.source_type == "archive") & no_listing_size
                 & (variants.is_coffee_guess.astype(str) != "False")
                 & (variants.served_outside_quarter.astype(str) != "True")]
    a = a.assign(host=a.source_url.map(lambda u: urlsplit(u).netloc))
    return (a.groupby(["roaster", "product_id", "quarter"], as_index=False)
             .agg(host=("host", "first"), product_title=("product_title", "first"),
                  served_ts=("served_ts", "first")))


def resolve_handles(work: pd.DataFrame, known: pd.DataFrame) -> pd.DataFrame:
    """Attach a handle to each product: stage 1's mapping, else archive discovery."""
    from src.collect import slugify  # imported here: collect imports this module (avoids a cycle)
    work = work.merge(known[["roaster", "product_id", "handle", "handle_source"]],
                      on=["roaster", "product_id"], how="left").fillna({"handle": "", "handle_source": "unmapped"})
    missing = work[work.handle == ""]
    discovered = {h: archived_handles(h) for h in sorted(missing.host.unique())}
    for i, r in missing.iterrows():
        handle, how = match_handle(slugify(r.product_title), discovered[r.host])
        work.loc[i, ["handle", "handle_source"]] = [handle, how]
    return work


# ---------- fetching ----------

def fetch_quarter(host: str, handle: str, quarter: str, served_ts: str) -> tuple[str, str, dict]:
    """(status, product snapshot ts, {variant_id: size info}) for one product-quarter."""
    snaps = scout.wayback_snapshots(f"{host}/products/{handle}", prefix=False, refresh=False)
    in_q = [ts for ts in snaps if wayback.ts_quarter(ts) == quarter]
    # Nearest to the listing snapshot we're filling, so both describe the same moment.
    ts = wayback.nearest(in_q, wayback.ts_date(served_ts))
    if ts is None:
        return "no_snapshot_in_quarter", "", {}
    html, served = wayback.fetch_snapshot(ts, snaps[ts])
    sizes = variant_sizes(html)
    return ("ok" if sizes else "no_variant_data"), served, sizes


def run() -> pd.DataFrame:
    from src.collect import HANDLES_OUT, VARIANTS_OUT, with_retry  # see resolve_handles
    variants = pd.read_csv(VARIANTS_OUT, dtype={"product_id": str, "variant_id": str,
                                                "served_ts": str})
    known = pd.read_csv(HANDLES_OUT, dtype={"product_id": str}).fillna("")
    work = resolve_handles(targets(variants), known)
    out = []
    for r in work.itertuples():
        base = {"roaster": r.roaster, "product_id": r.product_id, "quarter": r.quarter,
                "handle": r.handle, "handle_source": r.handle_source}
        if not r.handle:
            out.append({**base, "status": "unmapped"})
            continue
        print(f"{r.roaster} {r.quarter} {r.handle}", flush=True)
        try:
            status, ts, sizes = with_retry(fetch_quarter, r.host, r.handle, r.quarter, r.served_ts)
        except Exception as err:  # noqa: BLE001 - record and continue
            out.append({**base, "status": f"error: {type(err).__name__}"})
            continue
        if not sizes:
            out.append({**base, "status": status, "product_snapshot_ts": ts})
        for vid, info in sizes.items():
            out.append({**base, "status": status, "product_snapshot_ts": ts,
                        "variant_id": str(vid), **info})
    df = pd.DataFrame(out)
    df.to_csv(SIZES_OUT, index=False)
    return df
