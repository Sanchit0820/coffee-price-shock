# How Indian coffee roasters handled the 2024–25 price shock

*By Sanchit*

## The problem

Between early 2024 and early 2025, green arabica roughly doubled in price.
If you run pricing at a coffee roaster, you see that in your own costs. What
you don't see is what everyone else is doing. Are they raising prices? By how
much? Are they quietly shrinking packs? You end up repricing blind.

So I built a pipeline to find out. It tracks the shelf prices of 11 Indian
specialty roasters every quarter from 2023 to 2026, using archived copies of
their shop pages. It compares those prices to the cost of green coffee and to
general inflation. An LLM reads each product description to pull out origin,
process and roast. I checked it against 80 products I labelled by hand, and it
was right 93.6% of the time.

## What I found

**1. Roasters passed on the full cost rise, plus inflation, more than a year late.**

- Green coffee went up by Rs 42 per 100 g of roasted coffee.
- The typical roaster raised its shelf price by 165% of that in rupees.
- Most of the extra is general inflation (prices across India rose 12.6%).
  Take that out, and the typical roaster passed on 109%, about the whole cost
  rise.
- It didn't happen smoothly. Prices sat still, then jumped. The typical
  roaster's biggest jump came 5 quarters after costs started rising.

**2. Roasters used different levers.**

- Most simply raised prices on the same coffees.
- Some also moved upmarket. Blue Tokai and Kapi Kottai shifted their range
  toward pricier coffees, which lifted their average price by another 11–15
  points.
- Devans went the other way. It raised prices on the same coffees by 69%, but
  swapped pricier coffees for cheaper ones, so its average rose only 44%.

**3. Grey Soul shows why you have to look past same-product prices.**

- On the same coffees, Grey Soul raised prices by only 9%. That looks like a
  roaster absorbing the cost.
- But its average price per 100 g rose 38%. Most of that came from newer,
  pricier coffees (about 22 points).
- About 7 points came from shrinking packs. Three coffees went from 250 g to
  200 g at the same shelf price: 20% less coffee, 25% more per gram. All
  three were later repriced upward too.

## What I'd tell a roaster's pricing team

- **Track competitors' prices on the same products, not their average.** An
  average moves when the range changes, and that can hide a price rise or fake
  one.
- **Measure pass-through in rupees.** In percent, you'll always look like
  you're under-passing, because green coffee is only part of your price.
- **Expect competitors to move in steps, with a lag.** A quiet quarter doesn't
  mean they're holding. The big moves here came more than a year after the
  cost rise.
- **Watch pack sizes and new launches.** They're how some roasters raised
  prices without changing the number on the shelf.

I'm not saying which approach works best. I don't have sales data, so I can't
tell how customers responded.

## Limitations

- No sales or volume data, so nothing here is about demand.
- Quarterly snapshots. I can date a price move to a quarter at best.
- 11 roasters. The patterns are descriptive, not statistically tested.
- Coverage varies. Grey Soul's data ends in late 2025, and one roaster's
  evidence is partial.
- Shelf prices only. Coupons and subscriptions aren't captured.

## What I'd do next

- Get sales or volume data from a roaster, to measure how demand responded to
  price steps, pack cuts and range changes.
- Run the pipeline monthly as a live competitor price tracker.

## Sources for every number

All in `outputs/tables/` in the
[project repo](https://github.com/Sanchit0820/coffee-price-shock):

| Number | File |
|---|---|
| Arabica roughly doubled, early 2024 to early 2025 (101 → 198) | `1_cost_index.csv` |
| 11 roasters | `5_positioning.csv` |
| 93.6% accuracy on 80 hand-labelled products | `0_label_accuracy.csv` |
| Rs 42 per 100 g cost rise; 165% rupee pass-through (core median) | `2_pass_through_headline.csv` |
| Prices across India +12.6% | `2_cpi_quarterly.csv` |
| 109% after inflation; most of the extra from inflation (core median 56 points of the 65 above 100%) | `2_pass_through_real_cpi.csv` |
| Biggest jump 5 quarters after costs rose (core median) | `1_step_timing.csv` |
| Blue Tokai +15, Kapi Kottai +11 points; Devans 69% vs 44%; Grey Soul 9%, 38%, 22 and 7 points | `3_levers.csv` |
| 250 g → 200 g at the same price, +25% per gram, later repriced up | `3_size_cuts.csv` |
