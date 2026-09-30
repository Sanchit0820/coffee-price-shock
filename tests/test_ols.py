"""The numpy OLS against known answers."""
import numpy as np
import pandas as pd
import pytest

from src.analysis.ols import dummies, ols


def test_recovers_known_coefficients():
    rng = np.random.default_rng(0)
    x = rng.normal(size=500)
    y = 2.0 + 3.0 * x + rng.normal(scale=0.1, size=500)
    fit = ols(pd.Series(y), pd.DataFrame({"const": 1.0, "x": x}))
    assert fit["params"]["x"] == pytest.approx(3.0, abs=0.02)
    assert fit["ci_low"]["x"] < 3.0 < fit["ci_high"]["x"]
    assert fit["r2"] > 0.99


def test_hc1_matches_hand_formula_for_mean():
    # Regressing on a constant only: HC1 variance = n/(n-1) * sum(e^2)/n^2
    y = pd.Series([1.0, 2.0, 4.0, 7.0])
    fit = ols(y, pd.DataFrame({"const": [1.0] * 4}))
    e = y - y.mean()
    assert fit["se"]["const"] ** 2 == pytest.approx(4 / 3 * (e ** 2).sum() / 16)


def test_clustering_widens_ses_with_repeated_units():
    rng = np.random.default_rng(1)
    units = np.repeat(np.arange(40), 10)                 # 40 products, 10 quarters each
    unit_effect = rng.normal(size=40)[units]
    x = rng.normal(size=40)[units]                        # x fixed within a product
    y = 1.0 * x + unit_effect + rng.normal(scale=0.1, size=400)
    X = pd.DataFrame({"const": 1.0, "x": x})
    hc1 = ols(pd.Series(y), X, cov="HC1")["se"]["x"]
    cl = ols(pd.Series(y), X, cov="cluster", groups=units)["se"]["x"]
    assert cl > 2 * hc1       # treating 10 copies as independent overstates precision


def test_dummies_drop_baseline():
    d = dummies(pd.Series(["washed", "natural", "honey", "washed"]), "process", baseline="washed")
    assert list(d.columns) == ["process[honey]", "process[natural]"]
