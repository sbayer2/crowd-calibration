# Pre-registered plan — experiment 9: NHL live — crowd or book, and what is Jev agreeing with?

Written 2026-10-06, opening night of the NHL season, before the first game starts. Code: `nhl_live.py`. Scheduler:
`~/Library/LaunchAgents/com.sbayer2.crowd-calibration.nhl.plist`, every 5 minutes.

## Questions
1. **Crowd or book.** In sports, is Polymarket's price its own crowd's judgement, or largely the sportsbook line
   relayed by paid market makers? (Background: the research summary of 2026-10-06. Polymarket pays liquidity
   providers to quote near the midpoint; practitioners say sports quotes are copied from Pinnacle. No study measures
   the share.)
2. **What Jev agrees with.** Jev's answers correlate with Polymarket at about +0.6 (T-001, S-001). Is that agreement
   with the crowd, with the book, or with the reputational prior both start from?

## Data, collected going forward
- **Pinnacle and Matchbook moneylines** (The Odds API, free tier; no history available) at three moments:
  - **early:** once a day, the first tick after 14:00 UTC;
  - **T−60:** 45-70 min before each start-time slot;
  - **T−5:** 1-12 min before.
- **No-vig Pinnacle probability:** p = (1/odds) / Σ(1/odds) over the two teams.
- **Polymarket:** the moneyline matched by team names and start (±3 h). Its 1-minute price history is fetched after the
  games and read at each snapshot's time. The result comes from Polymarket's resolution.
- **Jev:** blind, once per game before it starts. It is told "NHL", "Away vs. Home" (full team names) and the date.
  Two configs from experiment 8: `noul_both`, and `bins_plain` (5-bin likelihood per team, plain wording). One fresh,
  stateless request each.
- **Orientation:** every probability is for the away team, the first-listed side as on Polymarket.

**Sample and stop rule.** All NHL games from 2026-10-06 until 2026-11-05, or until credits run out (guard: at most 16
calls a day, none below 25 credits left). Expected about 400 games. A dated interim count may be logged; claims only
at the end. Games are dropped (and counted) if any of these is missing: a Pinnacle T−5 price, a unique Polymarket
match, a Polymarket price within 10 minutes before the T−5 snapshot time, or a clean result.

## Measures and predictions

**Crowd or book.**
- **C1.** At T−5, Polymarket and Pinnacle (no-vig) agree at rank correlation ≥ 0.95, and mean absolute difference
  ≤ 0.03. Both are sharp, so this is expected either way. It is a calibration check, not evidence of copying.
- **C2. Polymarket adds nothing to Pinnacle at the close.**
  - Method: an out-of-fold logistic model of the result (5 chronological folds) on logit(Pinnacle T−5), with and
    without logit(Polymarket T−5).
  - Prediction: the log-loss difference has a 95% bootstrap CI that includes 0.
  - Mechanism: market makers anchor to the book.
  - Polymarket improving the fit would be evidence of crowd information beyond the book.
- **C3. Polymarket moves toward Pinnacle, not the reverse.**
  - Sample: games where |Polymarket − Pinnacle| ≥ 0.03 at T−60.
  - Measure: how much of that gap each closes by T−5, in signed moves toward the other's T−60 price.
  - Prediction: Polymarket closes more of the gap than Pinnacle (paired bootstrap CI excluding 0).
  - Reported as descriptive if fewer than 30 such games occur.

**What Jev agrees with.**
- **J1. Jev sides with neither.**
  - Partial rank correlations at T−5: ρ(Jev, Polymarket | Pinnacle) and ρ(Jev, Pinnacle | Polymarket).
  - Prediction: both lie within ±0.10.
  - Mechanism: their differences are game-day information and flow, which Jev cannot see.
- **J2. Jev is closer to the early line than the close.**
  - Prediction: ρ(Jev, Pinnacle early) ≥ ρ(Jev, Pinnacle T−5) and ≥ ρ(Jev, Polymarket T−5).
  - Mechanism: the early line is mostly a strength rating; the close adds news.
  - Paired bootstrap CI reported. The effect may be small; a CI including 0 is a null, not support.
- **J3. Jev trails both.** Jev's AUC is below both Pinnacle's and Polymarket's T−5 AUC. Expected from S-001 (NHL Jev
  AUC 0.53-0.54, market 0.645).

## What would change the reading
- If C2 shows Polymarket adding information (CI excluding 0 on the improving side), the crowd contributes beyond the
  book.
- If C3 reverses, with Pinnacle moving toward Polymarket, the book is not simply leading.
- If J1 fails, with Jev's partial correlation with one source above 0.10, Jev shares something specific with that
  source. A positive partial with Pinnacle would suggest Jev learned bookmaker-style valuations in pretraining (the B
  question, to test on pre-cutoff soccer).

## Limits, stated up front
- Two pre-game snapshots cannot resolve minute-by-minute lead-lag.
- Pinnacle odds via The Odds API come "from public website which may incur a delay". The snapshot time is when the call
  was made, not when Pinnacle last moved; each record keeps the bookmaker's `last_update`.
- Polymarket's displayed price is the midpoint, or the last trade if the spread exceeds 10¢.
- Snapshots need the Mac awake. Missed windows are logged, not filled.
