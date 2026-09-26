"""Read Shopify's embedded analytics object (`var meta = {...}`) from a collection page.

It lists every product rendered on the page with its variants:
  {"products": [{"id": 123, "type": "Coffee", "variants": [
      {"id": 456, "price": 43000, "name": "Monsoon Malabar - Whole Beans / 250g",
       "public_title": "Whole Beans / 250g", "sku": "..."}]}]}
Prices are integers in paise (1/100 rupee). There is no product title field;
it is recovered from the variant name.
"""
import json

_MARKER = "var meta = "


def extract_meta_products(html: str) -> list[dict] | None:
    """The `products` list from `var meta = {...}`, or None if the page has none.

    raw_decode parses exactly one JSON object starting at the brace and ignores
    whatever JavaScript follows it, which is safer than guessing where it ends.
    """
    start = html.find(_MARKER)
    if start == -1:
        return None
    try:
        meta, _ = json.JSONDecoder().raw_decode(html, start + len(_MARKER))
    except ValueError:
        return None
    products = meta.get("products") if isinstance(meta, dict) else None
    return products if isinstance(products, list) else None


def paise_to_rupees(paise) -> float | None:
    """43000 -> 430.0. Accepts ints or numeric strings; None if missing."""
    if paise in (None, ""):
        return None
    return int(paise) / 100


def product_title(variant_name: str, variant_title: str | None) -> str:
    """"Monsoon Malabar - Whole Beans / 250g" minus " - Whole Beans / 250g".

    Single-variant products have no variant title, and the name is the title.
    """
    suffix = f" - {variant_title}" if variant_title else ""
    if suffix and variant_name.endswith(suffix):
        return variant_name[: -len(suffix)].strip()
    return variant_name.strip()


def variant_rows(products: list[dict]) -> list[dict]:
    """One dict per variant with the fields we keep."""
    rows = []
    for p in products:
        for v in p.get("variants", []):
            variant_title = v.get("public_title") or ""
            rows.append({
                "product_id": p.get("id"),
                "product_type": p.get("type") or "",
                "product_title": product_title(v.get("name") or "", variant_title),
                "variant_id": v.get("id"),
                "variant_title": variant_title,
                "price_inr": paise_to_rupees(v.get("price")),
                "sku": v.get("sku") or "",
            })
    return rows
