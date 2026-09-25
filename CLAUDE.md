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
- Review queue: `data/review_queue.jsonl`; LLM cache: `data/cache/llm/`
- Tests: `pytest` from the project root; network and LLM are faked
- Shell is Windows PowerShell 5.1: don't rewrite files with Get-Content/Set-Content
  (it mangles UTF-8); use the editor tools

## Current phase
Phase 1: roaster selection
