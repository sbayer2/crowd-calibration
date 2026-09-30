# Pre-registered predictions

Written 2026-09-30, **before the full run**. Committed before any full-run output exists; the git history is the
timestamp. Later changes are dated amendments.

**Snapshot:** `runs/snapshot-20260930-164430.json` (gitignored; its market list and prices are summarised in FINDINGS once the run is
recorded). 60 markets: 30 contested (0.15-0.85), 30 tail markets.

**Disclosure.** A 2-market smoke test was seen first:
- Barcelona to win the Champions League: price 0.235, Jev P(yes) 0.230, bin forecast 0.159.
- Netanyahu to be the next Israeli PM: price 0.325, Jev P(yes) 0.330, bin forecast 0.536.
- openjev: P(yes) 0.919 and 0.685; bin forecasts 0.559 and 0.509.

## Method

- **Arms.** Jev (`typesafe-ai/jev`, gateway, unpinned): 3 runs, per-market mean. openjev 4B v5 (26de23c, local,
  deterministic): 1 run.
- **Inputs.** The state holds the question, resolution rules, close date and snapshot date. Never the price, volume or
  liquidity.
- **Readouts.** `forecast` = the expected bin midpoint of the Score question. `noul` = P(yes). `spread` =
  probability-weighted SD over the bins; this is the confidence.
- **Primary test.** Spearman ρ between Jev's `forecast` and price on the 30 contested markets, one-sided permutation
  test (10,000 shuffles), α = 0.05. H0: forecasts are unrelated to prices. Everything else is secondary.

## Predictions

- **M1 — Jev tracks the crowd on contested markets.** ρ(forecast, price) on contested markets between 0.30 and 0.65,
  p < 0.05.
  *Falsified if* ρ < 0.30 or p ≥ 0.05.
  *Mechanism:* world knowledge up to Jev's training cutoff (candidates, standings, base rates) overlaps with what
  traders know. It is not evidence of "crowd calibration" unless M3 also holds.
- **M2 — The full range looks better than it is.** ρ on all 60 exceeds ρ on contested markets by at least 0.15,
  because obvious longshots (Crystal Palace to win the Premier League at 0.2%) are easy.
- **M3 — Confidence does not track error (the post's claim, predicted to fail).** Spearman(spread, |forecast − price|)
  over all 60 is below 0.25 and not significant.
  *The post's claim holds if* ρ ≥ 0.25 with p < 0.05: confident answers sit closer to the market.
- **M4 — Jev-specific, not generic.** openjev's contested ρ is at least 0.15 below Jev's.
  *If openjev is within 0.15,* the correlation is a general language-model prior, not something specific to Jev.
- **M5 — The two readouts disagree.** Spearman(noul, forecast) over all 60 is below 0.8. The smoke test already showed
  0.33 against 0.54 on one market.
- **Leakage guard.** If the median |Jev P(yes) − price| over all 60 is below 0.02, stop and investigate before
  claiming anything. The state contains no price, so a match that close would need an explanation.

## Follow-up, not predicted here
After resolution: Brier scores for Jev and the market, and the favourite-longshot test (does Jev inherit the market's
overpricing of longshots?).
