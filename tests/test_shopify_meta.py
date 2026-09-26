"""Embedded Shopify product data: extraction, paise conversion, product titles."""
import json

from src.shopify_meta import extract_meta_products, paise_to_rupees, product_title, variant_rows

META = {"products": [{"id": 1, "type": "Coffee", "variants": [
    {"id": 11, "price": 43000, "name": "Monsoon Malabar - Whole Beans / 250g",
     "public_title": "Whole Beans / 250g", "sku": "MM250"},
    {"id": 12, "price": "155000", "name": "Monsoon Malabar - Whole Beans / 1kg",
     "public_title": "Whole Beans / 1kg"},
]}, {"id": 2, "type": "", "variants": [
    {"id": 21, "price": 99900, "name": "Oat Mlk", "public_title": None},
]}], "page": {"pageType": "collection"}}


def page(meta_obj):
    # Mimics the real script: the object is followed by more JavaScript.
    return f"<script>var meta = {json.dumps(meta_obj)};\nfor (var attr in meta) {{}}</script>"


def test_paise_to_rupees():
    assert paise_to_rupees(43000) == 430.0
    assert paise_to_rupees("155000") == 1550.0
    assert paise_to_rupees(99) == 0.99
    assert paise_to_rupees(None) is None
    assert paise_to_rupees("") is None


def test_extract_meta_products():
    assert len(extract_meta_products(page(META))) == 2
    assert extract_meta_products("<html>no meta here</html>") is None
    assert extract_meta_products("var meta = {broken") is None


def test_product_title_strips_variant_suffix():
    assert product_title("Monsoon Malabar - Whole Beans / 250g", "Whole Beans / 250g") == "Monsoon Malabar"
    assert product_title("Oat Mlk", None) == "Oat Mlk"
    # A dash inside the product name itself is kept.
    assert product_title("Dima Hasao, Assam -Naturals - 250g", "250g") == "Dima Hasao, Assam -Naturals"


def test_variant_rows():
    rows = variant_rows(extract_meta_products(page(META)))
    assert [r["variant_id"] for r in rows] == [11, 12, 21]
    assert rows[0]["price_inr"] == 430.0
    assert rows[0]["product_title"] == "Monsoon Malabar"
    assert rows[1]["price_inr"] == 1550.0
    assert rows[2]["variant_title"] == ""
