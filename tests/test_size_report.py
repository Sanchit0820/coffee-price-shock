"""Pack-size change detection."""
import pandas as pd

from src.size_report import confidence, product_changes, usable, variant_changes


def frame(rows):
    cols = ["roaster", "quarter", "product_id", "product_title", "variant_id", "variant_title",
            "size_grams", "size_source", "is_coffee_guess", "served_outside_quarter"]
    return pd.DataFrame([dict(zip(cols, r)) for r in rows])


ROWS = [
    # Product 1: variant 11 shrinks 250 -> 200 g in 2024Q3 (shrinkflation shape).
    ("R", "2024Q1", "1", "Estate", "11", "250g", 250, "variant_title", "True", "False"),
    ("R", "2024Q2", "1", "Estate", "11", "250g", 250, "variant_title", "True", "False"),
    ("R", "2024Q3", "1", "Estate", "11", "200g", 200, "variant_title", "True", "False"),
    # Product 2: a 1 kg option is added in 2024Q2; the 250 g variant is unchanged.
    ("R", "2024Q1", "2", "Blend", "21", "250g", 250, "variant_title", "True", "False"),
    ("R", "2024Q2", "2", "Blend", "21", "250g", 250, "variant_title", "True", "False"),
    ("R", "2024Q2", "2", "Blend", "22", "1kg", 1000, "variant_title", "True", "False"),
    # Excluded: non-coffee, and a row served from outside its quarter.
    ("R", "2024Q1", "3", "Mug", "31", "", 300, "product_title", "False", "False"),
    ("R", "2024Q3", "2", "Blend", "21", "100g", 100, "variant_title", "True", "True"),
]


def test_usable_drops_non_coffee_and_outside_quarter_rows():
    assert len(usable(frame(ROWS))) == 6


def test_variant_change():
    ch = variant_changes(usable(frame(ROWS)))
    assert len(ch) == 1
    assert (ch[0]["variant_id"], ch[0]["from_quarter"], ch[0]["to_quarter"],
            ch[0]["sizes_before"], ch[0]["sizes_after"]) == ("11", "2024Q2", "2024Q3", 250, 200)


def test_confidence():
    assert confidence("variant_title", "variant_title") == "high"
    assert confidence("product_page_variant", "product_title") == "high"
    assert confidence("product_page_text", "live_shipping_grams") == "low"   # Blue Tokai bundle
    assert confidence("listing_text", "variant_title") == "low"


def test_product_menu_changes():
    ch = {(c["product_id"], c["to_quarter"]): (c["sizes_before"], c["sizes_after"])
          for c in product_changes(usable(frame(ROWS)))}
    assert ch == {("1", "2024Q3"): ("250", "200"), ("2", "2024Q2"): ("250", "250 1000")}
