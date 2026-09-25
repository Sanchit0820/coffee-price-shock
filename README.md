# How Indian specialty coffee roasters handled the 2024–25 price shock

Measuring how much of the 2024–25 arabica price spike 10–12 Indian specialty
roasters passed on to retail prices, whether pack sizes shrank
(shrinkflation), and what premiums product attributes command (hedonic
regression).

## Data sources
- Roaster shop pages (current), including Shopify `/products.json` where available
- Internet Archive (Wayback CDX API) snapshots, one per quarter, Jan 2023 onward
- Input costs: ICE arabica / ICO composite prices, Coffee Board of India, RBI INR/USD

## Setup (Windows PowerShell)
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # then fill in values
pytest
```

## Layout
| Path | Contents |
|---|---|
| `data/raw/` | Cached HTTP responses; never re-fetched; not committed |
| `data/clean/` | Tidy tables produced by the pipeline |
| `src/` | Pipeline code (`http_client.py` for scraping, `llm/` for extraction) |
| `notebooks/` | Exploration and analysis |
| `outputs/` | Figures and tables for the write-up |

## Scraping ethics
Every request checks robots.txt, is rate-limited per site, and identifies the
project in its User-Agent. Sites whose terms prohibit automated access are
skipped.

## Status
Phase 0: setup and scaffolding.
