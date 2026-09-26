"""Wayback Machine helpers: list snapshots, choose one, fetch it raw.

A snapshot is identified by its timestamp ("20240523185941", YYYYMMDDhhmmss)
and the original URL it was captured from.
"""
import json
import re
from datetime import date, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

from src import http_client
from src.quarters import mid_quarter, quarter_of
from src.scout import CDX_TIMEOUT_SECONDS, cdx_query_url

# The archive sometimes serves a nearby capture instead of the exact one
# requested; the timestamp it really served is in the final URL.
_SERVED_TS = re.compile(r"/web/(\d{14})")


def ts_date(ts: str) -> date:
    return datetime.strptime(ts[:8], "%Y%m%d").date()


def ts_quarter(ts: str) -> str:
    return quarter_of(int(ts[:4]), int(ts[4:6]))


def nearest(timestamps, target: date, max_days: int | None = None) -> str | None:
    """The timestamp closest to `target`, optionally no more than max_days away."""
    best = min(timestamps, key=lambda ts: abs(ts_date(ts) - target), default=None)
    if best is None:
        return None
    if max_days is not None and abs(ts_date(best) - target) > timedelta(days=max_days):
        return None
    return best


def choose_mid_quarter(snapshots: dict[str, str], label: str) -> str | None:
    """From {timestamp: original_url}, the snapshot inside quarter `label` nearest its middle.

    Only snapshots inside the quarter count, so a quarter is never filled with
    a capture from a neighbouring quarter.
    """
    in_quarter = [ts for ts in snapshots if ts_quarter(ts) == label]
    return nearest(in_quarter, mid_quarter(label))


# ---------- pagination ----------

def page_number(original: str, listing_path: str) -> int | None:
    """Page number if `original` is page 2+ of the listing at `listing_path`, else None.

    Only URLs whose path is exactly the listing and whose query is just ?page=N
    count, so /collections/all-coffee isn't mistaken for /collections/all, and
    sorted or filtered views (?sort_by=...) are ignored.
    """
    parts = urlsplit(original)
    if parts.path.rstrip("/") != listing_path.rstrip("/"):
        return None
    query = parse_qs(parts.query)
    if set(query) != {"page"} or not query["page"][0].isdigit():
        return None
    page = int(query["page"][0])
    return page if page >= 2 else None


def paged_snapshots(listing_url: str) -> dict[int, list[tuple[str, str]]]:
    """{page number: [(timestamp, original), ...]} for archived pages 2+ of a listing.

    One CDX prefix query per listing URL; it returns every captured query-string
    variant of the path, which we then filter down to ?page=N.
    """
    parts = urlsplit(listing_url)
    body = http_client.fetch(cdx_query_url(parts.netloc + parts.path, prefix=True),
                             timeout=CDX_TIMEOUT_SECONDS)
    text = body.decode("utf-8").strip()
    rows = json.loads(text)[1:] if text else []
    pages: dict[int, list[tuple[str, str]]] = {}
    for ts, original in rows:
        n = page_number(original, parts.path)
        if n:
            pages.setdefault(n, []).append((ts, original))
    return pages


def linked_pages(html: str, listing_path: str) -> set[int]:
    """Page numbers (2+) the HTML links to for this listing, e.g. href="/collections/all?page=3"."""
    found = set()
    for href in re.findall(r'href="([^"]*[?&]page=\d+[^"]*)"', html):
        href = href.replace("&amp;", "&")
        # Relative links have no host; give them one so urlsplit reads the path.
        n = page_number(href if "//" in href else "https://x" + href, listing_path)
        if n:
            found.add(n)
    return found


# ---------- fetching ----------

def snapshot_url(ts: str, original: str) -> str:
    # "id_" asks for the page exactly as captured: no Wayback toolbar, no link rewriting.
    return f"https://web.archive.org/web/{ts}id_/{original}"


def fetch_snapshot(ts: str, original: str) -> tuple[str, str]:
    """Return (html, served_timestamp) for a snapshot, via the cache when possible."""
    url = snapshot_url(ts, original)
    body = http_client.fetch(url, timeout=CDX_TIMEOUT_SECONDS)
    meta = http_client.cached_meta(url) or {}
    match = _SERVED_TS.search(meta.get("final_url", ""))
    return body.decode("utf-8", errors="replace"), match.group(1) if match else ts
