"""Phase 4 maths on small hand-built cases (no files needed)."""
import numpy as np
import pandas as pd
import pytest

from src.analysis.data import geo_mean_ratio, lagged_quarter
from src.analysis.index import chain, normalise
from src.analysis.pass_through import HEADLINE_LAG, cost_at, pass_through


def items(rows):
    return pd.DataFrame(rows, columns=["quarter", "product_key", "size_grams", "ppg"])


def test_lagged_quarter_crosses_years():
    assert lagged_quarter("2025Q1", 1) == "2024Q4"
    assert lagged_quarter("2025Q1", 3) == "2024Q2"
    assert lagged_quarter("2024Q3", 0) == "2024Q3"


def test_geo_mean_ratio():
    assert geo_mean_ratio(np.array([110, 121]), np.array([100, 100])) == pytest.approx(np.sqrt(1.1 * 1.21))


def test_index_ignores_products_that_come_and_go():
    it = items([("2023Q1", "a", 250, 100), ("2023Q1", "b", 250, 200), ("2023Q1", "c", 250, 300),
                ("2024Q2", "a", 250, 110), ("2024Q2", "b", 250, 220), ("2024Q2", "c", 250, 330),
                ("2024Q2", "NEW", 250, 999)])            # a new expensive product
    c = normalise(chain(it))
    assert c.set_index("quarter")["index"]["2024Q2"] == pytest.approx(110.0)   # only matched items move it


def test_pack_size_change_is_not_a_match():
    it = items([("2023Q1", "a", 250, 100), ("2023Q1", "b", 250, 100), ("2023Q1", "c", 250, 100),
                ("2024Q2", "a", 200, 125), ("2024Q2", "b", 250, 100), ("2024Q2", "c", 250, 100),
                ("2024Q2", "d", 250, 100)])
    # a changed pack size -> not matched; b and c unchanged; only 2 matched < 3 -> chain breaks
    c = chain(it)
    assert c.segment.tolist() == [1, 2]


def test_break_starts_unanchored_segment():
    it = items([("2023Q1", k, 250, 100) for k in "abc"] + [("2024Q1", k, 250, 110) for k in "abc"]
               + [("2025Q1", k, 250, 50) for k in "xyz"])      # all new products: break
    c = normalise(chain(it)).set_index("quarter")
    assert c.loc["2023Q1", "index"] == pytest.approx(100 / 105 * 100)   # pre avg of 100 and 110 = 100
    assert c.loc["2024Q1", "index"] == pytest.approx(110 / 105 * 100)
    assert bool(c.loc["2023Q1", "main_segment"]) and not bool(c.loc["2025Q1", "anchored"])


def test_links_back_when_products_return():
    # 2025Q1 lists other IDs; the 2024 products return in 2026Q3 at +30%.
    it = items([("2023Q1", k, 250, 100) for k in "abc"] + [("2024Q1", k, 250, 100) for k in "abc"]
               + [("2025Q1", k, 250, 70) for k in "xyz"] + [("2026Q3", k, 250, 130) for k in "abc"])
    c = normalise(chain(it)).set_index("quarter")
    assert c.loc["2026Q3", "linked_from"] == "2024Q1"
    assert c.loc["2026Q3", "segment"] == c.loc["2024Q1", "segment"]
    assert c.loc["2026Q3", "index"] == pytest.approx(130.0)
    assert not bool(c.loc["2025Q1", "anchored"])          # the stray quarter stays apart


def test_cost_at_headline_lag_is_mean_of_lags():
    s = pd.Series({"2024Q1": 40.0, "2024Q2": 50.0, "2024Q3": 60.0, "2024Q4": 70.0})
    assert cost_at(s, "2024Q4", HEADLINE_LAG) == 55.0
    assert cost_at(s, "2024Q4", 2) == 50.0
    assert cost_at(s, "2024Q2", HEADLINE_LAG) is None          # lag 3 missing


def pt_inputs(scale):
    idx = pd.DataFrame({"roaster": "R", "tier": "core", "quarter": ["2023Q1", "2025Q1"],
                        "index": [100.0, 120.0], "main_segment": True, "segment": 1})
    it = pd.DataFrame({"roaster": "R", "quarter": ["2023Q1"], "ppg": [200.0]})
    qs = ["2023Q1", "2023Q2", "2023Q3", "2023Q4", "2024Q1", "2024Q2", "2024Q3", "2024Q4", "2025Q1"]
    cost = [40.0] * 5 + [50.0, 60.0, 70.0, 80.0]
    return idx, it, pd.DataFrame({"quarter": qs, "arabica_roasted_inr_100g": np.array(cost) * scale})


def test_rupee_and_percent_pass_through():
    idx, it, costs = pt_inputs(1.0)
    row = pass_through(idx, it, costs, 0.18).query("lag == '0'").iloc[0]
    # retail +20% of Rs 200 = Rs 40; cost +Rs 40 (40 -> 80): rupee pass-through 100%
    assert row.rupee_pass_through_pct == pytest.approx(100.0)
    # percent: +20% retail vs +100% cost = 20%
    assert row.percent_pass_through_pct == pytest.approx(20.0)


def test_cpi_deflation_splits_nominal_pass_through(tmp_path):
    from src.analysis.inflation import deflate, load_cpi
    # CPI flat at 100 through the pre-shock quarters, 110 by 2025Q1 (+10%).
    months = pd.date_range("2023-01-01", "2025-03-01", freq="MS")
    vals = [100.0 if m < pd.Timestamp("2024-04-01") else 110.0 for m in months]
    f = tmp_path / "INDCPI_2026-09-30.csv"
    pd.DataFrame({"observation_date": months.strftime("%Y-%m-%d"), "INDCPI": vals}).to_csv(f, index=False)
    cpi = load_cpi(f)
    assert cpi.set_index("quarter").cpi_index["2025Q1"] == pytest.approx(110.0)
    # Retail Rs 200 -> +Rs 60 (30%); cost +Rs 40: nominal 150%.
    head = pd.DataFrame({"roaster": ["R"], "quarter": ["2025Q1"], "base_price_100g": [200.0],
                         "retail_change_rs": [60.0], "cost_change_rs": [40.0],
                         "rupee_pass_through_pct": [150.0]})
    out = deflate(head, cpi).iloc[0]
    assert out.inflation_part_rs == pytest.approx(20.0)        # 10% of Rs 200
    assert out.real_rupee_pass_through_pct == pytest.approx(100.0)   # (60-20)/40
    assert out.pass_through_from_inflation_pts == pytest.approx(50.0)


def test_splice_links_new_base_through_overlap():
    from src.analysis.inflation import splice
    d = lambda s, e: pd.date_range(s, e, freq="MS")    # noqa: E731
    old = pd.DataFrame({"date": d("2024-10-01", "2025-03-01"), "cpi": [200, 201, 202, 204, 206, 208.0],
                        "base_year": 2012})
    # New base: same months 2025-01..03 at half the level, then two more months.
    new = pd.DataFrame({"date": d("2025-01-01", "2025-05-01"), "cpi": [102, 103, 104, 105, 106.0],
                        "base_year": 2024})
    out, info = splice(old, new)
    assert info["overlap_months"] == 3 and info["link_factor"] == pytest.approx(2.0)
    s = out.set_index("date").cpi
    assert s[pd.Timestamp("2025-03-01")] == 208.0                 # old base kept where it exists
    assert s[pd.Timestamp("2025-05-01")] == pytest.approx(212.0)  # 106 x 2
    assert len(out) == 8                                          # 6 old + 2 linked


def test_splice_needs_overlap():
    from src.analysis.inflation import splice
    old = pd.DataFrame({"date": pd.to_datetime(["2024-01-01"]), "cpi": [100.0], "base_year": 2012})
    new = pd.DataFrame({"date": pd.to_datetime(["2025-01-01"]), "cpi": [100.0], "base_year": 2024})
    with pytest.raises(ValueError):
        splice(old, new)


def test_roast_loss_changes_rupees_but_not_percent():
    # Roast loss scales every cost figure by 1 / (1 - loss): 15% vs 20% loss.
    a = pass_through(*pt_inputs(1 / 0.85), roast_loss=0.15).query("lag == '0'").iloc[0]
    b = pass_through(*pt_inputs(1 / 0.80), roast_loss=0.20).query("lag == '0'").iloc[0]
    assert a.percent_pass_through_pct == pytest.approx(b.percent_pass_through_pct)
    assert a.rupee_pass_through_pct != pytest.approx(b.rupee_pass_through_pct)


def test_step_timing_dates_the_biggest_link_as_a_range():
    from src.analysis.index import step_timing
    idx = pd.DataFrame({"roaster": "R", "tier": "core", "main_segment": True,
                        "quarter": ["2024Q1", "2024Q3", "2025Q2"],
                        "linked_from": [None, "2024Q1", "2024Q3"],
                        "link_change_pct": [None, 5.0, 30.0],
                        "index": [100.0, 105.0, 136.5]})
    row = step_timing(idx, "2024Q2").iloc[0]
    # Biggest link 2024Q3 -> 2025Q2: happened in 2024Q4..2025Q2, 2..4 quarters after 2024Q2.
    assert (row.step_quarter, row.span_quarters) == ("2025Q2", 3)
    assert (row.quarters_after_earliest, row.quarters_after_latest) == (2, 4)
    assert (row.index_before, row.index_after) == (105.0, 136.5)


def levers_inputs(tmp_path, monkeypatch):
    """One roaster, R. Pre-shock (2023Q1): products A and B at Rs 100/100 g.
    End (2025Q1): A at Rs 120 (same product: +20%), B dropped, C added at Rs 250.
    Product P1 (key A) had a confirmed 250 -> 200 g cut at the same shelf price
    (+25% per 100 g). P2's cut is NOT in the confirmed file, so it must be ignored."""
    from src.analysis import levers
    pd.DataFrame({"product_id": ["P1"]}).to_csv(tmp_path / "confirmed.csv", index=False)
    pd.DataFrame({
        "roaster": "R", "level": "variant", "confidence": "high", "crosses_product_split": "False",
        "product_id": ["P1", "P2"], "variant_id": ["V1", "V2"],
        "from_quarter": "2024Q3", "to_quarter": "2024Q4",
        "sizes_before": "250", "sizes_after": "200",
    }).to_csv(tmp_path / "size_changes.csv", index=False)
    monkeypatch.setattr(levers, "CONFIRMED_CUTS", tmp_path / "confirmed.csv")
    monkeypatch.setattr(levers, "CLEAN", tmp_path)
    variants = pd.DataFrame({"roaster": "R", "variant_id": ["V1", "V1", "V2", "V2"],
                             "quarter": ["2024Q3", "2024Q4", "2024Q3", "2024Q4"],
                             "ppg": [100.0, 125.0, 100.0, 150.0]})
    it = pd.DataFrame({"roaster": "R", "tier": "core",
                       "quarter": ["2023Q1", "2023Q1", "2025Q1", "2025Q1"],
                       "product_key": ["A", "B", "A", "C"], "ppg": [100.0, 100.0, 120.0, 250.0]})
    cov = pd.DataFrame({"roaster": ["R"], "quarter": ["2023Q1"], "source_type": ["archive"],
                        "completeness": ["complete"]})
    idx = pd.DataFrame({"roaster": "R", "quarter": ["2023Q1", "2025Q1"], "index": [100.0, 120.0],
                        "main_segment": True})
    return levers.levers(it, variants, cov, idx).iloc[0]


def test_levers_split_adds_up_on_the_index_baseline(tmp_path, monkeypatch):
    row = levers_inputs(tmp_path, monkeypatch)
    # Total: geometric mean 100 -> sqrt(120 x 250) = 173.2, i.e. +73.2%.
    assert row.total_pct == pytest.approx(73.2)
    # Like-for-like is the index change, the same number the other charts use.
    assert row.like_for_like_pct == pytest.approx(20.0)
    # Pack: 1 confirmed cut of 2 end products x +25% = 12.5 pp; P2 is ignored.
    assert row.size_cut_products == 1
    assert row.size_cut_ppg_change_pct == pytest.approx(25.0)
    assert row.pack_size_pp == pytest.approx(12.5)
    # Range & mix is the remainder, so the parts add back to the total.
    assert row.range_mix_pp == pytest.approx(40.7)
    assert row.like_for_like_pct + row.pack_size_pp + row.range_mix_pp == pytest.approx(row.total_pct)
