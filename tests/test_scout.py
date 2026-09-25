"""Tests for the scout's pure helpers (no network)."""
import json
from datetime import date

from src import scout


def test_quarter_labels_stop_at_current_quarter():
    labels = scout.quarter_labels(2023, date(2024, 5, 1))
    assert labels == ["2023Q1", "2023Q2", "2023Q3", "2023Q4", "2024Q1", "2024Q2"]


def test_parse_cdx_counts_each_timestamp_once():
    body = json.dumps([
        ["timestamp", "original"],
        ["20230115000000", "https://www.shop.example/coffee"],
        ["20230115000000", "http://shop.example/coffee"],  # same capture, other variant
        ["20240801120000", "https://shop.example/coffee"],
    ]).encode()
    assert list(scout.parse_cdx(body)) == ["20230115000000", "20240801120000"]


def test_parse_cdx_handles_empty_results():
    assert scout.parse_cdx(b"[]") == {}
    assert scout.parse_cdx(b"") == {}


def test_summarise_counts_quarters_and_earliest():
    snaps = {"20230301000000": "a", "20230302000000": "a", "20240801000000": "a"}
    quarters = ["2023Q1", "2023Q2", "2023Q3", "2023Q4", "2024Q1", "2024Q2", "2024Q3"]
    out = scout.summarise(snaps, quarters, "shop")
    assert out["shop_2023Q1"] == 2
    assert out["shop_2024Q3"] == 1
    assert out["shop_2023Q2"] == 0
    assert out["shop_quarters_covered"] == 2
    assert out["shop_earliest"] == "2023-03-01"


def test_products_json_validation():
    good = {"products": [{"title": "Beans", "variants": [{"price": "650.00"}]}]}
    assert scout.is_valid_products_json(json.dumps(good).encode())
    assert not scout.is_valid_products_json(b"<html>Not found</html>")
    assert not scout.is_valid_products_json(b"{}")
    assert not scout.is_valid_products_json(b'{"products": []}')
    assert not scout.is_valid_products_json(b"[1, 2]")
