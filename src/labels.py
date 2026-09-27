"""Hand-label sample for validating the LLM attribute extraction.

    python -m src.labels create   ->  data/labels/hand_labels.csv (never overwrites)

100 products, stratified: at least MIN_PER_ROASTER from every roaster, the rest
in proportion to roaster size. Within a roaster, Phase 2's ambiguous products
(is_coffee unresolved) are taken first, up to half its quota, then the rest is
split between products with and without a live description. Fixed seed.

The file shows only the text the model will see, never any pipeline label,
so labelling stays blind. Note lines at the top start with "#"; read_labels()
skips them.
"""
import argparse
import math

import pandas as pd

from src import config
from src.product_inputs import OUT as INPUTS

LABELS_DIR = config.DATA_DIR / "labels"
LABELS = LABELS_DIR / "hand_labels.csv"
SAMPLE_SIZE = 100
MIN_PER_ROASTER = 5
SEED = 42

TEXT_COLUMNS = ["roaster", "product_id", "product_title", "other_titles", "product_type",
                "variant_titles", "card_text", "description"]
# The fields to label, with the allowed values (same as the extraction schema).
FIELDS = {
    "is_coffee": "yes / no / unknown",
    "origin_country": "country name, 'multiple' or unknown",
    "region": "e.g. Chikmagalur, Coorg, Araku Valley; or unknown",
    "estate": "estate or farm name; or unknown",
    "species": "arabica / robusta / blend / other / unknown",
    "origin_type": "single_origin / blend / unknown",
    "process": "washed / natural / honey / monsooned / experimental / mixed / unknown",
    "roast_level": "light / light_medium / medium / medium_dark / dark / omni / unknown",
    "decaf": "yes / no / unknown",
    "flavoured_infused": "yes / no / unknown",
}
NOTE = [
    "# LABEL ONLY FROM THE TEXT PROVIDED IN THIS ROW. Use \"unknown\" when the text "
    "doesn't say. Don't look anything up or use outside knowledge.",
    "# Allowed values -> " + " | ".join(f"{k}: {v}" for k, v in FIELDS.items()),
    "# species 'other' = excelsa, liberica etc. process 'experimental' = anaerobic, "
    "carbonic maceration, yeast/koji/culture fermentation. Save as CSV UTF-8.",
]


def allocate(sizes: pd.Series, total: int = SAMPLE_SIZE, floor: int = MIN_PER_ROASTER) -> dict:
    """Per-roaster quotas: `floor` each (or all, if a roaster has fewer), the
    remainder split in proportion to how many products remain above the floor.
    Largest remainders get the leftover units so quotas sum exactly to `total`."""
    base = {r: min(floor, n) for r, n in sizes.items()}
    spare = {r: sizes[r] - base[r] for r in sizes.index}
    left = total - sum(base.values())
    raw = {r: left * spare[r] / sum(spare.values()) for r in sizes.index}
    quota = {r: base[r] + math.floor(raw[r]) for r in sizes.index}
    for r in sorted(raw, key=lambda r: raw[r] - math.floor(raw[r]), reverse=True):
        if sum(quota.values()) >= total:
            break
        if quota[r] < sizes[r]:
            quota[r] += 1
    return quota


def sample_roaster(g: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    """Ambiguous products first (up to half of n), then a description / no-description mix."""
    is_amb = g.is_coffee_guess_p2.isna() | (g.is_coffee_guess_p2 == "")
    take_amb = g[is_amb].sample(min(is_amb.sum(), n // 2), random_state=seed)
    # The rest of the quota comes from NON-ambiguous products, so the "half"
    # cap holds; leftover ambiguous ones only fill in if a roaster runs short.
    rest = g[~is_amb]
    k = n - len(take_amb)
    with_desc = rest[rest.has_description]
    n_desc = min(len(with_desc), round(k * len(with_desc) / len(rest))) if len(rest) else 0
    picked = [take_amb, with_desc.sample(n_desc, random_state=seed)]
    remaining = rest.drop(picked[1].index)
    picked.append(remaining.sample(min(k - n_desc, len(remaining)), random_state=seed))
    short = n - sum(len(p) for p in picked)
    if short > 0:
        spare_amb = g[is_amb].drop(take_amb.index)
        picked.append(spare_amb.sample(min(short, len(spare_amb)), random_state=seed))
    return pd.concat(picked)


def create() -> None:
    if LABELS.exists():
        raise SystemExit(f"{LABELS} already exists; not overwriting hand labels.")
    inputs = pd.read_csv(INPUTS, dtype={"product_id": str, "is_coffee_guess_p2": str})
    quota = allocate(inputs.groupby("roaster").size())
    sample = pd.concat(sample_roaster(g, quota[r], SEED) for r, g in inputs.groupby("roaster"))
    # Shuffle so roasters are interleaved (less anchoring on one shop's style).
    sample = sample.sample(frac=1, random_state=SEED).reset_index(drop=True)
    out = sample[TEXT_COLUMNS].fillna("")
    out.insert(0, "label_id", range(1, len(out) + 1))
    for field in FIELDS:
        out[field] = ""
    out["labeller_notes"] = ""
    LABELS_DIR.mkdir(parents=True, exist_ok=True)
    # utf-8-sig so Excel shows ₹ and accented names correctly.
    with LABELS.open("w", encoding="utf-8-sig", newline="") as f:
        f.write("\n".join(NOTE) + "\n")
        out.to_csv(f, index=False)
    print(f"Wrote {len(out)} products to {LABELS}")
    print(sample.groupby("roaster").size().to_string())
    amb = sample.is_coffee_guess_p2.isna() | (sample.is_coffee_guess_p2 == "")
    print(f"ambiguous: {amb.sum()}, with description: {sample.has_description.sum()}, "
          f"title/card only: {(~sample.has_description).sum()}")


def read_labels() -> pd.DataFrame:
    """The labelled file, skipping the '#' note lines at the top."""
    with LABELS.open(encoding="utf-8-sig") as f:
        skip = 0
        for line in f:
            if not line.startswith("#"):
                break
            skip += 1
    return pd.read_csv(LABELS, skiprows=skip, dtype=str, encoding="utf-8-sig").fillna("")


def main() -> None:
    parser = argparse.ArgumentParser(description="Hand-label sample")
    parser.add_argument("action", choices=["create"])
    parser.parse_args()
    create()


if __name__ == "__main__":
    main()
