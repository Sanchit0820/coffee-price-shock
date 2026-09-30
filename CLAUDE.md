# Project: How Indian specialty coffee roasters handled the 2024–25 price shock

## Goal
Resume project for analytics roles. Measure retail price pass-through of the
2024–25 arabica spike across 10–12 Indian specialty roasters, detect pack-size
changes (shrinkflation), and estimate attribute premiums (hedonic regression).

## Data sources
- Roaster shop pages (current), incl. Shopify /products.json where available
- Internet Archive (Wayback CDX API) snapshots, one per quarter, Jan 2023 onward
- Input costs: ICE arabica / ICO composite prices, Coffee Board of India, RBI INR/USD

## Rules
- Respect robots.txt and site terms; skip sites that prohibit automated access
- Rate-limit all requests; cache raw HTML in data/raw and never re-fetch
- LLM provider: Gemini API free tier (planned for Phase 3). Keep the LLM
  layer provider-agnostic so the model can be swapped without rewriting
  the pipeline. Cache every LLM response.
- Validate all LLM output with pydantic; failed rows go to a review queue
- Secrets live in .env only; never hardcode or commit keys
- I (Sanchit) must understand every piece of code — explain non-obvious
  logic in comments, keep functions small

## Structure
data/raw, data/clean, src/, notebooks/, outputs/

## Code map
- `src/config.py`: all paths and .env settings; import paths from here
- `src/http_client.py`: `fetch(url)` is the only way to hit the web (cache, robots, rate limit)
- `src/llm/`: `extract(provider, prompt, schema, row_id)` (in `client.py`) for all LLM calls;
  providers implement `LLMProvider` (`base.py`); Gemini lives in `gemini.py`
- `src/scout.py`: Phase 1 check of robots / Shopify / Wayback coverage per roaster
  → `data/roasters_scout.csv` (`python -m src.scout [--refresh]`). CDX normalises
  http/https and www, so one query per URL covers all variants.
- `docs/feasibility.md`: Phase 1 findings. Historical prices come from Shopify's
  embedded `var meta` object on archived collection pages (prices in paise);
  product pages are the fallback. `data/roasters_final.csv` is the chosen list,
  with switch windows to check by hand.
- Phase 2 (`docs/phase2.md`): `python -m src.collect stage1|stage2` builds
  `data/clean/variants_long.csv` + `coverage_report.csv`; `python -m src.size_report`
  finds pack-size changes. Modules: `quarters`, `wayback`, `shopify_meta`, `sizes`,
  `coffee_filter`, `flags`, `product_pages`, `fallback`, `collect`, `size_report`.
- Input costs: `python -m src.costs` reads the newest `data/external/CMO-*_<date>.xlsx`
  (World Bank) and `DEXINUS_<date>.csv` (FRED) -> `data/clean/input_costs_quarterly.csv`
  (₹ green-bean cost per 100 g roasted; roast loss 18% assumed, `--roast-loss`).
  New downloads go in `data/external/` with the download date in the filename.
- Hand labels (`src/labels.py`): Sanchit labels in `data/labels/hand_labels.xlsx`
  (dropdowns, product_id as text); `python -m src.labels import` validates it and writes
  `hand_labels.csv`. Never open the CSV in Excel (it corrupts product IDs). Labelling is
  blind: don't show attribute output until labels are imported.
- Phase 3 (`docs/phase3.md`): `src/product_inputs.py`, `src/extract_attributes.py`
  (prompt attrs-v2, batch 5), `src/evaluate_labels.py`, `src/matching.py` (match-v1).
  Accuracy is reported on held-out labels 21-100 only (1-20 shaped the prompt).
  Don't change the prompt in response to held-out errors without saying so: that
  turns the held-out set into a tuning set.
- Data rules: exclude `served_outside_quarter` rows from quarter-level
  aggregation; filter `partial` quarters before comparing line-ups; don't link
  by variant ID across an `id_break`; treat low-confidence size changes as artifacts;
  exclude `is_bundle` rows from price-per-gram analysis; follow a coffee over time
  with `product_keys_by_quarter.csv` (split at page reuse), never raw product_id;
  use `attributes_valid` before attaching attributes to a product-quarter.
- Review queue: `data/review_queue.jsonl`; LLM cache: `data/cache/llm/`
- Tests: `pytest` from the project root; network and LLM are faked
- Shell is Windows PowerShell 5.1: don't rewrite files with Get-Content/Set-Content
  (it mangles UTF-8); use the editor tools

## Current phase
Phase 4 (analysis) in progress. Phase 3 closed 2026-09-30.
Process/lot-word rule for the title-change check: approved and applied
(`is_different_coffee` in src/product_inputs.py).
Phase 4 first run 2026-09-30: `python -m src.analysis.run` -> outputs/*.png,
outputs/tables/*.csv; findings in `docs/phase4.md`. Headline = RUPEE pass-through
(percent is secondary). Regressions use `src/analysis/ols.py` (statsmodels can't
load: Windows Application Control blocks a scipy DLL). CPI check: two MOSPI
exports (base 2012 + base 2024) spliced over their 12-month overlap in
src/analysis/inflation.py; real rupee pass-through core median 109%. Step-0 LLM work done
(3 Grey Soul re-extractions; Corridor Seven archive->live matching: no links).
One like-for-like definition everywhere: the price index change from the pre-shock
average (charts 1, 3 and 5 agree). Levers are % / percentage points on that
baseline; only the 3 hand-confirmed Grey Soul cuts count (data/review/confirmed_size_cuts.csv).