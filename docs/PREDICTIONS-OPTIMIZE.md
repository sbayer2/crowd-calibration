# Pre-registered plan — experiment 6: searching how Jev is asked

Written 2026-10-05, before any search run. Code: `braves_opt.py`.

**Purpose (the user's framing).** The outcome is not whether Jev can beat Polymarket. It is how the *architecture of the
query* (question type, instructions, criteria, state) changes Jev's prediction of a real-world event. In emoji-pile,
changing the task and questions visibly changed the sort; here there is a right answer to measure against. Polymarket's
pre-game picks are treated as the practical ceiling for this sample.

**Already seen.** All 172 outcomes and market prices of the 2026 Braves season (Mar 20 - Oct 5). Experiment 5 (B-001)
ran seven prompt variants on 41 games and V3 (7-bin Score) on the other 131. None beat a coin flip on tuning; V3 on the
hold-out picked 78/131, the same as always picking the Braves.

**Inputs.** Jev sees only the matchup as Polymarket lists it, plus (depending on `state`) the start time and date. No
price, result, record, pitchers or injuries.

**Search space.** 5 question types x 6 instruction wordings x 3 criteria variants x 3 state shapes = 270 configs
(definitions in `braves_opt.py`). Each config turns Jev's answers into one number per game; the pick is "Braves" when
that number is at or above a cut-off fitted on the other three time blocks.

**Independence.** Every evaluation is a fresh pass over all 172 games. Each request is stateless: no cache, no uid, no
session. Jev never sees another game, an earlier answer, a score or an iteration; only the search uses scores.

**Search.** 20 random configs, then 200 iterations, each changing one setting of a top-5 config (75%) or crossing two
(25%). 220 distinct configs in total. Any config entering the top 5 is re-run with fresh calls until it has 3 runs, and
is ranked on the mean.

**Target ("consistent", option a, chosen by the user).** In each of four chronological blocks of 43 games, Jev's pick
accuracy is at least the market's: 69.8 / 58.1 / 58.1 / 53.5%. Fitness = the worst block's margin over the market
(ties: overall accuracy).

**Reference points, computed before the run.**

| | Blocks | Worst-block margin |
|---|---|---|
| Polymarket, picks at 50% (the target) | 70 / 58 / 58 / 53% | 0 |
| Always pick the Braves | 70 / 53 / 58 / 53% | -4.7 |
| Polymarket's own price, cut-off fitted the same way as Jev's | 70 / 49 / 58 / 53% | -9.3 |

The last row shows what the fitted cut-off costs a forecaster that has real information.

**Reported.**
- Leaderboard.
- Per-setting means: overall accuracy, margin, rank correlation with market price, rank correlation with outcome, share
  of Braves picks.
- Run-to-run rank agreement of repeated configs.
- Null control: every config re-scored against 200 shufflings of win/loss, giving the best margin luck alone reaches.

**Predictions.**
- **O1. No config is consistent** (margin >= 0). Mechanism: the state carries no 2026 information, so the query can
  only re-express Jev's priors about the clubs.
- **O2. The best config does not clear the null.** Its margin is not above the 95th percentile of the shuffled-outcome
  best.
- **O3. Query architecture moves the numbers more than the order.**
  - The question type explains more of the differences in Braves-pick share, and in rank correlation with the market,
    than wording, criteria or state do.
  - Within each of wording, criteria and state, the per-value means of rank correlation with the market differ by less
    than 0.15.
- **O4. Jev's order tracks the market's.** At least 80% of configs have a positive rank correlation with market price.
  Mechanism: team-reputation priors, as in C-001 and experiment 5.
- **O5. Jev's order does not track the outcomes.** The mean rank correlation with the outcome across configs is within
  ±0.05 of 0.
- **O6. Repeated runs agree more with each other than with the market.** The mean rank correlation between repeated
  runs of the same config is higher than the mean correlation with the market.

**What would change the reading.**
- If O1 or O2 fails, some way of asking extracts outcome-relevant structure from the matchup alone. That config gets a
  fresh 3-run confirmation before any claim.
- If O3 fails, wording, criteria or state matter as much as the question type: the emoji-pile pattern holds here too.
