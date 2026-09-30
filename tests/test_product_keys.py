"""Splitting a product key where a page was reused for another coffee."""
from src.product_keys import segment_titles


def test_page_reuse_starts_a_new_segment():
    titles = ["VIETNAMESE ROBUSTA COFFEE", "VIETNAMESE ROBUSTA COFFEE", "COLOMBIAN ARABICA COFFEE"]
    assert segment_titles(titles) == [1, 1, 2]


def test_rename_stays_one_segment():
    titles = ["March Mellow ( Cold Brew Blend )", "Cold Brew Blend - Regular (March Mellow)"]
    assert segment_titles(titles) == [1, 1]


def test_process_or_lot_change_splits_even_with_high_overlap():
    from src.product_inputs import is_different_coffee, process_or_lot_changed
    # The case the word-overlap check missed (57% overlap):
    assert is_different_coffee("Nagaland Zunheboto GRADED Naturals (Light-Med Profile)",
                               "Nagaland Zunheboto Graded Washed (Med Profile)")
    assert process_or_lot_changed("Odisha Red Honey (Light-Med Roast)", "Odisha Floral Honey (Light Roast)")
    assert process_or_lot_changed("Ampthill Downs: Lot #08", "Ampthill Downs: Lot #63")
    # Not a change: same process, roast descriptor changed; or process named in one title only.
    assert not is_different_coffee("Nagaland Zunheboto Naturals (Light-Med Profile)",
                                   "Nagaland Zunheboto Naturals (Light Profile)")
    assert not process_or_lot_changed("Kohima Naturals", "Kohima Naturals Lot")
    assert not process_or_lot_changed("Baarbara Estate", "Baarbara Estate Washed")
    assert segment_titles(["Graded Naturals", "Graded Washed"]) == [1, 2]


def test_each_change_is_judged_against_the_latest_title():
    # A -> B (reuse) -> B' (rename of B) -> C (reuse again)
    titles = ["Kohima Naturals", "Ultra Light Nagaland", "Ultra Light Nagaland Lot", "Fruit Naturals"]
    assert segment_titles(titles) == [1, 2, 2, 3]
