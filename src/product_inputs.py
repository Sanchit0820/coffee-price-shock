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


# ---------- title changes within one product ID ----------

TITLE_CHANGE_BELOW = 0.5
TITLE_CHANGES_OUT = config.DATA_DIR / "review" / "title_changes.csv"
# Words that say nothing about WHICH coffee it is; ignored when comparing titles.
_GENERIC = {"coffee", "coffees", "bean", "beans", "roast", "roasted", "profile", "blend",
            "the", "and", "of", "with", "regular", "a", "an", "by"}


def title_words(title: str) -> set[str]:
    return {w for w in re.sub(r"[^a-z0-9]+", " ", str(title).lower()).split()
            if w not in _GENERIC}


# Process words (normalised): a change between two titles that both name a
# process means a different coffee, even when most other words are the same
# ("Graded Naturals" -> "Graded Washed"). Decided 2026-09-30.
_PROCESS = [
    (r"\b(red|yellow|black|white|golden)\s+honey\b", lambda m: f"{m.group(1).lower()} honey"),
    (r"\bsemi[- ]washed\b", lambda m: "semi-washed"),
    (r"\bnaturals?\b", lambda m: "natural"),
    (r"\bwashed\b", lambda m: "washed"),
    (r"\bhoney\b", lambda m: "honey"),
    (r"\banaerobic\b", lambda m: "anaerobic"),
    (r"\baerobic\b", lambda m: "aerobic"),
    (r"\bcarbonic\b", lambda m: "carbonic"),
    (r"\bmacerat\w*", lambda m: "maceration"),
    (r"\bmonsoon\w*", lambda m: "monsooned"),
    (r"\bferment\w*", lambda m: "fermentation"),
    (r"\byeast\b", lambda m: "yeast"),
    (r"\bkoji\b", lambda m: "koji"),
    (r"\bcultur\w*", lambda m: "culture"),
    (r"\bpulped\b", lambda m: "pulped"),
    (r"\bwet[- ]hulled\b", lambda m: "wet-hulled"),
]
_LOT = re.compile(r"\blot\s*#?\s*([a-z]*\d[\w-]*)|#\s*([a-z]*\d[\w-]*)", re.IGNORECASE)


def process_words(title: str) -> set[str]:
    """Normalised process words in a title. A coloured honey ("red honey") is
    taken as one term, so "Red Honey" vs "Floral Honey" counts as a change."""
    text, found = str(title), set()
    for pattern, name in _PROCESS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            found.add(name(m))
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)   # don't count "honey" twice
    return found


def lot_ids(title: str) -> set[str]:
    return {(a or b).lower() for a, b in _LOT.findall(str(title))}


def process_or_lot_changed(a: str, b: str) -> bool:
    """True if BOTH titles name a process (or a lot) and it differs. One title
    naming none isn't a change: that is usually just a shorter title."""
    pa, pb, la, lb = process_words(a), process_words(b), lot_ids(a), lot_ids(b)
    return bool((pa and pb and pa != pb) or (la and lb and la != lb))


def is_different_coffee(a: str, b: str) -> bool:
    """The test used everywhere a product ID's title changes: low overlap of
    distinctive words, or a changed process or lot."""
    return title_similarity([a, b]) < TITLE_CHANGE_BELOW or process_or_lot_changed(a, b)


def title_similarity(titles: list[str]) -> float | None:
    """Lowest word overlap (Jaccard) between consecutive distinct titles of one product ID.

    Distinctive words only, so a rename or reordering scores high
    ("March Mellow ( Cold Brew Blend )" -> "Cold Brew Blend - Regular (March Mellow)")
    and a page reused for another coffee scores low ("VIETNAMESE ROBUSTA
    COFFEE" -> "COLOMBIAN ARABICA COFFEE" = 0). Character similarity misses
    that case: shared letters and "coffee" push it over 0.5. None if the title
    never changed.
    """
    if len(titles) < 2:
        return None
    scores = []
    for a, b in zip(titles, titles[1:]):
        wa, wb = title_words(a), title_words(b)
        scores.append(len(wa & wb) / len(wa | wb) if wa | wb else 1.0)
    return round(min(scores), 3)


# ---------- the table ----------

def build() -> pd.DataFrame:
    # All rows, including served_outside_quarter ones: that flag matters for
    # quarter-level aggregation, not for knowing which products exist (page-2
    # captures up to 30 days into the next quarter carry it).
    v = pd.read_csv(collect.VARIANTS_OUT, dtype=str)
    desc, cards = live_descriptions(), all_card_text(v)
    rows = []
    # kind="stable" keeps the file's own row order within a quarter. The default
    # sort isn't stable, so variant_titles came out in a different order on each
    # rebuild; that changed the LLM prompts and defeated the response cache.
    for (roaster, pid), g in v.sort_values("quarter", kind="stable").groupby(["roaster", "product_id"]):
        titles = list(dict.fromkeys(g.product_title.dropna()))
        variants = list(dict.fromkeys(t for t in g.variant_title.dropna() if t))
        d = desc.get((roaster, pid), "")
        c = cards.get((roaster, pid), "")
        sim = title_similarity(titles)
        rows.append({
            "title_similarity": sim,
            "title_changed": any(is_different_coffee(a, b) for a, b in zip(titles, titles[1:])),
            "process_or_lot_changed": any(process_or_lot_changed(a, b)
                                          for a, b in zip(titles, titles[1:])),
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
    changed = df[df.title_changed]
    TITLE_CHANGES_OUT.parent.mkdir(parents=True, exist_ok=True)
    changed[["roaster", "product_id", "other_titles", "product_title", "title_similarity",
             "process_or_lot_changed", "first_quarter", "last_quarter"]].to_csv(TITLE_CHANGES_OUT, index=False)
    print(f"  title changed within one ID (possible page reuse): {len(changed)} "
          f"-> {TITLE_CHANGES_OUT}")
    print(f"Wrote {len(df)} products to {OUT}")
    print(f"  with description: {df.has_description.sum()}, title only: {(~df.has_description).sum()}")
    print(f"  with card text:   {df.has_card_text.sum()}")
    print(f"  with either:      {(df.has_description | df.has_card_text).sum()}")


if __name__ == "__main__":
    main()
