"""Splitting a product key where a page was reused for another coffee."""
from src.product_keys import segment_titles


def test_page_reuse_starts_a_new_segment():
    titles = ["VIETNAMESE ROBUSTA COFFEE", "VIETNAMESE ROBUSTA COFFEE", "COLOMBIAN ARABICA COFFEE"]
    assert segment_titles(titles) == [1, 1, 2]


def test_rename_stays_one_segment():
    titles = ["March Mellow ( Cold Brew Blend )", "Cold Brew Blend - Regular (March Mellow)"]
    assert segment_titles(titles) == [1, 1]


def test_each_change_is_judged_against_the_latest_title():
    # A -> B (reuse) -> B' (rename of B) -> C (reuse again)
    titles = ["Kohima Naturals", "Ultra Light Nagaland", "Ultra Light Nagaland Lot", "Fruit Naturals"]
    assert segment_titles(titles) == [1, 2, 2, 3]
