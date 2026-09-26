# Phase 2: historical price collection

Collected September 2026. No LLM calls and no analysis; this phase builds the
dataset and flags its weak spots.

## How to rebuild

```
python -m src.collect stage1            # archived listings + live products.json
python -m src.collect stage2 --dry-run  # count product-page requests
python -m src.collect stage2            # product pages for missing sizes, then rebuild
python -m src.size_report               # pack-size changes across quarters
```

Everything is cached in `data/raw`, so re-running rebuilds the outputs without
new requests (apart from robots.txt checks, which aren't cached).

## Outputs (`data/clean/`)

| File | Contents |
|---|---|
| `variants_long.csv` | One row per variant per roaster-quarter, plus live rows (36,019) |
| `coverage_report.csv` | One row per roaster-quarter (+ live): snapshot, pages, variant count, % sized / non-coffee / ambiguous, ID carryover, live comparison |
| `product_page_sizes.csv` | Stage 2 results per product-quarter (status, snapshot, size per variant) |
| `product_handles.csv` | Product ID → URL handle and how it was found |
| `size_changes.csv` | Pack-size changes between consecutive observed quarters, with `confidence` |

## Method

1. **Snapshot per quarter:** the collection-page snapshot inside the quarter
   nearest its middle (Feb 15 / May 15 / Aug 15 / Nov 15), across all URLs in
   `archive_urls_counted`. Never borrowed from a neighbouring quarter.
2. **Pagination:** expected pages = highest `?page=N` linked from the listing
   (following later pages too). Extra pages use the archived copy nearest the
   page-1 date within ±30 days. Flag: `single_page`, `complete` or `partial`
   (with `missing_pages`).
3. **Parsing:** Shopify's embedded `var meta` object. Prices are paise → rupees
   (÷100). Product title = variant name minus the variant title.
4. **Size:** variant title → product title → (Dope only) the single size
   printed on the listing → stage 2 product page for the same quarter
   (variant title/options → the one size in the product text → shipping
   weight). `size_source` records which.
5. **Live:** `/collections/<handle>/products.json`, labelled with the current
   quarter and `source_type=live`. Prices there are rupee strings, and `grams`
   is shipping weight (used only as a labelled last resort).

## Rules for later phases

- **Exclude `served_outside_quarter` rows from every quarter-level aggregation.**
  They stay in the file, flagged. (One case: Dope "2026Q1" is an October 2025 capture.)
- **Filter partial quarters** before comparing product counts or line-ups
  across quarters (23 roaster-quarters; Bloom 6 of 7, Corridor Seven 5 of 8).
- **Don't link rows by variant ID across an ID break.** `id_break` in the
  coverage report marks quarters where under 10% of IDs carried over (Devans
  2024Q2, Grey Soul 2023Q2, Corridor Seven 2025Q1, Subko 2023Q2 and 2024Q3);
  those roasters have `variant_ids_stable = False`. Match by name in Phase 3.
  Black Baza's domain move kept 90% of IDs, so no manual flag.
- **Size changes with `confidence = low` are artifacts** until checked.

## Results

**Coverage:** 110 archived roaster-quarters, no fetch errors. Size coverage of
coffee and ambiguous archive rows is 99–100% for 9 roasters; Araku 88%
(Grand Reserve: product pages have no size or no snapshot), Subko 60% (most
product pages never state a size). Live size coverage 97%.

**Stage 2:** 111 product-quarters: 67 sized from their own quarter's product
page, 24 with no product-page snapshot in that quarter (size left empty, not
assumed), 20 with no findable URL handle. 709 rows filled; 105 requests.

**Sales:** 0 candidates. 46 drops over 10% exist, but none reverted the next
quarter. Compare-at prices were found for 19 archive rows.

**Live vs latest archive:** no bias between sources: where the last archived
quarter is recent (Third Wave, Blue Tokai, Dope), live prices match exactly.
Larger uniform gaps where the archive ends earlier (Araku +24%, Grey Soul +14%,
Black Baza +7%, Corridor Seven −6%) look like whole-catalogue repricing; check in Phase 3.

**Pack-size changes** (`size_changes.csv`):
- **Grey Soul (core), high confidence:** the same variant IDs relabelled
  250 → 200 GMS and 500 → 400 GMS on 7 products, from 2024Q4 through 2025Q4.
  The clearest shrinkflation signal in the data.
- **Grey Soul, unclear:** Badra 500 → 250, Biccode 250 → 150, Fruit Naturals
  150 → 200 and 250 → 400: variant IDs reassigned between sizes. Needs prices to judge.
- **Menu changes (sizes added or dropped), high confidence:** Bloom 11,
  Third Wave 6, Araku 4, Blue Tokai 2, Black Baza 1.
- **Low confidence = bundles** the non-coffee rules missed: Blue Tokai
  "5-in-1 Explorer Pack", "The Monsoon Trio", "The Rich & Bold Trio Pack";
  Dope "MOST WANTED DOPE". Their "size change" is per-bag vs total weight.

## Known gaps

- Bundles named "pack", "trio" or "N-in-1" are not caught by `is_coffee_guess`.
- Dope's single-size rule gives bundles on its page the 250 g size.
- Subko's line-up narrows to microlots after 2024Q2, and 40% of its rows have no size.
- Coverage is uneven; missing quarters stay missing (no interpolation).
