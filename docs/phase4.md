# Phase 4: analysis

Run 30 September 2026. Reproduce with `python -m src.analysis.run` (no LLM
calls). Charts: `outputs/1_price_index.png` ... `outputs/5_positioning.png`.
Tables (each chart's table view): `outputs/tables/`.

## Set-up (fixed before looking at any retail result)

- **Periods were set from the input-cost series alone, before any retail
  numbers were computed.** Green-coffee cost was flat at Rs 42-49 per 100 g
  roasted through 2024Q1 and rose from 2024Q2 (peak Rs 95 in 2025Q4), so
  **pre-shock = 2023Q1-2024Q1** and **shock = 2024Q2 onward**; the end point is
  the live snapshot, 2026Q3 (whose cost covers July-August only).
- **Araku's pre-shock baseline is shorter:** its archive starts in 2023Q4, so
  its baseline is 2023Q4-2024Q1 (2 quarters) rather than up to 5.
- **Data:** coffee only (LLM `is_coffee` = yes, not Phase 2 non-coffee - which
  drops drip bags, concentrates, subscriptions - and not a bundle); rows served
  outside their quarter, without a pack size, or inside a URL-switch window are
  excluded. 31,068 of 36,019 variant rows remain, forming 3,020 items
  (product key x pack size x quarter, priced at the median across grind options).
  Products are followed by `product_keys_by_quarter.csv` (split at page reuse).
- **Core 7 roasters give the headline; all 11 are the robustness check.**
  Subko has no usable index (median 1 matched item per link) and is left out of
  index and pass-through, kept in levers and the regression (decision D2).
- **Corridor Seven is partial evidence** (decision D1): its 2025 archived pages
  used other product IDs. Its 2024 products are live again, so its index links
  2024Q3 directly to 2026Q3 on 24 matched items; its 2025 prices rest on a
  3-item link. It is flagged wherever it appears.
- Cost basis: arabica (ICO, World Bank), Rs per 100 g roasted at an assumed
  18% roast loss; 15% and 20% are reported too.

## 1. Price index (`1_price_index.png`, `1_price_index.csv`)

Chained index of the same products at the same pack size; a quarter links to
the most recent earlier quarter sharing at least 3 such items, so products
coming and going, missing pages and pack-size changes can't move it. There is
never a unit-value bridge. Pre-shock average = 100.

- **Finding:** by 2026Q3 the core roasters' like-for-like prices stood 21-69%
  above their pre-shock level (Araku 121, Blue Tokai 137, Third Wave 139,
  Corridor Seven 141, Kapi Kottai 152, Devans 169), while green-coffee cost
  had roughly doubled (index 202).
  *Caveat:* Grey Soul's index ends in 2025Q4 at 109 because too few of its
  products carry into the live snapshot.
- **Finding:** prices moved in a few large steps, mostly a year or more after
  the cost began rising in 2024Q2 (Blue Tokai +25% and Kapi Kottai +36% in
  2025Q3, Third Wave +34% in 2026Q2); Devans was the exception, stepping up
  from 2024Q2 onward.
  *Caveat:* quarterly snapshots can't date a step more precisely than a quarter.
  `1_step_timing.csv` dates each roaster's largest single link as a range
  (earliest to latest quarter, since a link can span an archive gap): the core
  median is 5 quarters after 2024Q2 on both bounds; Corridor Seven's biggest
  step spans 2024Q3 -> 2026Q3 and can't be dated.

## 2. Pass-through (`2_pass_through.png`, `2_pass_through_headline.csv`)

Headline = **rupee pass-through**: the retail rupee increase per 100 g divided
by the green-coffee rupee increase per 100 g roasted, pre-shock average to the
latest quarter, with cost averaged over lags 0-3 (pre-specified, not the
best-fitting lag).

- **Finding (headline):** the median core roaster raised retail prices by
  **Rs 1.65 for every Rs 1 rise in green-coffee cost** (rupee pass-through
  165%; range 51-237%); every core roaster except Grey Soul passed on more
  than the full rupee increase.
  *Caveat:* the cost is a global arabica benchmark; Indian estate prices,
  roasting, packaging and GST also moved, so above-100% pass-through does not
  by itself mean wider margins.
- **Percent pass-through (secondary):** median 42.5% (retail +21-69% against
  cost +92%). *Green coffee is only part of the retail price, so percent
  pass-through understates how much of the cost rise was passed on.*
- **Robustness:** all 10 roasters with an index: median rupee pass-through
  162%, percent 41%. Excluding the partial Corridor Seven: core median 162%.
- **Roast loss:** core median rupee pass-through is 171% at 15% loss, 165% at
  18%, 161% at 20%; percent pass-through is identical at all three, because
  roast loss scales every cost rupee by the same factor (tested).
- **Inflation check (CPI-deflated), `2_pass_through_real_cpi.csv`:** each
  roaster's retail rupee increase is split into what general inflation alone
  would give (pre-shock price x CPI growth) and the real remainder; real rupee
  pass-through = real remainder / green-coffee rupee increase. CPI rose 12.6%
  from the pre-shock average to 2026Q3.
  - **Finding:** general inflation explains about **56 points of the 165%**:
    median core real rupee pass-through is **109%** (107-113% at 15-20% roast
    loss; 109% excluding Corridor Seven and across all roasters).
  - **Which story the numbers support:** for the typical core roaster, **full
    pass-through of the green-coffee cost plus general inflation, not broad
    margin expansion** (real pass-through close to 100%: Blue Tokai 109%, Third
    Wave 108%); only Devans (167%) and Kapi Kottai (179%) raised prices by
    clearly more than cost plus inflation, consistent with margin expansion
    relative to green coffee, while Araku (51%) and Grey Soul (2%, where
    inflation accounts for its entire like-for-like rise) absorbed part of the cost.
  - *Caveat:* the cost is a global arabica benchmark, not what Indian roasters
    paid, and CPI is economy-wide, not roasters' own non-coffee costs; 2026Q3
    CPI covers July-August only.
  - **CPI source and splice:** MOSPI, All India, Combined, General index,
    monthly, in two exports (`data/external/CPI_base2012_2026-09-30.xlsx`,
    Jan 2022-Dec 2025; `CPI_base2024_2026-09-30.xlsx`, Jan 2025-Aug 2026).
    They were spliced into one series in 2012-base units: 2012-base values are
    kept through Dec 2025; the 8 months Jan-Aug 2026 are the 2024-base values
    x a link factor of **1.8985** = mean(2012-base) / mean(2024-base) over the
    **12 months both cover (Jan-Dec 2025)**. The month-by-month ratio in the
    overlap stayed within 1.8937-1.9027 (0.5% spread), so one factor is safe.
    Quarterly CPI = mean of its months, rebased to the pre-shock average = 100.
    Details: `2_cpi_splice.csv`, `2_cpi_monthly_spliced.csv`, `2_cpi_quarterly.csv`.
- **Lags:** the headline sits in the middle of lags 0-3 for every roaster
  (e.g. Blue Tokai 141-199% across lags).
- **Finding:** quarter-to-quarter retail changes show no detectable link to
  cost changes at 0-3 quarter lags (pooled regression, sum of lags -0.03,
  95% CI -0.25 to +0.19, 70 observations, core; all roasters +0.13, CI -0.10
  to +0.37, 95 observations).
  *Caveat:* small sample; this says repricing is lumpy and slow, not that it
  didn't happen - the long-difference headline is the measure to use.

## 3. Levers (`3_levers.png`, `3_levers.csv`)

Same baseline and definition as sections 1, 2 and 5: from the **pre-shock
average** (the main index segment's pre-shock quarters whose listing page was
complete) to the **last quarter of the main index segment** (2026Q3; Grey Soul
2025Q4). The total is split into:

- **total** = % change in the geometric-mean price per 100 g of all coffee
  items listed (pre-shock quarters averaged in logs);
- **like-for-like** = the price index change (index at end - 100). This is the
  same number as charts 1 and 5, so like-for-like repricing is now identical
  across the charts (an earlier version measured it from a single start
  quarter and disagreed with chart 5, e.g. Devans 63% vs 69%);
- **pack-size cuts** = (confirmed cut products / products in the end line-up)
  x the average % change in price per 100 g per cut;
- **range & mix** = total - like-for-like - pack size: products added or
  dropped and shifts in size mix. A remainder, not measured directly.

The segments are in percentage points of the total % change. Because the parts
are subtracted in percent rather than log points they don't compound exactly,
but at these sizes the difference is small and everything is in one unit.

| Roaster | Total | Like-for-like | Pack-size cuts | Range & mix |
|---|---|---|---|---|
| Kapi Kottai | +62.8% | +52.2% | - | +10.7 pp |
| Blue Tokai | +52.1% | +37.2% | - | +14.9 pp |
| Third Wave | +44.5% | +39.3% | - | +5.2 pp |
| Devans | +43.9% | +68.6% | - | -24.7 pp |
| Grey Soul (to 2025Q4) | +37.8% | +8.6% | +6.8 pp | +22.3 pp |
| Corridor Seven (partial) | +36.6% | +40.7% | - | -4.0 pp |
| Dope | +31.1% | +26.9% | - | +4.2 pp |
| Araku | +12.1% | +21.1% | - | -9.0 pp |

- **Finding:** straight like-for-like price rises did most of the work for
  every roaster except Grey Soul.
  *Caveat:* range & mix is a remainder, not measured directly.
- **Finding:** Blue Tokai and Kapi Kottai's line-ups also moved upmarket, adding
  about 15 and 11 points on top of their price rises (Blue Tokai added 20
  products at a median Rs 298/100 g and dropped 23 at Rs 197; Kapi Kottai
  dropped 18 at a median Rs 196 and added 3 at Rs 360).
- **Finding:** Devans and Araku raised like-for-like prices by 69% and 21% but
  their line-ups moved to cheaper coffee, so their average price per 100 g rose
  only 44% and 12% (range & mix -25 and -9 points; Devans' 4 new products median
  Rs 175/100 g vs Rs 480 for its 3 dropped ones).
  *Caveat:* few products are involved (Devans 4 added, 3 dropped; Araku 3 and 3).
- **Finding:** Grey Soul's average price per 100 g rose 38% to 2025Q4, but only
  about 9 points came from repricing the same products. Newer, pricier coffees
  (added median Rs 350/100 g vs Rs 260 dropped) gave about 22 points and the 3
  pack-size cuts about 7.
  *Caveat:* only 1 Grey Soul product runs from the pre-shock quarters to 2025Q4;
  its like-for-like figure is a chain of shorter overlaps, not one set of
  products followed throughout.
- **Finding (shrinkflation):** Grey Soul cut the pack size of **3 products,
  confirmed as the same coffee across the cut**, from 250 g to 200 g (and
  500 g to 400 g) **at an unchanged shelf price**: 20% less coffee, +25% per
  100 g. The 3 (listed in `data/review/confirmed_size_cuts.csv`):
  - Nagaland Zunheboto Naturals: 250 g Rs 649 -> 200 g Rs 649; 500 g Rs 1,250 -> 400 g Rs 1,250 (2023Q3 -> 2024Q4)
  - Roasters Espresso (Med-Dark Roast): 250 g Rs 699 -> 200 g Rs 699 (2025Q3 -> 2025Q4)
  - Strawberry in Loop: 250 g Rs 699 -> 200 g Rs 699 (2025Q3 -> 2025Q4), then the
    200 g pack rose to Rs 799 by 2026Q3 - a price rise on top of the shrink.
  All three were later repriced upward as well (`3_size_cuts.csv`): Nagaland
  200 g Rs 699 and 400 g Rs 1,373 by 2025Q1; Roasters Espresso 200 g Rs 799 by 2026Q3.
  Weighted by the share of Grey Soul's 2025Q4 line-up affected (3 of 11
  products x +25%), pack-size cuts account for about 7 points of its
  line-up-wide change.
  *Caveat:* only these 3 count. Two other same-variant "cuts" (Badra
  500 -> 250 g, Biccode 250 -> 150 g) are variant IDs reassigned between sizes,
  i.e. relabels, and are excluded; 3 more Grey Soul size changes are different
  coffees on reused pages.
- Not split: Black Baza and Bloom (no complete pre-shock page inside the index
  segment) and Subko (no price index).

## 4. Hedonic regression (`4_hedonic.png`, `4_hedonic_coefficients.csv`)

log(price per 100 g) on process, species, origin type (`origin_type_analysis`),
roast level, roaster, log pack size and quarter; before and during the shock
separately; SEs clustered by product. Core: 818 observations / 143 products
before, 1,521 / 197 during. Categories with < 5 products or < 20 observations
are not reported. Baseline: washed / arabica / single origin / medium roast.

- **Finding:** before the shock, natural and experimental processes sold at a
  premium over washed of about 25% (95% CI 12-39%) and 21% (10-34%).
  *Caveat:* 17 and 20 products.
- **Finding:** during the shock the estimated premiums were smaller (natural
  +8%, CI -1 to +17%; experimental +10%, CI 1-21%), but no before-vs-during change
  is statistically clear (every shock-period shift's 95% CI includes zero).
  *Caveat:* read as "no evidence the premiums changed", not "they narrowed".
- **Finding:** blends sold about 13-16% below single origins in both periods
  (CI roughly -27% to -4%).
  *Caveat:* `origin_type_analysis` is a rule-derived field (Phase 3), not the
  model's own origin_type.
- **Finding:** bigger packs are cheaper per gram: each doubling of pack size
  lowers the price per 100 g by about 10% in both periods (coefficient -0.148
  per log unit before, -0.141 during: -9.8% and -9.3% per doubling).
- Species and most roast levels are too thin or too often "unknown" to support
  a finding. **Robustness:** all 11 roasters give the same signs (natural +20%
  and experimental +19% before; blend -15%/-11%).

## 5. Positioning (`5_positioning.png`, `5_positioning.csv`)

- **Finding:** the cheapest roaster (Devans, Rs 126/100 g pre-shock) repriced
  most (+69%) and the two priciest (Araku Rs 256, Grey Soul Rs 260) least
  (+21%, +9%); the middle is mixed.
  *Caveat:* 10 roasters - a pattern, not a tested relationship; Grey Soul is
  measured to 2025Q4, and Subko has no like-for-like measure.
- **Reading the percentages:** cheaper coffee needs a bigger % rise for the
  same rupee increase, because green coffee is a larger share of its price.
  Green coffee rose about Rs 42 per 100 g roasted; that is +33% of Devans'
  Rs 126 pre-shock price but only +16% of Grey Soul's Rs 260. The chart's grey
  curve is the % rise that equals that Rs 42 at each price level; a roaster
  above it passed on more rupees than green coffee rose. So part of the
  "cheapest repriced most" pattern is arithmetic, not a different pricing
  strategy. On the curve's terms, every roaster except Grey Soul sits above it
  (Araku only just), matching the rupee pass-through in section 2.

## Open items

- **Step 0 LLM work completed** (after Gemini 503 retries): the 3 Grey Soul
  products flagged by the process/lot rule were re-extracted one per call
  (no attribute value changed) and are now in the regression; matching for
  Corridor Seven's archive-to-live ID change rejected all 16 candidate pairs
  (the live products are its 2024 coffees under their original IDs, not
  renamed 2025 listings), so no new links and nothing for review. The analysis
  was re-run afterwards; only the regression's shock-period figures moved,
  slightly (numbers above are the final ones).
- Colours: the dataviz skill's documented, pre-validated palette, used
  unchanged (its validator needs Node.js, which isn't installed).
- `statsmodels` can't load here (Windows Application Control blocks a scipy
  file), so regressions use `src/analysis/ols.py` (numpy; tested).
