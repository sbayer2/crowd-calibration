# Pre-registered plan — experiment 13: NCAA football spreads and totals three days out — book, exchanges and blind Jev

Written 2026-10-18 and approved by the user at about 16:20 CDT, before any spread or total was collected. The first
snapshot is due Wednesday 2026-10-21 at 11:00 CDT.

## Questions
1. **Do the prediction markets price the line like the book?** Three days before kickoff, do Kalshi's and Polymarket's
   spread and total lines match Pinnacle's?
2. **How much of a spread or total can a blind model reproduce?** Experiments 7, 8 and 11 found that blind Jev
   expresses a reputational prior. A point spread is close to a pure strength gap, so it should carry that prior
   well. A total depends more on style and this season's pace, so it should carry it poorly.
3. **Accuracy.** Against the final score, how far off is each source, and does Jev's disagreement with the book
   point to the side that covers?

## Games
- Every Saturday game in experiment 12's scope (`docs/PREDICTIONS-NCAAF.md`, amendment of 10-18): an AP Top 25 team,
  Saturdays 10-24 to 12-05.
- The poll used is the one current at the snapshot: the poll released the Sunday before. Experiment 12 freezes its
  poll on Saturday morning; the two are normally the same. Any game in one scope but not the other is listed.
- Expected n: about 20 a Saturday, so about 140 games.

## Snapshot: once per game, about three days out
- **When:** the first tick at or after **Wednesday 11:00 CDT (16:00 UTC)** before each Saturday. That is 72 hours before
  the 11:00 kickoffs and up to about 83 hours before the latest ones. Each game's lead time is recorded.
- **If missed:** the snapshot is taken at the next tick, up to Thursday 11:00 CDT, and flagged as late. After that the
  week is recorded as missed.
- **Every source is read at the same moment**, so no source is fresher than another:
  - **Pinnacle** (The Odds API, `americanfootball_ncaaf`, markets `spreads,totals`, region eu, Pinnacle and
    Matchbook): each team's spread point and price, and the total point with the over and under prices. One call
    covers every game: **2 credits a week, about 14 in all.** The experiment 12 credit guard and NHL reserve apply.
  - **Kalshi** (public API, no account): series `KXNCAAFSPREAD` and `KXNCAAFTOTAL`; every rung's yes bid and ask.
  - **Polymarket** (public Gamma API): the `spreads` and `totals` markets of each `cfb` event; every rung's best bid and
    ask.
  - **Jev** (see below).

## Turning each source into one line
Sign convention: **margin = away score − home score.** A Pinnacle line of home −7.5 is a margin line of −7.5.

- **Pinnacle:** the listed point. The no-vig probability of each side covering is also stored.
- **Kalshi and Polymarket ladders:** each rung is a yes/no market, such as "Team A wins by over 7.5" or "Over 52.5
  points".
  1. **Usable rungs:** a bid and an ask both present, with ask − bid ≤ 0.10. The rung's price is the midpoint.
  2. **Spreads:** every rung is converted to P(margin > x). "Home wins by over 7.5" becomes P(margin > −7.5) =
     1 − mid.
  3. **Consistent order:** the probabilities are forced to fall as x rises (pool-adjacent-violators, equal weights).
  4. **The line** is the x where the fitted probability crosses 0.5, by linear interpolation between neighbouring
     rungs.
  5. **Unusable ladder:** fewer than 3 usable rungs, or no usable rung on each side of 0.5.
- **"Market" line:** Kalshi's when its ladder is usable, otherwise Polymarket's. Kalshi comes first because its ladders
  were cleaner on 10-18: quoted on both sides and in order. Polymarket's had many empty rungs at a placeholder 0.50,
  and some were out of order. Each exchange is also reported on its own.

## Jev, blind
- **What Jev is told:** "NCAA football game: Away vs. Home, date". No rankings, no records, no lines. One fresh,
  stateless request per game, taken at the snapshot time.
- **Margin question** (Score, 8 ordered levels): "Which team wins this game, and by how many points?" The levels are:
  {away} by 21 or more · {away} by 14-20 · {away} by 7-13 · {away} by 1-6 · {home} by 1-6 · {home} by 7-13 ·
  {home} by 14-20 · {home} by 21 or more.
- **Total question** (Score, 7 ordered levels): "How many points will the two teams score in total?" The levels are:
  under 35 · 35-41 · 42-48 · 49-55 · 56-62 · 63-69 · 70 or more.
- **Jev's line:**
  - **Primary:** the median of its distribution, interpolated within the bin that contains it. The open-ended bins are
    taken as 21-35 points for the margin and 25-35 and 70-85 for the total.
  - **Secondary:** the expected value, using bin midpoints and ±28, 30 and 77.5 for the open-ended bins.
- **Home team:** Jev is not told which team is at home, only the "Away vs. Home" order. S-001 found it cannot infer
  home field from that, so its margin carries no home edge.

## Outcome
- The final score from ESPN's public scoreboard, fetched after each Saturday. Overtime counts.
- A postponed or cancelled game is dropped, under the 10-17 postponed-game rule.

## Matching across sources
- The Odds API's full team names are the reference.
- Polymarket is matched with `team_in`, as in `collect-poly`.
- Kalshi uses short names ("Georgia St."). A fixed alias table expands "St." to "State" and adds known cases.
- A game that matches no rung set in a source counts as missing for that source. Hand matches are recorded in this
  file.

## Measures and predictions
**Markets against the book** (paired by game):
- **S1.** Kalshi's spread line agrees with Pinnacle's: mean absolute difference ≤ 1.0 point, Pearson r ≥ 0.97.
  Polymarket: mean absolute difference ≤ 2.0 (thin ladders).
  - Mechanism: exchange market makers quote off the books.
- **S2.** Kalshi's total agrees with Pinnacle's: mean absolute difference ≤ 1.5 points. Polymarket: ≤ 2.5.

**Accuracy against the final score:**
- **S3.** Pinnacle's and the market's spread mean absolute errors are within 0.5 points of each other: the paired
  bootstrap CI of the difference includes 0. Both are expected around 12-14 points.
- **S4.** Jev's spread mean absolute error is worse than Pinnacle's by at least 1.5 points, with the paired CI
  excluding 0.

**What Jev reproduces:**
- **J5.** Pearson r(Jev margin, Pinnacle spread line) ≥ 0.60.
  - Mechanism: in college football the strength gaps (a Top 10 team against an unranked one) are large and carried by
    programme reputation, which Jev knows.
  - Experiment 8's moneyline agreement in the NFL was +0.59; spreads in this sport should be at least as easy.
- **J6.** Pearson r(Jev total, Pinnacle total) ≤ 0.40, and below the J5 value (paired bootstrap of the difference).
  - Mechanism: totals depend on this season's offences, defences and pace, which a pre-2025 reputation carries
    poorly.
- **J7.** Jev's lines are compressed: SD(Jev margin) < SD(Pinnacle line), and likewise for totals.
- **J8.** Jev gives no edge against the book. When Jev's margin is on one side of Pinnacle's line, that side covers
  at a rate whose 95% CI includes 50%. The same for over/under. The rate is reported with its CI, for all games and
  for games where Jev differs from the line by 7 points or more.

## What would change the reading
- **S1 failing** (Kalshi off the book by more than a point on average) would mean three-day-out exchange lines are not
  simply relayed book lines, the reverse of what experiments 9-12 are testing at the close.
- **J5 failing** would mean Jev's reputational prior does not reach the size of a strength gap.
- **J6 failing** (Jev's totals tracking Pinnacle's at r > 0.40) would mean Jev knows teams' scoring styles, not only
  their strength.
- **J8 failing** with a cover rate above 50% would be the first evidence in this repo that Jev's disagreement with a
  sharp source has value. It would need replication before any claim.

## Sample and power
- About 140 games.
- The SD of a college football spread's error against the result is about 15-17 points. The paired SE of a
  difference in mean absolute error is therefore well under a point, so S3 and S4 are adequately powered.
- A correlation at n = 140 has an SE of about 0.06-0.08.
- J8: a 50% cover rate at n = 140 has a 95% CI of about ±8 points, so only a large edge would show.

## Limits, stated up front
- One snapshot per game, so no line movement. The three-day line is not the closing line.
- Pinnacle via The Odds API may lag Pinnacle's own site. The snapshot keeps each bookmaker's `last_update`.
- Kalshi and Polymarket ladders three days out are thin. A ladder line is an estimate whose quality depends on quoting.
  The share of usable ladders is reported.
- Jev is not told home field; Pinnacle prices it. Part of any Jev-Pinnacle gap is home advantage by construction. A
  secondary analysis adds a constant home term fitted out of fold, and reports it.

## Code (written after this plan is committed, before Wednesday's snapshot)
- `live_odds.py`: a `t72` snapshot type for the NCAA football arm, plus a `collect-scores` command (ESPN finals).
- `ladders.py` (new): reads the Kalshi and Polymarket ladders and computes the line.
- Jev questions alongside the existing ones (`sports_jev.py` pattern). Records go to `runs/ncaaf/t72.jsonl`.
- Analysis: written before 12-05, run once at the end.
