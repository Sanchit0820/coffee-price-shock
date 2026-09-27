"""Phase 3 inputs: one row per product with all the text the LLM (and the hand
labeller) may use. No network and no LLM calls: everything comes from Phase 2
outputs and the raw-page cache.

    python -m src.product_inputs  ->  data/clean/product_inputs.csv

A "product" is (roaster, product_id). Text fields:
  product_title   latest title seen; other_titles lists earlier variants of it
  product_type    as set by the shop (often blank)
  variant_titles  distinct variant names, e.g. "Whole Beans / 250g | Aeropress / 250g"
  card_text       visible listing-card text after the title (tasting notes etc.)
  description     live products.json body text (only products still on sale)
Long fields are capped so a batch of prompts stays small.
"""
import json
import re
from urllib.parse import urlsplit

import pandas as pd
from bs4 import BeautifulSoup

from src import collect, config, http_client, wayback

OUT = config.CLEAN_DIR / "product_inputs.csv"
CAP = {"variant_titles": 600, "card_text": 300, "description": 1500}


def clean_text(html_or_text: str) -> str:
    """Strip tags and collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", html_or_text or "")
    return re.sub(r"\s+", " ", text).strip()


def cap(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


# ---------- descriptions (live products.json) ----------

def live_descriptions() -> dict[tuple[str, str], str]:
    out = {}
    for r in collect.load_roasters():
        p = urlsplit(r["live_url"])
        for page in range(1, collect.LIVE_MAX_PAGES + 1):
            url = f"{p.scheme}://{p.netloc}{p.path}/products.json?limit=250&page={page}"
            body, _ = http_client._cache_paths(url)
            if not body.exists():
                break
            items = json.loads(body.read_bytes()).get("products", [])
            if not items:
                break
            for it in items:
                out[(r["roaster"], str(it["id"]))] = clean_text(it.get("body_html"))
    return out


# ---------- listing card text (cached archive pages) ----------

def visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" "))


def cached_page(served_ts: str, requested_ts: str, url: str) -> str | None:
    """The cached listing HTML for a row, trying the served then requested timestamp.
    Never fetches: returns None if the page isn't in the cache."""
    for ts in (served_ts, requested_ts):
        snap = wayback.snapshot_url(ts, url)
        if http_client.cached_meta(snap):
            body, _ = http_client._cache_paths(snap)
            return body.read_bytes().decode("utf-8", errors="replace")
    return None


# Shop-theme button and price labels that carry no product information.
_UI_NOISE = re.compile(
    r"regular price|sale price|unit price|price|quick ?view|quick shop|buy now|add to cart|"
    r"sold out|icon-x|close \(esc\)|hot new|new|sale|from|per|you will save|/|\+|\"",
    re.IGNORECASE)


def tidy_card(snippet: str, title: str) -> str:
    """Drop a repeated title and theme labels; keep notes, sizes and prices."""
    s = snippet
    if s.lower().startswith(title.lower()):
        s = s[len(title):]
    # The last card on a page runs into the pagination bar and footer: cut there.
    s = re.split(r"\b1 2 (?:icon-chevron )?next\b", s, flags=re.IGNORECASE)[0]
    s = _UI_NOISE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip(" -|,")


def card_snippets(text: str, titles: dict[str, str]) -> dict[str, str]:
    """{product_id: text between its title and the next product title on the page}.

    Cards list products one after another, so the text after a title up to the
    next title is that product's card (notes, "250gm", price...).
    """
    lower = text.lower()
    hits = sorted((lower.find(t.lower()), pid, t) for pid, t in titles.items()
                  if t and lower.find(t.lower()) >= 0)
    out = {}
    for i, (pos, pid, title) in enumerate(hits):
        end = hits[i + 1][0] if i + 1 < len(hits) else pos + len(title) + CAP["card_text"]
        snippet = tidy_card(text[pos + len(title): end].strip(), title)
        if snippet:
            out[pid] = snippet
    return out


def all_card_text(v: pd.DataFrame) -> dict[tuple[str, str], str]:
    """Longest card snippet seen for each product across its archived pages."""
    out: dict[tuple[str, str], str] = {}
    pages = v[v.source_type == "archive"].groupby(["roaster", "served_ts", "requested_ts", "source_url"])
    for (roaster, served, requested, url), g in pages:
        html = cached_page(served, requested, url)
        if html is None:
            continue
        titles = dict(zip(g.product_id, g.product_title))
        for pid, snippet in card_snippets(visible_text(html), titles).items():
            if len(snippet) > len(out.get((roaster, pid), "")):
                out[(roaster, pid)] = snippet
    return out


# ---------- the table ----------

def build() -> pd.DataFrame:
    # All rows, including served_outside_quarter ones: that flag matters for
    # quarter-level aggregation, not for knowing which products exist (page-2
    # captures up to 30 days into the next quarter carry it).
    v = pd.read_csv(collect.VARIANTS_OUT, dtype=str)
    desc, cards = live_descriptions(), all_card_text(v)
    rows = []
    for (roaster, pid), g in v.sort_values("quarter").groupby(["roaster", "product_id"]):
        titles = list(dict.fromkeys(g.product_title.dropna()))
        variants = list(dict.fromkeys(t for t in g.variant_title.dropna() if t))
        d = desc.get((roaster, pid), "")
        c = cards.get((roaster, pid), "")
        rows.append({
            "roaster": roaster, "tier": g.tier.iloc[0], "product_id": pid,
            "product_title": titles[-1] if titles else "",
            "other_titles": " | ".join(titles[:-1]),
            "product_type": g.product_type.dropna().iloc[-1] if g.product_type.notna().any() else "",
            "variant_titles": cap(" | ".join(variants), CAP["variant_titles"]),
            "card_text": cap(c, CAP["card_text"]),
            "description": cap(d, CAP["description"]),
            "has_description": len(d) > 20, "has_card_text": len(c) > 0,
            "is_coffee_guess_p2": g.is_coffee_guess.mode().iloc[0] if g.is_coffee_guess.notna().any() else "",
            "is_bundle_p2": (g.is_bundle == "True").any(),
            "first_quarter": g.quarter.min(), "last_quarter": g.quarter.max(),
            "n_quarters": g.quarter.nunique(),
        })
    return pd.DataFrame(rows)


def main() -> None:
    df = build()
    df.to_csv(OUT, index=False)
    print(f"Wrote {len(df)} products to {OUT}")
    print(f"  with description: {df.has_description.sum()}, title only: {(~df.has_description).sum()}")
    print(f"  with card text:   {df.has_card_text.sum()}")
    print(f"  with either:      {(df.has_description | df.has_card_text).sum()}")


if __name__ == "__main__":
    main()
