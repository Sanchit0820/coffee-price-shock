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
| `input_costs_quarterly.csv` | Green-coffee input costs per quarter, ₹ per 100 g roasted, with 1–3 quarter lags (see "Input costs") |

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
5. **Coffee, bundles and multipacks** (`src/coffee_filter.py`, `src/sizes.py`):
   - `is_coffee_guess` = False only for genuinely non-coffee items (equipment,
     other drinks and formats such as drip bags and concentrates, pantry items
     like cardamom and jaggery, subscriptions and kits). None = ambiguous.
   - `is_bundle` = several coffees sold as one product (samplers, trios,
     "N-in-1", "... Bundle", gift boxes, "Coffees (Pack of 3)"). Bundles are
     coffee, but **exclude them from price-per-gram work**: their size is per
     bag or a total across different coffees. Matched on the product title
     only, because some shops use the type loosely (Black Baza types single
     cardamom and jaggery as "Bundles"). A non-coffee item is never a bundle.
   - "(Pack of N)" on a single coffee is a multipack: per-bag size × N
     (SKIA Coffee (Pack of 2): 2 × 200 g = 400 g, `multipack = True`).
   - **Dope's page-wide size** is not applied to products priced above
     **1.75× the page median**; they're marked `is_bundle` and left unsized.
     **This threshold was fitted to Dope's own price gap**: its three
     multi-coffee bundles (MOST WANTED DOPE, FOREIGN RETURN, ECCENTRIC EDITIONS)
     sit at 1.99–2.79× the median, its dearest single coffee (DOUBLE BARREL)
     at 1.43×. It is not a general rule; revisit it if applied to another shop.
     The card text confirms two of the three ("These 3 have been...", "The 3
     beans here..."); ECCENTRIC EDITIONS is inferred from price alone.
6. **Live:** `/collections/<handle>/products.json`, labelled with the current
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
- **Exclude `is_bundle` rows from price-per-gram analysis** (they stay in the data).
- **Dope's listing cards show regular vs sale prices** ("Regular price
  Rs. 1,520 / Sale price Rs. 1,240 / You Will Save Rs. 280"). The embedded
  data only carries the price actually charged, so for Dope the visible card
  text is a second source of sale information. Use it in Phase 3 when checking
  whether a price drop was a sale.

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
  250 → 200 GMS and 500 → 400 GMS on **6** products, from 2024Q4 through 2025Q4.
  (Corrected in Phase 3: an earlier version said 7, wrongly counting "Fruit
  Naturals", whose sizes went *up*.) **Phase 3 re-check against the
  title-change check: only 3 of the 6 are the same coffee across the cut**
  (see docs/phase3.md, "Grey Soul size cuts re-checked").
- **Grey Soul, unclear:** Badra 500 → 250, Biccode 250 → 150, Fruit Naturals
  150 → 200 and 250 → 400: variant IDs reassigned between sizes. Needs prices to judge.
- **Menu changes (sizes added or dropped), high confidence:** Bloom 11,
  Third Wave 6, Araku 4, Blue Tokai 2, Black Baza 1.
- Bundles are excluded from the size report. Before `is_bundle` existed, 26
  "changes" came from bundles (Blue Tokai trios / 5-in-1 pack, Dope MOST
  WANTED): per-bag vs total weight, not pack-size decisions. All 167 remaining
  changes are high confidence.

**Bundles:** 1,215 rows across 25 products (`is_bundle = True`), all coffee.

## Input costs (`src/costs.py`)

```
python -m src.costs [--roast-loss 0.18]  ->  data/clean/input_costs_quarterly.csv
```

**Sources** (in `data/external/`; the filename carries the download date, and
the loader uses the newest file of each kind):

| File | Source | Series | Units | Frequency |
|---|---|---|---|---|
| `CMO-Historical-Data-Monthly_2026-09-27.xlsx` | World Bank Commodity Price Data ("Pink Sheet"), edition updated 2 Sep 2026, "Monthly Prices" sheet | `Coffee, Arabica` (ICO indicator, other mild Arabicas, avg New York and Bremen/Hamburg, ex-dock); `Coffee, Robusta` (ICO indicator, avg New York and Le Havre/Marseilles, ex-dock) | US$/kg, nominal | Monthly, to 2026M08 |
| `DEXINUS_2026-09-27.csv` | FRED (Federal Reserve Bank of St. Louis), series DEXINUS | Indian rupees to one US dollar, noon buying rates in New York | INR per USD | Daily, 2021-09-20 to 2026-09-18 |

No Coffee Board of India data yet; global series only.

**Method:**
1. Daily INR/USD → monthly mean (blank holiday rows are skipped, not zeros).
2. Per month: green ₹/kg = US$/kg × INR/USD.
3. Per month: **roasted ₹ per 100 g = green ₹/kg ÷ (1 − roast_loss) ÷ 10**.
4. Quarter = mean of its months' rupee values (each month's price at that
   month's rate, not average price × average rate), labelled like
   `variants_long.csv` ("2024Q3"). `months_in_quarter < 3` marks a partial
   quarter: **2026Q3 has July–August only**.
5. `_lag1`, `_lag2`, `_lag3` = the roasted cost 1, 2 or 3 quarters earlier,
   computed before trimming to 2022Q1 onward.

**Assumption: roast loss = 18%** (`roast_loss` column, `--roast-loss` flag).
Roasting typically removes 15–20% of green-bean weight (mostly water), so
1 kg of roasted coffee needs 1 / (1 − 0.18) ≈ 1.22 kg of green. This
is a single assumed value for all roasters and roast levels; darker roasts
lose more. It scales every rupee figure by the same factor, so it changes
levels, not percentage changes over time.

**Units in the output:** `*_usd_kg` US$/kg green; `inr_per_usd` rupees per
dollar; `*_green_inr_kg` ₹/kg green; `*_roasted_inr_100g` ₹ of green bean per
100 g roasted.

**Caveats:**
- **Green-bean cost only.** No roasting, packaging, labour, shipping, GST or
  margin, so it is a cost *driver*, not a cost of goods.
- **Global benchmarks.** Indian specialty roasters mostly buy Indian estate
  coffee, whose prices only partly follow ICO prices. Coffee Board data
  would be the better local series if it becomes available.
- **Earliest lags use a partial quarter.** The FX series starts 20 Sep 2021,
  so 2021Q3 is one partial month; it only feeds 2022Q1 `lag2` and 2022Q2
  `lag3`. Analysis from 2023Q1 onward is unaffected.

## Known gaps

- Subko's line-up narrows to microlots after 2024Q2, and 40% of its rows have no size.
- Coverage is uneven; missing quarters stay missing (no interpolation).
