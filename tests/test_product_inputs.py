"""Card-text extraction for the Phase 3 inputs table."""
from src.product_inputs import card_snippets, clean_text, tidy_card, title_similarity


def test_build_is_deterministic(tmp_path, monkeypatch):
    """Same variants_long -> identical inputs table, byte for byte (the LLM cache depends on it)."""
    import pandas as pd

    from src import product_inputs as pi
    rows = []
    for q in ("2024Q1", "2024Q2"):
        for i, size in enumerate(["250g", "500g", "1kg", "100g", "2kg", "750g"]):
            rows.append({"roaster": "R", "product_id": "1", "product_title": "Estate", "quarter": q,
                         "variant_title": f"{size} / Grind {i}", "product_type": "Coffee",
                         "tier": "core", "is_coffee_guess": "True", "is_bundle": "False",
                         "source_type": "archive", "served_ts": "", "requested_ts": "", "source_url": ""})
    variants = tmp_path / "variants_long.csv"
    pd.DataFrame(rows).to_csv(variants, index=False)
    monkeypatch.setattr(pi.collect, "VARIANTS_OUT", variants)
    monkeypatch.setattr(pi, "live_descriptions", lambda: {})
    monkeypatch.setattr(pi, "all_card_text", lambda v: {})
    first, second = pi.build(), pi.build()
    assert first.to_csv(index=False) == second.to_csv(index=False)
    assert first.variant_titles.iloc[0].startswith("250g / Grind 0 | 500g / Grind 1")


def test_title_similarity_flags_page_reuse_not_renames():
    assert title_similarity(["VIETNAMESE ROBUSTA COFFEE", "COLOMBIAN ARABICA COFFEE"]) == 0.0
    assert title_similarity(["March Mellow ( Cold Brew Blend )",
                             "Cold Brew Blend - Regular (March Mellow)"]) >= 0.5
    assert title_similarity(["Arabica French Roast", "ARABICA FRENCH ROAST COFFEE"]) == 1.0
    assert title_similarity(["Only One Title"]) is None
    # A chain is judged by its weakest step.
    assert title_similarity(["Kohima Naturals", "Kohima Naturals", "Ultra Light Nagaland"]) == 0.0


def test_card_snippets_split_between_titles():
    text = ("Monsoon Malabar Dark Chocolate, Spice ₹ 520 "
            "Attikan Estate Plum, Jaggery ₹ 610 1 2 Next About Us Contact")
    out = card_snippets(text, {"1": "Monsoon Malabar", "2": "Attikan Estate", "3": "Not On Page"})
    assert out["1"] == "Dark Chocolate, Spice ₹ 520"
    assert out["2"] == "Plum, Jaggery ₹ 610"     # footer after the pagination bar is cut
    assert "3" not in out


def test_tidy_card_removes_theme_labels_and_repeated_title():
    s = tidy_card("Dhak Blend Regular price From Rs. 399.00 Quick View Cocoa", "Dhak Blend")
    assert s == "Rs. 399.00 Cocoa"


def test_clean_text_strips_html():
    assert clean_text("<p>Washed <b>Arabica</b></p>\n from   Coorg") == "Washed Arabica from Coorg"
