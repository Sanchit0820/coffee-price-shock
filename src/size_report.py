"""Find pack-size changes across quarters (data check, not analysis).

    python -m src.size_report   ->  data/clean/size_changes.csv

Two levels, both between consecutive OBSERVED quarters of a roaster:
  variant: the same variant ID shows a different size (the same buy option
           now weighs something else: the clearest shrinkflation signal);
  product: the same product ID offers a different SET of sizes (e.g. 250 g
           replaced by 200 g, or a 1 kg option added).
Uses coffee and ambiguous rows only, and leaves out rows served from outside
their quarter. Products whose IDs changed (catalogue rebuilds) can't be
followed here; Phase 3 matches those by name.
"""
import pandas as pd

from src import config

VARIANTS = config.CLEAN_DIR / "variants_long.csv"
OUT = config.CLEAN_DIR / "size_changes.csv"


# Sizes read from a title the shop wrote for that product/variant. Shipping
# weight (can include packaging, or be a bundle's total) and the page-wide
# single-size rule (a bundle on Dope's page inherits "250 gm") are weaker.
TITLE_SOURCES = {"variant_title", "product_title", "product_page_variant"}


def confidence(source_before: str, source_after: str) -> str:
    """"high" only if both sizes came from titles; else "low" (check by hand)."""
    return "high" if {source_before, source_after} <= TITLE_SOURCES else "low"


def usable(v: pd.DataFrame) -> pd.DataFrame:
    return v[(v.is_coffee_guess.astype(str) != "False")
             & (v.served_outside_quarter.astype(str) != "True")
             & v.size_grams.notna()]


def variant_changes(v: pd.DataFrame) -> list[dict]:
    out = []
    for (roaster, vid), g in v.groupby(["roaster", "variant_id"]):
        g = g.drop_duplicates("quarter").sort_values("quarter")
        for (_, a), (_, b) in zip(g.iterrows(), g.iloc[1:].iterrows()):
            if a.size_grams != b.size_grams:
                out.append({"level": "variant", "roaster": roaster, "product_id": a.product_id,
                            "product_title": b.product_title, "variant_id": vid,
                            "variant_title_before": a.variant_title, "variant_title_after": b.variant_title,
                            "from_quarter": a.quarter, "to_quarter": b.quarter,
                            "sizes_before": a.size_grams, "sizes_after": b.size_grams,
                            "size_source_before": a.size_source, "size_source_after": b.size_source,
                            "confidence": confidence(a.size_source, b.size_source)})
    return out


def product_changes(v: pd.DataFrame) -> list[dict]:
    out = []
    for (roaster, pid), g in v.groupby(["roaster", "product_id"]):
        menu = g.groupby("quarter").size_grams.apply(lambda s: tuple(sorted(set(s))))
        sources = g.groupby("quarter").size_source.apply(set)
        quarters = sorted(menu.index)
        for qa, qb in zip(quarters, quarters[1:]):
            if menu[qa] != menu[qb]:
                both = sources[qa] | sources[qb]
                out.append({"level": "product", "roaster": roaster, "product_id": pid,
                            "product_title": g[g.quarter == qb].product_title.iloc[0],
                            "from_quarter": qa, "to_quarter": qb,
                            "sizes_before": " ".join(f"{x:g}" for x in menu[qa]),
                            "sizes_after": " ".join(f"{x:g}" for x in menu[qb]),
                            "confidence": "high" if both <= TITLE_SOURCES else "low"})
    return out


def main() -> None:
    v = usable(pd.read_csv(VARIANTS, dtype={"product_id": str, "variant_id": str}))
    df = pd.DataFrame(variant_changes(v) + product_changes(v))
    df.to_csv(OUT, index=False)
    print(f"Wrote {len(df)} size changes to {OUT}")


if __name__ == "__main__":
    main()
