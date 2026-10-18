# Pre-registered plan — experiment 12: NCAA football Top 25 live — crowd or book, and what Jev agrees with

Written 2026-10-10, about 12:40 CDT. The first collected kickoffs are at 14:30 CDT (19:30 UTC); the games that began
at 11:00 CDT today are not collected. Code: `live_odds.py --sport ncaaf` (the experiment 9 collector). Scheduler:
`~/Library/LaunchAgents/com.sbayer2.crowd-calibration.ncaaf.plist`.

## Design
The same as experiment 9 (`docs/PREDICTIONS-NHL.md`), with these differences:
- **Games:** every game on Saturday 2026-10-10 and Saturday 2026-10-17 (US Central date) in which at least one team is
  in the AP Top 25.
  - The poll is read from ESPN's public rankings feed (`site.api.espn.com/.../college-football/rankings`) and frozen
    the first time a tick runs on each Saturday: the Week 6 poll for 10-10, the Week 7 poll for 10-17.
  - Matching is on the full team name used by The Odds API.
  - On 10-10, the six ranked teams without a listed game (BYU, Iowa, Miami, Mississippi State, SMU, Texas Tech) were
    checked against ESPN's scoreboard: none plays today.
- **Expected n:** 12 games on 10-10, and about 15-20 on 10-17.
- **Jev:** told "NCAA football", "Away vs. Home" (full team names) and the date. It is not told the rankings. Two
  configs: `noul_both` and `bins_plain`, one fresh, stateless request each. Each Jev record also stores both teams' AP
  ranks, for analysis only.
- **Odds:** Pinnacle and Matchbook moneylines (The Odds API `americanfootball_ncaaf`, region eu); no-vig as in
  experiment 9.
- **Polymarket matching:** tag `cfb`. Polymarket lists games as "Away vs. Home" with short names; a match requires both
  names inside The Odds API's full names and a start within ±3 h.
- **Snapshot moments:** unchanged (early, T−60: 45-70 min, T−5: 1-12 min). One deviation on 10-10: the early snapshot
  is taken at arming time (about 12:45 CDT), not 09:00.
- **Neutral sites:** Texas vs. Oklahoma (10-10) is played in Dallas, but The Odds API lists Oklahoma as home. The
  listing is kept as given. Neutral-site games are flagged in the analysis, not dropped.

## Sample: a pilot, stated up front
About 25-35 games: descriptive only. College football has much wider strength gaps than NHL or MLB, so prices spread
from about 0.05 to 0.95. That makes rank correlations easy to reach and AUCs high for everyone.
- **Primary report:** the experiment 9 tables with CIs, and no verdicts.
- **Secondary, pre-registered:** pooled with NHL and MLB for C2 and J1, with sport as a fixed effect, as in
  experiment 10.

## Predictions (direction as in experiment 9)
- **C1.** At T−5, Polymarket and Pinnacle agree: rank correlation ≥ 0.95, mean absolute difference ≤ 0.03.
- **C2.** Adding Polymarket to Pinnacle does not improve out-of-fold log loss (pooled analysis).
- **C3.** In games with a T−60 gap ≥ 0.03, Polymarket closes more of the gap than Pinnacle. Descriptive at this n.
- **J1.** Jev's partial correlations with each source, holding the other fixed, lie within ±0.10. Reported with CIs.
- **J2.** Jev correlates with Pinnacle's early line at least as much as with either closing price.
- **J3.** Jev's AUC is below both sources'.
- **J4 (new, sport-specific).** Jev's rank correlation with Pinnacle at T−5 is higher here than in the NHL arm.
  - Mechanism: the reputational prior Jev holds for programmes like Alabama, Ohio State or Texas carries more of the
    outcome when the strength gaps are large.
  - What would disprove it: an NCAAF ρ at or below the NHL ρ.

## Credit budget (shared free key)
About 444 credits left at arming. This arm uses about 13 credits on 10-10 (early, then T−60 and T−5 for 6 kickoff
slots) and about 15-17 on 10-17: about 30 in all. The NHL arm's projected use through 2026-11-05 still fits. The
shared guard still applies: at most 16 calls per sport per UTC day, none below 25 credits left.

## Operations
- The Mac must be awake through the last T−5 (about 21:25 CDT on 10-10).
- On 10-17, a new `caffeinate` must cover about 09:00-22:00 CDT.
- The LaunchAgent is unloaded after the 10-17 games resolve.

## Amendment 2026-10-10, 19:20 CDT (operational, no change to the snapshot windows or measures)
- LSU @ Kentucky moved its kickoff from 23:00 to 23:10 UTC after its T−60 snapshot. The collector read the schedule
  only hourly, so it took the "T−5" for 23:00 at 22:48, 22 minutes before the real kickoff. The game has no snapshot
  in the T−5 window and is recorded as missed.
- From now on, all three arms update a game's start time from every odds snapshot, so a moved kickoff gets its own
  T−5 window. This costs an extra credit when the move creates a new slot.
- Stanford @ Notre Dame and Maryland @ Ohio State had no Pinnacle moneyline at any snapshot and are dropped by the
  existing rule.

## Amendment 2026-10-13, 19:04 CDT (operational)
- The shared guard's daily cap rose from 16 to 24 calls per sport per UTC day (the "16 calls" above now reads 24).
  See the same-dated amendment in `docs/PREDICTIONS-NHL.md`. The 2026-10-10 slate never reached the cap.

## Amendment 2026-10-17, 09:50 CDT (drop rule for postponed games)
- A postponed game's original listing is dropped and counted. The rescheduled game counts under its new start. A
  suspended game keeps its original listing. Full rule: the same-dated amendment in `docs/PREDICTIONS-MLB.md`. No
  NCAAF game has been postponed so far.

## Amendment 2026-10-18, 08:30 CDT (Polymarket name matching; written after the game's result was known)
- **Case.** Florida State @ Miami (10-17, Odds API id `33f259d8`) did not match its Polymarket market
  (`cfb-flst-mia-2026-10-17`, market 5353447). Polymarket's outcome name is "Miami (FL)", which is not a substring of
  the Odds API name "Miami Hurricanes", so `collect-poly` found 0 candidates.
- **Fix.** The matcher now also accepts an outcome name with a trailing two-letter state tag removed ("Miami (FL)" ->
  "Miami"). The other conditions are unchanged: start within 3 hours, both teams in away/home order, and exactly one
  candidate, otherwise no match. The rule is general and is in the code (`team_in` in `live_odds.py`); it applies to
  all three arms. NHL and MLB names carry no state tags, and games that already matched are not retried, so no existing
  match changes.
- **Effect.** The game matched (closed, Miami won). The 10-17 slate has 16 of 16 games with a Polymarket result. The
  result is Polymarket's own resolution, not anything this fix chose, but the fix was written after it was known and is
  reported as such.

## Amendment 2026-10-18, 10:30 CDT (operational)
- The plan says the LaunchAgent is unloaded after the 10-17 games resolve. By the user's decision it is left running.
  With no listed Saturday ahead it collects no games and spends no credits (last snapshot 10-18 02:19 UTC). No data
  changes.
