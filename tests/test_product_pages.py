"""Product-page size parsing and archived-handle matching (no network)."""
import json

from src.fallback import match_handle
from src.product_pages import rich_variants, single_size, variant_sizes


def page(variants, og_title="", og_desc=""):
    analytics = [{"id": v["id"], "price": v["price"], "name": "x"} for v in variants]
    return (f'<meta property="og:title" content="{og_title}">'
            f'<meta property="og:description" content="{og_desc}">'
            f'<script>var meta = {{"product":{{"variants":{json.dumps(analytics)}}}}};</script>'
            f'<script>var product = {{"variants":{json.dumps(variants)}}};</script>')


def v(vid, title, weight=0, compare=None):
    return {"id": vid, "title": title, "option1": title, "option2": None, "option3": None,
            "options": [title], "price": 42000, "compare_at_price": compare, "weight": weight}


def test_rich_variants_skip_the_analytics_copy():
    html = page([v(1, "250g"), v(2, "1kg")])
    assert set(rich_variants(html)) == {1, 2}
    assert "weight" in rich_variants(html)[1]


def test_size_from_variant_title_first():
    out = variant_sizes(page([v(1, "250g / Medium", weight=300)]))
    assert out[1]["size_grams"] == 250 and out[1]["size_source"] == "product_page_variant"


def test_size_from_product_text_when_variant_has_none():
    out = variant_sizes(page([v(1, "Whole Bean")], og_desc="Our lot 24, sold in 250g bags."))
    assert out[1]["size_grams"] == 250 and out[1]["size_source"] == "product_page_text"


def test_shipping_weight_is_last_resort_and_zero_is_ignored():
    assert variant_sizes(page([v(1, "Whole Bean", weight=500)]))[1]["size_source"] == \
        "product_page_shipping_weight"
    assert variant_sizes(page([v(1, "Whole Bean", weight=0)]))[1]["size_grams"] is None


def test_ambiguous_product_text_is_not_used():
    out = variant_sizes(page([v(1, "Whole Bean")], og_desc="Available in 250g and 1kg."))
    assert out[1]["size_grams"] is None


def test_falls_back_to_analytics_variants_when_no_rich_json():
    # Subko-style page: only the analytics copy exists.
    html = ('<script>var meta = {"product":{"id":1,"variants":[{"id":7,"price":59500,'
            '"name":"Woodway - Whole Bean (250g)","public_title":"Whole Bean (250g)"}]}};</script>')
    out = variant_sizes(html)
    assert out[7]["size_grams"] == 250 and out[7]["size_source"] == "product_page_variant"
    assert out[7]["compare_at_price_inr"] is None


def test_compare_at_price_in_rupees():
    assert variant_sizes(page([v(1, "250g", compare=50000)]))[1]["compare_at_price_inr"] == 500.0


def test_single_size():
    assert single_size("250 gms whole beans").grams == 250
    assert single_size("2 x 500 gms").grams == 1000
    assert single_size("250g or 500g") is None
    assert single_size("no size") is None


def test_targets_include_rows_filled_by_an_earlier_run():
    import pandas as pd

    from src.fallback import targets
    rows = pd.DataFrame([
        # listing gave no size -> target
        dict(source_type="archive", size_grams=None, size_source="", is_coffee_guess="True",
             served_outside_quarter="False", roaster="R", product_id="1", quarter="2024Q1",
             source_url="https://x.com/c", product_title="A", served_ts="20240215000000"),
        # filled by a previous stage 2 run -> still a target
        dict(source_type="archive", size_grams=250, size_source="product_page_text",
             is_coffee_guess="True", served_outside_quarter="False", roaster="R",
             product_id="2", quarter="2024Q1", source_url="https://x.com/c",
             product_title="B", served_ts="20240215000000"),
        # sized by the listing -> not a target
        dict(source_type="archive", size_grams=250, size_source="variant_title",
             is_coffee_guess="True", served_outside_quarter="False", roaster="R",
             product_id="3", quarter="2024Q1", source_url="https://x.com/c",
             product_title="C", served_ts="20240215000000"),
    ])
    assert sorted(targets(rows).product_id) == ["1", "2"]


def test_match_handle():
    handles = {"ampthill-downs-lot-24", "kerehaklu-estate-lot-uda-1", "black-honey-coffee",
               "lot-a-1", "lot-a-2"}
    assert match_handle("ampthill-downs-lot-24", handles) == ("ampthill-downs-lot-24", "cdx_exact")
    assert match_handle("kerehaklu-estate-lot-uda", handles) == ("kerehaklu-estate-lot-uda-1", "cdx_prefix")
    assert match_handle("black-honey", handles) == ("black-honey-coffee", "cdx_prefix")
    assert match_handle("lot-a", handles) == ("", "unmapped")        # two candidates: don't guess
    assert match_handle("unknown", handles) == ("", "unmapped")
