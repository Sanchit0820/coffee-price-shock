"""Ordinary least squares with robust standard errors, in plain numpy.

Written because statsmodels can't load here: Windows Application Control
blocks one of scipy's compiled files, and statsmodels imports scipy.

  cov="HC1"      heteroskedasticity-robust (White, small-sample corrected)
  cov="cluster"  clustered by `groups` (CR1: same correction as Stata / statsmodels)
Confidence intervals use the normal approximation (+/- 1.96 SE); p-values are
two-sided normal. With few observations these are approximate - the reason the
regression results are reported as supporting, not headline, evidence.
"""
import math

import numpy as np
import pandas as pd

Z95 = 1.959964


def _p_normal(t: np.ndarray) -> np.ndarray:
    return np.array([math.erfc(abs(x) / math.sqrt(2)) for x in t])


def ols(y: pd.Series, X: pd.DataFrame, cov: str = "HC1", groups=None) -> dict:
    """Fit y = X b. Returns params, se, ci_low, ci_high, p (all Series by column), cov, n, k, r2."""
    Xv, yv = X.to_numpy(float), y.to_numpy(float)
    n, k = Xv.shape
    bread = np.linalg.pinv(Xv.T @ Xv)           # pinv: tolerant of a redundant dummy
    beta = bread @ Xv.T @ yv
    e = yv - Xv @ beta
    if cov == "HC1":
        meat = (Xv * e[:, None] ** 2).T @ Xv
        V = n / (n - k) * bread @ meat @ bread
    elif cov == "cluster":
        g = pd.factorize(pd.Series(groups))[0]
        G = g.max() + 1
        scores = np.zeros((G, k))
        np.add.at(scores, g, Xv * e[:, None])
        meat = scores.T @ scores
        V = G / (G - 1) * (n - 1) / (n - k) * bread @ meat @ bread
    else:
        raise ValueError(cov)
    se = np.sqrt(np.clip(np.diag(V), 0, None))
    idx = X.columns
    r2 = 1 - (e @ e) / ((yv - yv.mean()) @ (yv - yv.mean()))
    return {"params": pd.Series(beta, idx), "se": pd.Series(se, idx),
            "ci_low": pd.Series(beta - Z95 * se, idx), "ci_high": pd.Series(beta + Z95 * se, idx),
            "p": pd.Series(_p_normal(beta / np.where(se > 0, se, np.nan)), idx),
            "cov": pd.DataFrame(V, idx, idx), "n": n, "k": k, "r2": r2}


def dummies(s: pd.Series, prefix: str, baseline: str | None = None) -> pd.DataFrame:
    """One 0/1 column per level except the baseline (default: first level, sorted)."""
    levels = sorted(s.unique())
    base = baseline if baseline in levels else levels[0]
    return pd.DataFrame({f"{prefix}[{lv}]": (s == lv).astype(float)
                         for lv in levels if lv != base}, index=s.index)
