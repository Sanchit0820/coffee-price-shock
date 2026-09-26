"""Input costs: unit conversion, FX averaging, quarter aggregation, lags, loader."""
import pandas as pd
import pytest
from openpyxl import Workbook

from src import costs

# ---------- unit conversion ----------


def test_green_inr_per_kg():
    assert costs.green_inr_per_kg(8.0, 85.0) == 680.0


def test_roasted_per_100g_default_loss():
    # 820 Rs/kg green at 18% loss: 1 kg roasted needs 1/0.82 kg green = Rs 1000/kg -> Rs 100 per 100 g
    assert costs.roasted_inr_per_100g(820.0) == pytest.approx(100.0)


def test_roasted_per_100g_other_losses():
    assert costs.roasted_inr_per_100g(850.0, roast_loss=0.15) == pytest.approx(100.0)
    assert costs.roasted_inr_per_100g(800.0, roast_loss=0.20) == pytest.approx(100.0)
    assert costs.roasted_inr_per_100g(1000.0, roast_loss=0.0) == pytest.approx(100.0)


@pytest.mark.parametrize("bad", [-0.1, 1.0, 1.5])
def test_roast_loss_must_be_a_share(bad):
    with pytest.raises(ValueError):
        costs.roasted_inr_per_100g(800.0, roast_loss=bad)


# ---------- FX ----------

def test_monthly_fx_ignores_blank_days():
    daily = pd.DataFrame({"observation_date": ["2024-01-02", "2024-01-03", "2024-01-26", "2024-02-01"],
                          "DEXINUS": [83.0, 85.0, None, 84.0]})
    fx = costs.monthly_fx(daily)
    assert fx.inr_per_usd.tolist() == [84.0, 84.0]   # Jan = mean(83, 85); the holiday isn't a zero
    assert fx.fx_days.tolist() == [2, 1]
    assert fx.month.tolist() == [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-02-01")]


# ---------- quarters ----------

def monthly_frame(values, start="2024-01-01"):
    months = pd.date_range(start, periods=len(values), freq="MS")
    return pd.DataFrame({"month": months, "x": values, "fx_days": 20})


def test_quarter_labels_and_means():
    q = costs.to_quarters(monthly_frame([1, 2, 3, 10, 20, 30]))
    assert q.quarter.tolist() == ["2024Q1", "2024Q2"]   # same labels as variants_long.csv
    assert q.x.tolist() == [2.0, 20.0]
    assert q.months_in_quarter.tolist() == [3, 3]


def test_partial_quarter_is_flagged():
    q = costs.to_quarters(monthly_frame([1, 2, 3, 4, 6], start="2025-01-01"))  # Apr-May only
    assert q.months_in_quarter.tolist() == [3, 2]
    assert q.x.tolist() == [2.0, 5.0]


def test_rupees_averaged_month_by_month():
    # Month 1: $10 at 80 = 800; month 2: $5 at 100 = 500 -> mean 650.
    # (Average price x average rate would give 7.5 x 90 = 675: wrong.)
    prices = pd.DataFrame({"month": pd.to_datetime(["2024-01-01", "2024-02-01"]),
                           "arabica_usd_kg": [10.0, 5.0], "robusta_usd_kg": [1.0, 1.0]})
    fx = pd.DataFrame({"month": prices.month, "inr_per_usd": [80.0, 100.0], "fx_days": 20})
    q = costs.to_quarters(costs.monthly_costs(prices, fx, 0.18))
    assert q.arabica_green_inr_kg.iloc[0] == pytest.approx(650.0)


# ---------- lags ----------

def test_lags_shift_by_whole_quarters():
    q = pd.DataFrame({"quarter": ["2024Q3", "2024Q1", "2024Q2", "2024Q4"], "c": [3, 1, 2, 4]})
    out = costs.add_lags(q, ["c"])
    assert out.quarter.tolist() == ["2024Q1", "2024Q2", "2024Q3", "2024Q4"]   # sorted first
    assert out.c_lag1.tolist()[1:] == [1, 2, 3]
    assert out.c_lag3.tolist()[3] == 1
    assert out.c_lag1.isna().iloc[0]


# ---------- Pink Sheet loader ----------

def pink_sheet(path, arabica_unit="($/kg)"):
    """A tiny workbook with the real layout: title rows, header row, unit row, months."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Monthly Prices"
    ws.append(["World Bank Commodity Price Data (The Pink Sheet)"])
    ws.append([None, "Crude oil", "Coffee, Arabica", "Coffee, Robusta"])
    ws.append([None, "($/bbl)", arabica_unit, "($/kg)"])
    ws.append(["2024M01", 80.0, 5.5, 3.1])
    ws.append(["2024M02", 81.0, 6.0, 3.3])
    wb.save(path)
    return path


def test_load_pink_sheet_finds_columns_by_header(tmp_path):
    df = costs.load_pink_sheet(pink_sheet(tmp_path / "cmo.xlsx"))
    assert df.columns.tolist() == ["month", "arabica_usd_kg", "robusta_usd_kg"]
    assert df.arabica_usd_kg.tolist() == [5.5, 6.0]
    assert df.month.tolist() == [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-02-01")]


def test_load_pink_sheet_rejects_changed_units(tmp_path):
    with pytest.raises(ValueError):
        costs.load_pink_sheet(pink_sheet(tmp_path / "cmo.xlsx", arabica_unit="(cents/lb)"))
