"""Snapshot selection and pagination helpers."""
from datetime import date

from src import wayback
from src.quarters import mid_quarter


def test_mid_quarter():
    assert mid_quarter("2024Q1") == date(2024, 2, 15)
    assert mid_quarter("2024Q4") == date(2024, 11, 15)


def test_choose_mid_quarter_picks_closest_to_middle():
    snaps = {"20240105000000": "a", "20240220000000": "b", "20240330000000": "c"}
    assert wayback.choose_mid_quarter(snaps, "2024Q1") == "20240220000000"


def test_choose_mid_quarter_never_uses_a_neighbouring_quarter():
    # Dec 31 is closer to Feb 15 than nothing, but it's in 2023Q4.
    snaps = {"20231231000000": "a", "20240401000000": "b"}
    assert wayback.choose_mid_quarter(snaps, "2024Q1") is None


def test_nearest_respects_max_days():
    ts = ["20240101000000", "20240301000000"]
    assert wayback.nearest(ts, date(2024, 1, 20), max_days=30) == "20240101000000"
    assert wayback.nearest(ts, date(2024, 5, 1), max_days=30) is None
    assert wayback.nearest([], date(2024, 1, 1)) is None


def test_page_number_only_matches_same_listing():
    path = "/collections/all"
    assert wayback.page_number("https://x.com/collections/all?page=2", path) == 2
    assert wayback.page_number("https://x.com/collections/all/?page=3", path) == 3
    assert wayback.page_number("https://x.com/collections/all?page=1", path) is None
    assert wayback.page_number("https://x.com/collections/all-coffee?page=2", path) is None
    assert wayback.page_number("https://x.com/collections/all?page=2&sort_by=price", path) is None
    assert wayback.page_number("https://x.com/collections/all?sort_by=price", path) is None


def test_linked_pages_reads_relative_links():
    html = ('<a href="/collections/all?page=2">2</a><a href="/collections/all?page=3">3</a>'
            '<a href="/collections/other?page=9">x</a><a href="/collections/all?page=2&amp;sort_by=x">s</a>')
    assert wayback.linked_pages(html, "/collections/all") == {2, 3}
