# Pre-registered predictions — experiment 2: tonight's games

Written 2026-09-30 at about 18:00 UTC, **before any games snapshot was frozen or any model saw a game**. The git history
is the timestamp. Later changes are dated amendments.

## Design

- **Games.** Polymarket moneyline markets (MLB, NHL, NFL, NBA, WNBA) starting 20 minutes to 30 hours after each
  daily freeze, both quotes present, spread ≤ 0.03, liquidity ≥ $20k (`games.py`). Price = the bid-ask midpoint for
  the first-listed team A. Frozen daily for 7 days, from 2026-09-30.
- **Inputs.** League, the two teams, start time, today's date and the resolution rules. Never the price.
- **Arms.**
  - Jev (gateway alias, unpinned): 3 runs, per-game mean.
  - openjev 4B v5 (26de23c): 1 run.
- **Readouts.**
  - `p_a` (primary) = the mean of P(A wins) and 1 − P(B wins), both sides asked, to cancel the aversion to "very
    likely yes" seen in C-001.
  - Also reported: `p_a_bins` (the same from the 7-bin Score) and the one-sided P(A wins).
- **Outcome.** Resolved by `resolve.py` from the closed market (the outcome priced at exactly 1). Voided or unresolved
  games are excluded and listed.
- **Scores.** Brier (primary) and log loss, for the market, Jev, openjev and a coin flip (0.5), each with a bootstrap
  95% CI, plus a paired bootstrap of Brier(Jev) − Brier(market).

## Predictions

- **G1 — Weak agreement.** Spearman(Jev `p_a`, price) is between 0.2 and 0.5. *Mechanism:* team-reputation priors from
  training; Jev cannot know 2026 form, injuries or lineups.
- **G2 — No better than a coin flip.** Jev's Brier CI includes 0.25.
- **G3 — The market beats Jev.** Brier(Jev) − Brier(market) > 0. *Falsified if* the paired CI includes 0 with the
  point estimate ≤ 0. *Power caveat:* see below.
- **G4 — The cutoff test of the "ether" idea.** If Jev's Brier CI lies entirely below 0.25, Jev is sensing
  outcome-relevant structure without current information. I predict it will not (G2); G4 is where the idea is
  tested.
- **G5 — Framing bias.** The mean |P(A wins) − (1 − P(B wins))| is at least 0.05 for Jev.
- **G6 — Confidence.** Spread vs |p_a − outcome|: no prediction; reported, as the game-outcome version of C-001's M3.

## Power, stated before any data

Games priced 0.35-0.65 give a market Brier near 0.24, so near-coin-flip Briers differ by about 0.01. With 100-140
games over the week:
- a Jev edge over the coin flip is detectable only if it is large;
- Jev vs the market will almost certainly stay inside the CI.

**If n < 80, counts are reported, not verdicts.** Winner-picking counts are descriptive only.
