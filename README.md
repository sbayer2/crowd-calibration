# crowd-calibration: is the prediction-market crowd baked into Jev?

## Context

A LinkedIn post by the user proposes an experiment: take 20-30 active Polymarket questions, ask Jev each one without
the market price, and compare Jev's probability and confidence with the price. The null hypothesis is that Jev's
probabilities are random with respect to prices; rejecting it would support "prediction-market wisdom is encoded in
Jev's calibrated weights".

It can be run with no Polymarket account or subscription. Verified 2026-09-30:
- Polymarket's Gamma API (`https://gamma-api.polymarket.com/markets`) returns `question`, `description`, `outcomes`,
  `outcomePrices`, `bestBid`, `bestAsk`, `lastTradePrice`, `volumeNum`, `liquidityNum`, `endDate`, `createdAt` and
  `negRisk` without authentication.
- Jev runs on the existing gateway credit ($15; about $0.00001 per question).
- openjev runs locally at no cost.

**The post's design is changed in three ways, all from evidence gathered in this session:**
1. **Confidence has to be measured separately from the point estimate.** A noul returns a single number, so its
   "confidence" is just distance from 0.5. Jev is therefore also asked a Score question over probability bins. The
   expected value is the forecast; the spread of the distribution (mid-level mass and entropy) is the confidence.
   This makes the post's "58% with high vs low confidence" measurable.
2. **Obvious markets would inflate the correlation.** Many markets sit at 0.2% or 99.8%. This is the easy-agreement
   confound already recorded in emoji-pile's crowd-disagreement proposal. The primary test is on contested markets
   (price 0.15-0.85); all 60 are reported as secondary.
3. **A control model is needed.** openjev, an open Qwen3.5 4B with Jev's interface, shows whether any correlation is
   Jev-specific or a general language-model prior. Safety-set OJ-001 showed openjev tracks Jev closely on another
   task.

Decisions (user, 2026-09-30): **60 markets** (30 contested + 30 across the full range); **Jev + openjev control**.

## Project

New project `~/projects/crowd-calibration/` (git, local only). Python 3.13 `.venv`; torch and transformers only for the
openjev arm. The layout follows safety-set.

```
crowd-calibration/
  .gitignore            .venv/, __pycache__/, .env, runs/, *.log
  .env                  AI_GATEWAY_API_KEY (the user copies it in, as for safety-set)
  markets.py            fetch + filter + freeze a snapshot of Polymarket markets
  jev.py                copied from safety-set/jev.py (gateway transport, retries); noted as a copy
  openjev_arm.py        pattern of safety-set/openjev_arm.py; vendor/openjev copied with SOURCE.md
  questions.py          state + the two questions (noul, score over probability bins)
  run.py                ask each arm about each frozen market; 3 Jev runs, 1 openjev run
  analyze.py            correlations, permutation test, bootstrap CIs, confidence analysis
  docs/PREDICTIONS.md   written and committed before any model sees a market
  docs/ADC.md           ADC-001...
  tests/FINDINGS.md
  README.md
```
