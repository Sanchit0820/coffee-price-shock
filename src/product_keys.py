"""Product keys per quarter, split where a product ID's page was reused for another coffee.

    python -m src.product_keys  ->  data/clean/product_keys_by_quarter.csv

The key from product_matches.csv follows one coffee across ID breaks. But a
product ID can also be REUSED for a different coffee (Devans "VIETNAMESE
ROBUSTA COFFEE" -> "COLOMBIAN ARABICA COFFEE"). For the products flagged by the
title-change check, the key is split where the distinctive title words change:
  segment 1 keeps the product's key; segment n gets "<key>@<first quarter>".
segment_start_date is the earliest snapshot in that first quarter.

attributes_valid: extraction for flagged products used the latest title only,
so its attributes describe the LAST segment; earlier segments must not inherit
them. Unflagged products: always True.

Use this file (not product_id) to follow a coffee over time.
"""
import pandas as pd

from src import config
from src.product_inputs import TITLE_CHANGE_BELOW, TITLE_CHANGES_OUT, title_similarity

OUT = config.CLEAN_DIR / "product_keys_by_quarter.csv"


def segment_titles(titles: list[str]) -> list[int]:
    """Segment number (1, 2, ...) for each title in time order: a new segment
    starts when a title shares < TITLE_CHANGE_BELOW of its distinctive words
    with the current segment's latest title."""
    segments, current, last = [], 1, None
    for t in titles:
        if last is not None and t != last and title_similarity([last, t]) < TITLE_CHANGE_BELOW:
            current += 1
        segments.append(current)
        last = t
    return segments


def build() -> pd.DataFrame:
    from src.collect import VARIANTS_OUT
    from src.matching import MATCHES_OUT

    v = pd.read_csv(VARIANTS_OUT, dtype=str)
    keys = pd.read_csv(MATCHES_OUT, dtype=str).set_index(["roaster", "product_id"]).product_key
    flagged = set(map(tuple, pd.read_csv(TITLE_CHANGES_OUT, dtype=str)[["roaster", "product_id"]].values))
    v["date"] = v.served_ts.str[:8]
    per_q = (v.groupby(["roaster", "product_id", "quarter", "source_type"])
              .agg(product_title=("product_title", lambda s: s.mode().iloc[0]),
                   first_date=("date", "min"))
              .reset_index())
    # Archive before live within the same quarter label, so live is always last.
    per_q["order"] = per_q.source_type.map({"archive": 0, "live": 1})
    per_q = per_q.sort_values(["roaster", "product_id", "quarter", "order"], kind="stable")
    out = []
    for (roaster, pid), g in per_q.groupby(["roaster", "product_id"], sort=False):
        base = keys[(roaster, pid)]
        is_flagged = (roaster, pid) in flagged
        segs = segment_titles(list(g.product_title)) if is_flagged else [1] * len(g)
        last_seg = max(segs)
        starts = {}
        for seg, r in zip(segs, g.itertuples()):
            starts.setdefault(seg, (r.quarter, r.first_date))
        for seg, r in zip(segs, g.itertuples()):
            start_q, start_d = starts[seg]
            out.append({
                "roaster": roaster, "product_id": pid, "quarter": r.quarter,
                "source_type": r.source_type, "product_title": r.product_title,
                "product_key": base if seg == 1 else f"{base}@{start_q}",
                "segment": seg, "segment_start_quarter": start_q,
                "segment_start_date": (f"{start_d[:4]}-{start_d[4:6]}-{start_d[6:8]}"
                                       if isinstance(start_d, str) and len(start_d) >= 8 else ""),
                "title_changed": is_flagged,
                "attributes_valid": (not is_flagged) or seg == last_seg,
            })
    return pd.DataFrame(out)


def main() -> None:
    df = build()
    df.to_csv(OUT, index=False)
    split = df[df.segment > 1].drop_duplicates(["roaster", "product_id", "segment"])
    print(f"Wrote {len(df)} product-quarters, {df.product_key.nunique()} product keys to {OUT}")
    print(f"split products: {df[df.title_changed].product_id.nunique()}, new keys from splits: {len(split)}")
    print(split[["roaster", "product_id", "segment_start_quarter", "segment_start_date",
                 "product_title"]].to_string(index=False))


if __name__ == "__main__":
    main()
