# Phase 3: LLM attribute extraction and product matching

Run 30 September 2026 on `gemini-3.8-flash` (paid tier after the free tier's
20 requests/day ran out). No analysis in this phase. **Status: closed.**

**Headline:** on held-out hand labels 21-100, the raw model output averages
**93.6%** accuracy over the 8 informative fields. Labels were never corrected
after seeing model output.

## How to rebuild

```
python -m src.product_inputs               # inputs table (no LLM); also title-change check
python -m src.labels xlsx | import | india-rule   # hand labels (see below)
python -m src.extract_attributes pilot     # batch 5 vs batch 20 on labels 1-20
python -m src.extract_attributes run       # all products -> product_attributes.csv
python -m src.extract_attributes review    # rebuild review file + accuracy, no LLM calls
python -m src.matching [--dry-run]         # links across ID breaks -> product_matches.csv
python -m src.product_keys                 # per-quarter keys, split at page reuse
python -m src.size_report                  # re-run: marks changes crossing a split
python -m src.llm.smoke                    # one tiny live call to check the model
```

Every LLM response is cached (keyed on provider, model and full prompt), so
re-running costs nothing unless the inputs or prompt change. The inputs table
is deterministic (stable sort), which the cache relies on.

## Reliability layer (`src/llm/`)

- Retry only on 429/503, with exponential backoff (2, 4, 8, 16, 32 s + jitter).
  The Gemini adapter maps those to a provider-agnostic `RetryableError`.
- The Google SDK's own retries are **off** (`attempts=1`): with both layers on,
  one call became up to 30 requests during a 503 spell and exhausted the free quota.
- Batches are validated item by item; a failed or missing item is retried alone.
- Every output row records `model` and `prompt_version`.

## Inputs (`data/clean/product_inputs.csv`)

536 products (roaster, product_id). 202 have a live description, 334 are title
only; 433 have listing-card text; 517 have at least one of the two.

**Title-change check:** if a product ID's successive titles share under 50% of
their distinctive words (generic words like coffee/roast/blend ignored), the
page may have been reused for another coffee (e.g. Devans "VIETNAMESE ROBUSTA
COFFEE" -> "COLOMBIAN ARABICA COFFEE"). 8 products are flagged
(`title_changed`, listed in `data/review/title_changes.csv`); their earlier
titles are left out of the extraction text. Five are Grey Soul, including two
products in the Phase 2 size-change report ("Ultra Light Nagaland", "Fruit
Naturals"): those size changes may be a different coffee on a reused page.

## Hand labels (`data/labels/`)

100 products, stratified by roaster (min 5), labelled blind by Sanchit in
`hand_labels.xlsx` from the row text only; `import` validates and writes
`hand_labels.csv`. One rule was applied uniformly to all 100 labels after
labelling (not tuned to model output): **where region is an Indian place,
origin_country = India** (16 rows changed; `src/labels.py INDIAN_REGIONS`).
Labels 1-20 were used in the pilot and shaped the prompt, so **accuracy is
reported on labels 21-100 (held out)**. Decaf is "unknown" in all 100 labels
and flavoured in 97, so those two fields say little and are reported apart.

## Extraction (`src/extract_attributes.py`, prompt `attrs-v2`)

Fields: is_coffee, origin_country, region, estate, species, origin_type,
process, roast_level, decaf, flavoured_infused, each with confidence and an
evidence snippet. **Validation:** allowed values only; any value other than
"unknown" needs evidence found verbatim in that product's text.

**Pilot (labels 1-20):** batch 5 and batch 20 both 20/20 valid, 97.5% agreement;
batch 20 drew on outside knowledge (species from variety names, roast from
"Vienna Roast"), so the run uses **batch 5**. attrs-v2 then added: cask/barrel
aged = flavoured; the word "blend" alone isn't an origin blend; no species or
roast from variety/style names.

**Full run:** 536 products, 108 batches + 47 single retries (155 calls).
533 valid (489 first time, 44 after retry), 3 failed twice (in the review file).

**Held-out accuracy (labels 21-100, n = 80):**

| Field | Accuracy | Found (label known) | Invented (label unknown) |
|---|---|---|---|
| is_coffee | 97.5% | 97.5% | - |
| origin_country | 92.5% | 93.5% | 8.2% |
| region | 92.5% | 88.5% | 5.6% |
| estate | 95.0% | 96.6% | 3.9% |
| species | 98.8% | 95.5% | 0.0% |
| origin_type | **76.2%** | 67.3% | 7.1% |
| process | 98.8% | 97.2% | 0.0% |
| roast_level | 97.5% | 97.5% | 0.0% |
| decaf | 98.8% | (none known) | 0.0% |
| flavoured_infused | 90.0% | 50.0% (2 known) | 7.7% |

**Mean over the 8 informative fields: 93.6% (headline, raw model output).** A
product that failed validation counts as wrong on every field (one held-out
product, "Bird-Friendly Bundle"). After the post-processing rules below the
same figure is 93.9%; the difference comes only from rule 5 (that product's
fields become "unknown", which matches the label where the label is
"unknown"). `python -m src.extract_attributes review` prints both.

**origin_type (76.2%) is a definition clash, kept as the clean figure.** The
labels treat an estate-named product as single origin and a "... Blend" title
as a blend; the approved attrs-v2 rule says the word "blend" alone is not
enough, so the model answers "unknown" there (15 of 19 held-out misses). The
prompt was not changed after seeing held-out errors.

Error patterns (details in the Phase 3 report):
- **origin_type** is mostly definitional: the labels treat an estate-named
  product as single origin and a "... Blend" title as a blend; the approved
  attrs-v2 rule says the word "blend" alone is not enough, so the model says
  "unknown" there.
- **flavoured_infused "no"**: the model sometimes says "no" with irrelevant
  evidence ("100% Arabica"). The verbatim check proves a snippet exists, not
  that it supports the value.
- Some disagreements look like labelling misses (the text does say it).
- Genuine model errors include taking the roaster's name "ARAKU" as a region.

**is_coffee vs Phase 2:** of the 34 Phase 2 ambiguous products, the LLM calls 22
coffee and 12 not. Of 52 Phase 2 non-coffee products, the LLM calls 25 coffee
(drip bags, subscriptions etc. are coffee products but not bags of beans);
price-per-gram work should keep using both columns.

## Post-processing rules (decided 30 Sep 2026; applied to all products, no LLM calls)

Applied in `postprocess()` (`src/extract_attributes.py`); idempotent.

1. **`origin_type_analysis`** (for the analysis only; never scored): title
   contains the word "blend" -> blend; else a named estate (the extracted
   `estate`) or "single origin/estate" in the text -> single_origin; else the
   model's `origin_type`. `origin_type_analysis_rule` records which rule
   fired: 47 title blend, 243 estate/single-origin, 246 model value.
2. **decaf / flavoured_infused "no" needs real evidence** (text that says
   unflavoured / no added flavours / caffeinated etc.); otherwise "unknown".
   46 flavoured "no" answers changed; the model's own answers are kept in
   `*_model` columns.
3. (No correction of labels after seeing model output; no disagreement review.)
4. **Reused pages are different products**: see "Product keys per quarter".
5. **The 3 products that failed validation twice are kept, all "unknown"**
   (`rules_applied` says so).

## Process/lot-word rule (approved 30 Sep 2026, applied before Phase 4)

The title-change check also flags a change when BOTH titles name a process
(natural, washed, honey incl. red/yellow/black/white honey, anaerobic,
carbonic, monsooned, fermented, yeast, koji, culture...) or a lot ("Lot #08")
and it differs, even with high word overlap - it had missed Grey Soul "Graded
Naturals -> Graded Washed". One test (`is_different_coffee`) drives both the
flag and the key split. Effect: **11 flagged products** (3 new, all Grey Soul),
**521 product keys**; the size report marks 64 changes as crossing a split; the
same 3 of 6 Grey Soul size cuts survive. The 3 new products' attributes were
re-extracted one per call (no value changed). Matching also now checks for an
ID break between the last archived quarter and the live snapshot (same < 10%
carryover rule): only Corridor Seven qualified, and all 16 candidate pairs
were rejected (its live products are its 2024 coffees under original IDs).

## Product keys per quarter (`src/product_keys.py`)

`data/clean/product_keys_by_quarter.csv` gives the key for every
product-quarter. For the 8 products flagged by the title-change check the key
is **split where the distinctive title words change** (segment 1 keeps the
key; later segments get `<key>@<first quarter>`, with `segment_start_date`).
9 new keys from 8 products (one Grey Soul page reused twice), **518 keys in
all**. Extraction saw only the latest title of a flagged product, so
`attributes_valid` is True only for its last segment. **Use this file, not
product_id, to follow a coffee over time.** The size report marks changes that
cross a split (`crosses_product_split`, 26 rows, all Grey Soul).

## Grey Soul size cuts re-checked

Phase 2 reported same-variant 250 -> 200 g / 500 -> 400 g cuts on 7 Grey Soul
products; the correct count is **6** (the 7th, "Fruit Naturals", went up).
Checked for "same coffee across the cut" by title before vs after:

| Product | Title before -> after | Verdict |
|---|---|---|
| Strawberry in Loop | unchanged | same coffee |
| Roasters Espresso (Med-Dark Roast) | unchanged | same coffee |
| Nagaland Zunheboto Naturals | "(Light-Med Profile)" -> "(Light Profile)" | same coffee, roast profile changed too |
| Odisha Red Honey -> Odisha Floral Honey | different honey-process name | unclear |
| Nagaland Zunheboto Graded Naturals -> Graded Washed | process changed | different coffee |
| Nagaland Kohima 23 Naturals -> Ultra Light Nagaland | flagged page reuse (split) | different coffee |

**3 of 6 survive** (2 with an unchanged title). The "Graded Naturals -> Graded
Washed" case was NOT flagged by the title-change check (57% word overlap):
a change of process word can mean a different coffee even when most words
stay. A process/lot-word rule for the check is an open decision.

## Matching (`src/matching.py`, prompt `match-v1`)

96 candidate pairs across the 5 ID breaks (14 identical titles accepted by
rule, 82 judged by the LLM). Result: **27 links**: 14 identical titles, 9 by
the LLM (7 Devans, 2 Subko), 4 by reviewer decision (Devans duplicate old
listings); 68 rejected by the LLM; 1 rejected by the reviewer (Grey Soul Badra:
new title adds a variety, possibly another lot). 536 products -> 509
`product_key`s (536 - 27).
Reviewer decisions live in `data/review/match_review.csv` (`your_decision`)
and survive re-runs.

## Files

| File | Contents |
|---|---|
| `data/clean/product_inputs.csv` | Model inputs per product, title-change flag |
| `data/clean/product_attributes.csv` | Attributes + confidence + evidence, model, prompt_version, status |
| `data/clean/product_matches.csv` | product_key per product and how it was linked |
| `data/clean/product_keys_by_quarter.csv` | product_key per product-quarter, split at page reuse (use this) |
| `data/clean/match_candidates.csv` | Every candidate pair and decision |
| `data/clean/pilot/` | Pilot outputs (attrs-v1) |
| `data/review/attribute_review.csv` | 11 products: 3 failed, 8 title changes |
| `data/review/match_review.csv` | Match decisions (5 decided) |
| `data/review/title_changes.csv` | Possible page reuse within one product ID |
