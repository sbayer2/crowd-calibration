# Pre-registered plan — experiment 10: MLB postseason live — crowd or book, and what Jev agrees with

Written 2026-10-07, about 07:15 CDT, before the first collected game (Guardians @ White Sox, ALDS, 20:00 UTC). Code:
`live_odds.py --sport mlb` (the experiment 9 collector, given a sport setting). Scheduler:
`~/Library/LaunchAgents/com.sbayer2.crowd-calibration.mlb.plist`.

## Design
The same as experiment 9 (`docs/PREDICTIONS-NHL.md`), with these differences:
- **Games:** every MLB postseason game from the Division Series (in play on 2026-10-07) through the last World Series
  game.
- **Jev:** told "MLB", "Away vs. Home" (full team names) and the date. Two configs: `noul_both` and `bins_plain`.
- **Polymarket matching:** tags `mlb` (scanned by date window) and `mlb-playoffs` (read whole).
- **Same in both arms:** snapshot moments, no-vig method, drop rules, measures, and the shared credit guard.

## Sample: a pilot, stated up front
The postseason yields about 30-45 games, too few to settle C2, C3 or J1 on their own; a partial correlation at n = 40
has an SE of about 0.16.
- **Primary MLB report:** descriptive. The same tables as experiment 9, with CIs, and no verdicts.
- **Secondary, pre-registered:** NHL and MLB pooled for C2 and J1, with sport as a fixed effect: a sport indicator in
  the logistic model, and partial correlations computed within sport, then combined with weights proportional to
  games.

## Predictions (direction as in experiment 9)
- **C1.** Polymarket and Pinnacle agree at T−5: rank correlation ≥ 0.95, mean absolute difference ≤ 0.03.
- **C2.** Adding Polymarket to Pinnacle does not improve out-of-fold log loss.
- **C3.** In games with a T−60 gap ≥ 0.03, Polymarket closes more of the gap than Pinnacle. Descriptive below 30 such
  games.
- **J1.** Jev's partial correlations with each source, holding the other fixed, lie within ±0.10. At this n, reported
  with CIs; no verdict.
- **J2.** Jev correlates with Pinnacle's early line at least as much as with either closing price.
- **J3.** Jev's AUC is below both sources'. Context: S-001 found plain-config Jev AUC 0.575 on regular-season MLB.

**Postseason-specific note (descriptive):** MLB playoff games are between strong teams, so Jev's reputational prior has
a compressed range. J2 and J3 may look weaker than in the regular season for that reason alone.

## Credit budget (shared free key)
- About 489 credits for both arms until the monthly reset. Expected use: NHL about 10 a day, MLB about 3-9 a day
  while the postseason runs, total about 400-450.
- The shared guard (no call below 25 credits left) may cut the last days of the NHL window. Any cut is reported, not
  hidden.
