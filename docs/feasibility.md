# Phase 1 feasibility: can we get historical prices from archived pages?

Checked September 2026. Scout output: `data/roasters_scout.csv`. Final list: `data/roasters_final.csv`.

## Method

1. **Scout** (`src/scout.py`): for each candidate, check robots.txt, whether
   `/products.json` works (Shopify), and count Wayback snapshots per quarter
   of the beans listing page from 2023-Q1. Older addresses of the same page
   (`extra_archive_urls` in `data/roasters_candidates.csv`) are merged in.
2. **Feasibility sample** (one-off script, not the scraper): for each shortlisted
   roaster, open the earliest archived listing snapshot from 2023 and from 2025
   (raw `id_` snapshots, i.e. the HTML as originally served) and check:
   - prices and pack sizes in the visible text;
   - links to product pages, and whether 3 sampled product pages have 2023 snapshots;
   - structured data on one 2023 product page (JSON-LD, Shopify variant JSON);
   - Shopify's embedded analytics object on the listing itself
     (`var meta = {"products": [...]}`), which lists every product's variants
     with price and variant title.
3. All requests went through `src/http_client.py` (robots-checked, rate-limited,
   cached in `data/raw`).

## Key findings

- **No archived `/products.json` anywhere.** The Wayback Machine has never
  captured it for any candidate. Historical prices must come from archived HTML.
- **Visible listing text is not enough.** Prices are mostly "from ₹X" or a
  single price without a size, and 2023 listings show no pack sizes. Some 2023
  listings (Third Wave, Black Baza) render cards with JavaScript, so the
  visible HTML has no prices at all.
- **The embedded `var meta` object is the data source.** On Shopify collection
  pages it lists every variant with a price and a title such as
  `Whole Beans / 250g`. It is present on 2023 and 2025 snapshots for every
  roaster below, so **Phase 2 is built around archived collection pages**, with
  product pages only as a fallback (their variant JSON has a `weight` in grams).
- It is **not** present on Shopify *content* pages (`/pages/...`), which is why
  Subko's `/pages/coffee` was replaced by its collection pages.

## Results

Variant counts are from the embedded `var meta` object (2023 → 2025).
"Sized" = variant title contains a pack size.

| Roaster | Listing URL(s) used | 2023 → 2025 variants | Sized | Product pages with 2023 snapshots (of 3) | Product-page structured data | Verdict |
|---|---|---|---|---|---|---|
| Third Wave | `/collections/coffee-beans` | 96 → 56 | 100% / 100% | 3 | Variant JSON + JSON-LD | Pass |
| Devans | `/collections/coffee` | 384 → 394 | 99% / 99% | 3 | Variant JSON, price + weight | Pass |
| Grey Soul | `/collections/coffee` | 480 → 463 | 95% / 97% | 3 | Variant JSON, price + weight | Pass |
| Kapi Kottai | `/collections/all` | 309 → 237 | 100% / 100% | 3 | Variant JSON, price + weight | Pass |
| Araku | `/collections/coffee` | 52 → 43 | 77% / 93% | 2 | Variant JSON + JSON-LD | Pass (2023 starts Nov) |
| Corridor Seven | `/collections/all` | 463 → 448 | 100% / 100% | 2 | Variant JSON, price + weight | Pass |
| Bloom | `/collections/coffee` | 351 → 241 | 99% / 99% | 3 | Variant JSON, price + weight | Pass |
| Blue Tokai | `/collections/coffee` → `/collections/roasted-and-ground-coffee-beans` | 681 → 626 | 98% / 94% | 2 | Variant JSON, price + weight | Pass (stitched) |
| Black Baza | `store.` subdomain `/collections/all-coffee` → `www` `/collections/coffee` | 183 → 135 | 81% / 90% | 3 | Variant JSON + JSON-LD, price + weight | Pass (stitched) |
| Subko | `/collections/roasted-beans` + `/collections/specialty-arabica-microlots` | 145 → 73 | 24% / 68% | 1 | Variant JSON + JSON-LD, price + weight | Pass with caveat |
| Dope | `/collections/coffee` | 185 → 177 | 0% / 0% | 3 | Variant JSON, no weight | Pass with caveat |
| Seven Beans | `/collections/coffee` | — → 69 | — / 99% | 3 | Variant JSON, price + weight | **Fail: no 2023 listing** |
| Savorworks | `/collections/coffee` | — → 157 | — / 99% | 2 | Variant JSON + JSON-LD | **Fail: no 2023 listing** |

What the unsized variants are:
- **Kapi Kottai, Corridor Seven:** none. They were 1 kg packs that a first
  version of the size pattern missed (it required 2+ digits); fixed.
- **Devans, Bloom, Blue Tokai, Black Baza, Grey Soul, Seven Beans, Savorworks:**
  non-coffee or bundles (chicory, concentrate, drip bags, sampler packs, filters,
  "4 X COFFEES"), plus Grey Soul 1 kg variants spelled "1 Kilogram".
- **Araku 2023:** Grand Reserve variants are titled `Whole Beans / Tin` with no
  size; the size must come from the product page.
- **Subko:** many microlot variants carry grind / jar options but no size;
  sizes need product pages (their variant JSON has `weight`).
- **Dope:** no variant has a size; the store sells one pack size (250 gm, shown
  in visible text). Size comes from text, so shrinkflation checks rely on it.

## Caveats for Phase 2

- **Prices are in paise.** `43000` in `var meta` means ₹430.00. Divide by 100.
- **Sale prices.** `var meta` has no compare-at ("was") price, so a sale during
  a snapshot looks like a price cut. Cross-check with the visible "Sale price" /
  strikethrough text or the product page's `compare_at_price` before counting a drop.
- **Missing sizes.** Parse size from the variant title; fall back to the
  product page's variant `weight` (grams), then to visible text. Keep 1 kg,
  "Kilo", "Kilogram" and "gms" spellings in the pattern.
- **Non-coffee items** (equipment, chicory, drip bags, samplers, subscriptions)
  appear on some listings (Corridor Seven and Kapi Kottai use `/collections/all`).
  Filter by product `type` and by title.
- **Coverage is uneven.** Quarters with no snapshot stay missing; do not
  interpolate prices.
- **Visible-text parsing fails on JavaScript-rendered 2023 pages** (Third
  Wave, Black Baza), so it cannot be the primary method.

## Switch windows (stitched roasters)

A price, pack-size or line-up jump inside these windows must be checked by
hand before it counts as a price increase or shrinkflation.

| Roaster | Window | What changed | Risk |
|---|---|---|---|
| Blue Tokai | 2024-04-18 to 2024-05-23 | Collection renamed on the same Shopify store | Low |
| Black Baza | 2025-03-19 to 2025-07-20 | Moved from `store.blackbazacoffee.com` to `www` (platform change); no 2025-Q2 data | High |
| Subko | after 2024-Q2 | `roasted-beans` archive ends; `specialty-arabica-microlots` (microlots only) continues | Medium: line-up scope narrows |
| Dope | 2026-03-07 | New `/pages/shop-dope`; old collection still live in 2026-Q1 | Low (after the main window) |

Black Baza's old subdomain robots.txt (archived 2023, 2024, 2025) is Shopify's
default: it does not block collections or products, or our user agent.
