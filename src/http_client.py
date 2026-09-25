"""Polite, cached HTTP fetching.

fetch(url) is the only function the rest of the pipeline needs. It:
  1. returns the cached copy from data/raw if we have ever fetched this URL
     (so we never hit a site twice for the same page);
  2. otherwise checks robots.txt and refuses disallowed URLs;
  3. waits so requests to one host are spaced out;
  4. downloads, and saves the body plus a small metadata file to data/raw.

Only successful (HTTP 200) responses are cached; errors raise, so a temporary
failure can be retried later.
"""
import hashlib
import json
from datetime import datetime, timezone
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests

from src import config
from src.ratelimit import RateLimiter

USER_AGENT = "coffee-price-research/0.1 (personal academic project"
USER_AGENT += f"; contact: {config.CONTACT_EMAIL})" if config.CONTACT_EMAIL else ")"

_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT
_limiter = RateLimiter(config.SCRAPE_DELAY_SECONDS)
_robots: dict[str, RobotFileParser] = {}  # host -> parsed robots.txt, fetched once per run


class DisallowedByRobots(Exception):
    """Raised when robots.txt forbids fetching a URL."""


# ---------- cache ----------

def _cache_paths(url: str):
    """Map a URL to (body_path, meta_path) under data/raw/<host>/.

    File names are a hash of the full URL, because URLs contain characters
    (?, :, /) that are not valid in Windows file names.
    """
    host = urlsplit(url).netloc.replace(":", "_")
    key = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    folder = config.RAW_DIR / host
    return folder / f"{key}.body", folder / f"{key}.meta.json"


def _read_cache(url: str) -> bytes | None:
    body_path, meta_path = _cache_paths(url)
    # Require both files: a body without meta means a write was interrupted.
    if body_path.exists() and meta_path.exists():
        return body_path.read_bytes()
    return None


def _write_cache(url: str, response: requests.Response) -> None:
    body_path, meta_path = _cache_paths(url)
    body_path.parent.mkdir(parents=True, exist_ok=True)
    body_path.write_bytes(response.content)
    meta = {
        "url": url,
        "final_url": response.url,  # differs from url if there was a redirect
        "status": response.status_code,
        "content_type": response.headers.get("Content-Type", ""),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    # Meta is written last, so its presence marks a complete cache entry.
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


# ---------- robots.txt ----------

def _load_robots(scheme: str, host: str) -> RobotFileParser:
    """Download and parse robots.txt for a host.

    We download it with our own session (not RobotFileParser.read()) so the
    request carries our User-Agent and timeout. Status handling follows the
    robots.txt standard (RFC 9309):
      - 200         -> obey the rules in the file
      - 401 / 403   -> treat the whole site as off-limits
      - other 4xx   -> no robots.txt, everything allowed
      - 5xx / error -> unsure, so be conservative and treat as off-limits
    """
    parser = RobotFileParser()
    _limiter.wait(host)
    try:
        resp = _session.get(f"{scheme}://{host}/robots.txt", timeout=20)
    except requests.RequestException:
        parser.disallow_all = True
        return parser

    if resp.status_code == 200:
        parser.parse(resp.text.splitlines())
    elif resp.status_code in (401, 403) or resp.status_code >= 500:
        parser.disallow_all = True
    else:
        parser.allow_all = True
    return parser


def _robots_for(url: str) -> RobotFileParser:
    parts = urlsplit(url)
    if parts.netloc not in _robots:
        _robots[parts.netloc] = _load_robots(parts.scheme, parts.netloc)
    return _robots[parts.netloc]


# ---------- public API ----------

def fetch(url: str) -> bytes:
    """Return the body of `url`, from cache if possible, else politely from the web."""
    cached = _read_cache(url)
    if cached is not None:
        return cached

    robots = _robots_for(url)
    if not robots.can_fetch(USER_AGENT, url):
        raise DisallowedByRobots(url)

    # Honour the site's Crawl-delay if it asks for more than our default.
    crawl_delay = robots.crawl_delay(USER_AGENT) or 0
    _limiter.wait(urlsplit(url).netloc, max(config.SCRAPE_DELAY_SECONDS, float(crawl_delay)))

    response = _session.get(url, timeout=30)
    response.raise_for_status()  # 4xx/5xx -> exception, and nothing is cached
    _write_cache(url, response)
    return response.content
