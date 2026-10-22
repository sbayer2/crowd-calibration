# Pre-registered plan — experiment 14: NBA moneylines from free sources — two exchanges and blind Jev

Written 2026-10-22 and approved by the user at about 9:58 CDT, before any NBA price or Jev answer was collected. No Odds
API credits are used.

## Why
- **Budget.** A Pinnacle arm like the NHL one would cost about 10 credits a night. The free key's remaining credits are
  committed to experiments 9, 10, 12 and 13 (ADC-007, ADC-015). This arm uses only free, public sources.
- **A fourth sport.** Experiments 9, 10 and 12 test Jev against the crowd in hockey, baseball and college football.
  S-001 found that how far blind Jev tracks the market depends on the sport (rank correlation +0.12 in NHL to +0.64 in
  MLB; NBA +0.23). The NBA adds a sport where outcomes turn on current form, rest and injuries, which Jev cannot see.

## Questions
1. **Do the two exchanges agree at the close?** Polymarket and Kalshi both list every NBA game. Does either add
   anything to the other in predicting the result?
2. **How much of an NBA game can blind Jev reproduce?** And does it reproduce the early price better than the close?
3. **Across sports:** is Jev's agreement with the closing crowd lower in the NBA than in college football?

## Games
- Every NBA game in ESPN's schedule from the first game day after this arm's code is committed through 2026-12-05
  (the end of experiment 12). Regular season, NBA Cup group games included. Days run on US Central time.
- Expected n: about 7 games a day for about 40 days, so **about 280 games**.

## Data
- **Schedule, start time and result:** ESPN's public scoreboard (`basketball/nba`). The start is ESPN's scheduled
  time, read at the last schedule refresh before it. Overtime counts. Postponed games are dropped under the 10-17 rule.
- **Polymarket:** the moneyline of each `nba` event, matched by team names and start (±3 h), as in `collect-poly`.
  Outcomes are [away, home]. Its 1-minute price history is fetched after the games.
- **Kalshi** (public API, no account): series `KXNBAGAME`, the away team's market, matched by team names and date. Its
  1-minute candlesticks (yes bid and yes ask at each minute's close) are fetched after the games. The home team's
  market is kept as a check.
- **Jev:** blind, once per game before it starts. It is told "NBA", "Away vs. Home" (ESPN's full team names) and the
  date. The two configs of experiments 9-12, `noul_both` and `bins_plain`. One fresh, stateless request each. An answer
  is valid only if it was received before the start.
- **Orientation:** every probability is for the away team.

## Prices at each moment
- **Moments:** early = 14:00 UTC on the game day; T−60 = 60 minutes before the start; T−5 = 5 minutes before.
- **Polymarket:** the last history point at or before the moment, at most 10 minutes old (as in experiment 9).
- **Kalshi:** the midpoint of the yes bid and ask at the last minute at or before the moment, at most 10 minutes old,
  usable only if ask − bid ≤ 0.10. Otherwise Kalshi has no price at that moment.
- Because both histories are fetched after the games, the moments are exact: no source depends on the Mac being awake
  at a given minute. Only Jev's answer does.

## Drops (counted by reason, in this order)
Postponed; no Jev answer before the start; no unique Polymarket match; no Polymarket price at T−5; no clean result
(ESPN final, with Polymarket's resolution agreeing). A game without a usable Kalshi price at T−5 stays in the sample
but leaves the Kalshi measures.

## Measures and predictions
Verdicts need at least 100 usable games (as in experiment 12); below that, counts only.

**The two exchanges.**
- **E1. They agree at T−5:** rank correlation ≥ 0.95 and mean absolute difference ≤ 0.02.
  - Mechanism: arbitrage between the venues, and market makers on both quoting off the books.
- **E2. Kalshi adds nothing to Polymarket at the close.** Out-of-fold logistic model of the result (5 chronological
  folds) on logit(Polymarket T−5), with and without logit(Kalshi T−5). Prediction: the log-loss difference has a 95%
  bootstrap CI that includes 0. The reverse (Polymarket added to Kalshi) is reported too.
- **E3. Who moves (descriptive, no prediction).** In games where the two differ by ≥ 0.03 at T−60, the share of the gap
  each closes by T−5. No prediction: both venues trade NBA games heavily (Kalshi's 10-21 games settled with 1-3
  million contracts each), and there is no prior result to predict from.

**Blind Jev.**
- **N1. Jev trails the crowd:** Jev's AUC is below Polymarket's T−5 AUC, with the paired bootstrap CI of the difference
  excluding 0. Expected from S-001: Jev about 0.57-0.58, the market well above.
- **N2. Jev is closer to the early price than to the close:** ρ(Jev, Polymarket early) ≥ ρ(Jev, Polymarket T−5),
  paired bootstrap CI reported. Mechanism as in experiment 9's J2: the early price is mostly a strength rating, the
  close adds injury and rest news. A CI including 0 is a null, not support.
- **N3. Weak agreement:** ρ(Jev, Polymarket T−5) is above 0 and at most 0.45, for each config. S-001's NBA value was
  +0.23 to +0.26. Rosters have changed since Jev's training data, so the value may be lower still.
- **Home edge (descriptive):** Jev's mean away probability, Polymarket's, and the share of away wins.

**Across sports.**
- **X6. Jev agrees less with the closing crowd in the NBA than in college football:** ρ(Jev, Polymarket T−5) in
  experiment 12's NCAA football games minus the same in this NBA sample, per config. Prediction: the difference is
  positive, with a 95% bootstrap CI (games resampled within each sport) excluding 0.
  - Mechanism: college football's strength gaps are large and follow programme reputation, which Jev knows; NBA
    strength shifts with rosters and form.
  - Needs at least 100 usable games in each sport. NHL and MLB values are reported alongside, without a prediction.
  - The same quantity for NHL, MLB and NCAA football comes from `analyze_live.py` at the end, so it is not computed
    early (ADC-013).

## What would change the reading
- **E2 failing** (Kalshi improving on Polymarket, or the reverse) would mean the two exchanges price NBA games
  differently, and the better one carries information the other lacks.
- **N2 reversed,** with Jev closer to the close than to the early price, would suggest Jev's prior reflects more than
  reputation.
- **X6 failing** (no sport difference) would mean Jev's agreement with the crowd is about equal across sports, against
  S-001's spread.

## Limits, stated up front
- No sportsbook line, so no crowd-or-book test (experiment 9's C1-C3). The exchanges are compared only with each
  other and with the result.
- Kalshi's quoted bid and ask are read from 1-minute candles, not the order book; a price can be up to a minute stale.
- ESPN's start is the scheduled tip-off; the actual tip is a few minutes later, so T−5 is at least 5 minutes before.
- Jev needs the Mac awake and online before each start. Missed Jev answers are counted, not filled.

## Code (written after this plan is approved, before the first game)
- A new module, `nba_free.py`: a `tick` (refresh the ESPN schedule; ask Jev for games starting within the next few
  hours) and a `collect` (Polymarket and Kalshi histories, results). Data in `runs/nba/`.
- A fourth LaunchAgent, `com.sbayer2.crowd-calibration.nba`, every 2 minutes. It never calls the Odds API.
- Analysis in `analyze_live.py` or a sibling script, tested on synthetic data, run on real data only as counts until
  12-05 (ADC-013).

## Amendment 2026-10-22, 10:05 CDT (implementation; written before any NBA price was read for analysis)
- **Start of the sample: 2026-10-22.** The LaunchAgent first ran at 10:02 CDT and asked Jev about that night's two
  games (Cleveland @ Philadelphia, Denver @ Oklahoma City) well before tip-off, so they are included.
- **Collector:** `nba_free.py`. Its tick refreshes the ESPN schedule hourly (Central today and tomorrow); a start moves
  only on a listing read before it. Jev is asked from 14:00 UTC for games starting within 20 hours and more than 5
  minutes away. The tick also runs `collect` hourly for games that started 3.5 hours to 3 days ago.
- **Kalshi:** matched by both team names and the date in the market rules (one day either side of the Central date).
  Kalshi lists cities; "Los Angeles C" and "Los Angeles L" map to the Clippers and the Lakers. Candles are fetched for
  both teams' markets from 13:45 UTC on the game day to the start. Kalshi omits minutes without activity; the 10-minute
  rule covers the gaps (the longest in a 13-hour test on 10-21 was 7 minutes).
- **Live check (10-21, scratch directory, Jev not called):** all 11 games matched in ESPN, Polymarket and Kalshi, and
  every result agreed with the final score.
- **Analysis:** `analyze_nba.py`, tested on synthetic data (`tests/test_analyze_nba.py`). The choices this plan leaves
  open are fixed in its docstring. On real data it is run only as `counts` until the 12-05 games are final (ADC-013).
