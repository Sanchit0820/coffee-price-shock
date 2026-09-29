"""Field-level accuracy of extracted attributes against the hand labels.

Per field:
  accuracy  share of labelled products where the model's value = the hand label
  found     where the hand label is a real value (not "unknown"): share the model got
  invented  where the hand label is "unknown": share where the model gave a value
            anyway (a guess the text doesn't support)
Dropdown fields match exactly (case-insensitive). Free-text fields
(origin_country, region, estate) match after lower-casing and dropping
punctuation and filler words, so "Salawara Estate" = "salawara". Region also
matches when one answer contains the other as whole words ("Gandha" vs
"Gandha, Andhra Pradesh"), since both name the same place.
"""
import re

import pandas as pd

from src.labels import ALLOWED

_FILLER = {"estate", "estates", "farm", "farms", "plantation", "district", "the"}


def norm_free(value: str) -> str:
    words = re.sub(r"[^a-z0-9]+", " ", str(value).lower()).split()
    return " ".join(w for w in words if w not in _FILLER)


# Fields where one answer containing the other counts as a match
# ("Gandha" vs "Gandha, Andhra Pradesh": same place, different detail).
CONTAINMENT_FIELDS = {"region"}


def same(field: str, pred: str, gold: str) -> bool:
    if ALLOWED[field]:
        return str(pred).strip().lower() == str(gold).strip().lower()
    p, g = norm_free(pred), norm_free(gold)
    if p == g:
        return True
    if field in CONTAINMENT_FIELDS and not is_unknown(pred) and not is_unknown(gold) and p and g:
        # Whole-word containment, so "coorg" doesn't match inside "coorgshire".
        return f" {p} " in f" {g} " or f" {g} " in f" {p} "
    return False


def is_unknown(value: str) -> bool:
    return str(value).strip().lower() in ("unknown", "")


def field_scores(pred: pd.DataFrame, gold: pd.DataFrame) -> pd.DataFrame:
    """One row per field. `pred` rows whose extraction failed (status != ok) count as wrong."""
    m = gold.merge(pred, on=["roaster", "product_id"], suffixes=("_gold", "_pred"))
    rows = []
    for field in ALLOWED:
        g, p = m[f"{field}_gold"], m[f"{field}_pred"].fillna("")
        ok = pd.Series([same(field, a, b) for a, b in zip(p, g)], index=m.index)
        known = ~g.map(is_unknown)
        rows.append({
            "field": field, "n": len(m),
            "accuracy": round(ok.mean(), 3),
            "gold_known": int(known.sum()),
            "found": round(ok[known].mean(), 3) if known.any() else None,
            "invented": round((~p[~known].map(is_unknown)).mean(), 3) if (~known).any() else None,
        })
    return pd.DataFrame(rows)


def agreement(a: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    """Share of products (valid in both runs) where two runs give the same value, per field."""
    m = a[a.status == "ok"].merge(b[b.status == "ok"], on=["roaster", "product_id"],
                                  suffixes=("_a", "_b"))
    return pd.DataFrame([{"field": f, "n": len(m),
                          "agreement": round(pd.Series([same(f, x, y) for x, y in
                                                        zip(m[f"{f}_a"], m[f"{f}_b"])]).mean(), 3)}
                         for f in ALLOWED])
