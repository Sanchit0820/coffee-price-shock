"""Read pack sizes (and compare-at prices) from an archived Shopify product page.

Product pages carry a "rich" variant list in the theme's product JSON:
  "variants":[{"id": 456, "title": "250g / Medium", "option1": "250g",
               "price": 42000, "compare_at_price": null, "weight": 250, ...}]
Prices and compare-at prices are in paise. `weight` is Shopify's SHIPPING
weight in grams: often the net weight, but sometimes 0 (Subko) or including
packaging (Grey Soul's oat milk: 750), so it is the last resort.
"""
import json
import re

from bs4 import BeautifulSoup

from src.shopify_meta import paise_to_rupees
from src.sizes import Size, parse_size_grams

_VARIANTS_KEY = '"variants":'


def rich_variants(html: str) -> dict[int, dict]:
    """{variant_id: variant dict} from every "variants":[...] array that has
    per-variant detail (options / weight). The analytics copy on the same page
    only has id/name/price and is skipped."""
    decoder = json.JSONDecoder()
    found: dict[int, dict] = {}
    i = html.find(_VARIANTS_KEY)
    while i != -1:
        try:
            arr, _ = decoder.raw_decode(html, i + len(_VARIANTS_KEY))
        except ValueError:
            arr = None
        for v in arr if isinstance(arr, list) else []:
            if isinstance(v, dict) and "id" in v and ("weight" in v or "options" in v):
                found.setdefault(v["id"], v)
        i = html.find(_VARIANTS_KEY, i + 1)
    return found


def analytics_variants(html: str) -> dict[int, dict]:
    """{variant_id: variant} from the analytics object `var meta = {"product": {...}}`.

    Only id / name / public_title / price, no weight or compare-at. Used when a
    theme has no rich variant JSON (Subko), where the title may still carry the
    size ("Whole Bean (250g)").
    """
    start = html.find("var meta = ")
    if start == -1:
        return {}
    try:
        meta, _ = json.JSONDecoder().raw_decode(html, start + len("var meta = "))
    except ValueError:
        return {}
    product = meta.get("product") if isinstance(meta, dict) else None
    variants = product.get("variants", []) if isinstance(product, dict) else []
    return {v["id"]: {"title": v.get("public_title") or "", "name": v.get("name") or ""}
            for v in variants if isinstance(v, dict) and "id" in v}


def product_text(html: str) -> str:
    """Product title + description only (not the menu, related products or footer).

    Taken from the page's own metadata: og:title / og:description and the
    JSON-LD Product block.
    """
    soup = BeautifulSoup(html, "lxml")
    parts = [m.get("content", "") for m in soup.select(
        'meta[property="og:title"], meta[property="og:description"]')]
    for s in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(s.string or "")
        except ValueError:
            continue
        for d in data if isinstance(data, list) else [data]:
            if isinstance(d, dict) and d.get("@type") == "Product":
                parts += [str(d.get("name", "")), str(d.get("description", ""))]
    return " ".join(parts)


def single_size(text: str) -> Size | None:
    """The size if `text` mentions exactly one distinct pack size, else None."""
    sizes = {s for chunk in re.findall(r"\d+(?:\.\d+)?\s*(?:x\s*\d+\s*)?[a-zA-Z]+", text)
             if (s := parse_size_grams(chunk))}
    return sizes.pop() if len(sizes) == 1 else None


def variant_sizes(html: str) -> dict[int, dict]:
    """{variant_id: {size_grams, multipack, size_source, compare_at_price_inr}}."""
    text_size = single_size(product_text(html))
    # Rich variant JSON when the theme has it; otherwise the analytics copy.
    variants = rich_variants(html) or analytics_variants(html)
    out = {}
    for vid, v in variants.items():
        options = " / ".join(str(v.get(k) or "") for k in ("title", "option1", "option2", "option3"))
        size, source = parse_size_grams(options), "product_page_variant"
        if size is None and text_size:
            size, source = text_size, "product_page_text"
        if size is None and (v.get("weight") or 0) > 0:
            size, source = Size(float(v["weight"]), False), "product_page_shipping_weight"
        out[vid] = {
            "size_grams": size.grams if size else None,
            "multipack": size.multipack if size else None,
            "size_source": source if size else "",
            "compare_at_price_inr": paise_to_rupees(v.get("compare_at_price")),
        }
    return out
