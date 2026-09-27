"""Card-text extraction for the Phase 3 inputs table."""
from src.product_inputs import card_snippets, clean_text, tidy_card


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
