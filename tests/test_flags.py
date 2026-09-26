"""Completeness, switch windows, sale detection, live comparison, coffee guess."""
from datetime import date

from src.coffee_filter import is_coffee_guess
from src.flags import (compare_live, completeness, id_carryover, in_switch_window,
                       mark_sales, sale_status, uniform_listing_size)
from src.sizes import Size


# ---------- completeness ----------

def test_completeness_flags():
    assert completeness(set(), set()) == ("single_page", [])
    assert completeness({2, 3}, {2, 3}) == ("complete", [])
    assert completeness({2, 3}, {2}) == ("partial", [3])
    assert completeness({2, 3, 4}, set()) == ("partial", [2, 3, 4])


# ---------- switch windows ----------

def test_switch_window_date_range():
    w = "2024-04-18 to 2024-05-23 (collection renamed)"
    assert in_switch_window(w, date(2024, 5, 1))
    assert not in_switch_window(w, date(2024, 6, 1))


def test_switch_window_single_date_means_that_quarter():
    w = "2026-03-07 (new /pages/shop-dope)"
    assert in_switch_window(w, date(2026, 2, 1))
    assert not in_switch_window(w, date(2026, 4, 1))


def test_switch_window_after_quarter():
    w = "after 2024-Q2 (roasted-beans archive ends)"
    assert in_switch_window(w, date(2024, 8, 1))
    assert not in_switch_window(w, date(2024, 5, 1))
    assert not in_switch_window("", date(2024, 8, 1))


# ---------- sales ----------

def test_sale_status():
    assert sale_status(500, 400, 500) == "candidate"      # -20%, then back
    assert sale_status(500, 400, 400) == "False"          # dropped and stayed down
    assert sale_status(500, 460, 500) == "False"          # only -8%
    assert sale_status(500, 400, 480) == "candidate"      # back to 96%
    assert sale_status(None, 400, 500) == "not_checkable"
    assert sale_status(500, 400, None) == "not_checkable"


def row(q, vid, price, roaster="R"):
    return {"roaster": roaster, "quarter": q, "variant_id": vid, "price_inr": price,
            "source_type": "archive"}


def test_mark_sales_first_and_last_quarter_not_checkable():
    rows = [row("2024Q1", 1, 500), row("2024Q2", 1, 400), row("2024Q3", 1, 500)]
    mark_sales(rows)
    assert [r["sale_suspected"] for r in rows] == ["not_checkable", "candidate", "not_checkable"]


def test_mark_sales_uses_observed_neighbours_across_gaps():
    # No snapshot in 2024Q2: 2024Q3's neighbours are 2024Q1 and 2024Q4.
    rows = [row("2024Q1", 1, 500), row("2024Q3", 1, 400), row("2024Q4", 1, 500)]
    mark_sales(rows)
    assert rows[1]["sale_suspected"] == "candidate"


def test_mark_sales_ignores_live_rows():
    rows = [row("2024Q1", 1, 500), {**row("2026Q3", 1, 100), "source_type": "live",
                                    "sale_suspected": "False"}]
    mark_sales(rows)
    assert rows[1]["sale_suspected"] == "False"


# ---------- ID continuity ----------

def test_id_carryover():
    rows = [row("2024Q1", 1, 1), row("2024Q1", 2, 1), row("2024Q2", 1, 1), row("2024Q2", 3, 1),
            row("2024Q4", 7, 1), row("2024Q4", 8, 1)]   # 2024Q4: catalogue rebuilt
    assert id_carryover(rows) == {"2024Q1": None, "2024Q2": 0.5, "2024Q4": 0.0}


# ---------- live vs archive ----------

def test_compare_live():
    archive = [{"variant_id": 1, "price_inr": 500}, {"variant_id": 2, "price_inr": 1000},
               {"variant_id": 3, "price_inr": 200}]
    live = [{"variant_id": 1, "price_inr": 550}, {"variant_id": 2, "price_inr": 1000},
            {"variant_id": 9, "price_inr": 50}]
    out = compare_live(archive, live)
    assert out["live_matched"] == 2
    assert out["live_median_pct_diff"] == 5.0
    assert out["live_share_higher"] == 0.5
    assert compare_live(archive, [])["live_matched"] == 0


# ---------- page-wide size ----------

def test_uniform_listing_size():
    one = "<div>Baarbara 250 gm Rs. 645</div><div>Buzz 250gm Rs. 520</div>"
    two = "<div>A 250 gm</div><div>B 1 kg</div>"
    assert uniform_listing_size(one) == Size(250, False)
    assert uniform_listing_size(two) is None
    assert uniform_listing_size("<script>var x='500g'</script><p>no sizes</p>") is None


# ---------- coffee guess ----------

def test_coffee_guess():
    assert is_coffee_guess("Monsoon Malabar AA", "Coffee", True) is True
    assert is_coffee_guess("Hario V60 Dripper", "Equipment", False) is False
    assert is_coffee_guess("Chicory Powder", "Coffee", True) is False       # strong beats type
    assert is_coffee_guess("Customised Sampler Pack", "Coffee", False) is False
    assert is_coffee_guess("4 X COFFEES", "", False) is False
    assert is_coffee_guess("Dark Chocolate Espresso", "Coffee", True) is True  # tasting note
    assert is_coffee_guess("Dark Chocolate Espresso", "", True) is None       # can't tell
    assert is_coffee_guess("Kilpauk Standard", "", True) is True              # grams, no keyword
    assert is_coffee_guess("Mystery Item", "", False) is None
