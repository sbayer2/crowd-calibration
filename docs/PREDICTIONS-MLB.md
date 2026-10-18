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

## Amendment 2026-10-07, 15:57 CDT (operational, no change to collection rules or measures)
- The MLB T−5 snapshot for Guardians @ White Sox (20:00 UTC) was missed. The Mac was awake, but no tick completed or logged in the
  window (19:48-19:59 UTC): either timer delays or a tick stalled on the failing hotspot DNS. Recorded as missed.
- From now on both LaunchAgents run every 2 minutes, not 5, giving 5-6 attempts per window. Each run writes a line to
  `runs/<sport>/heartbeat.log`, so gaps can be diagnosed.
- The snapshot windows (T−60: 45-70 min; T−5: 1-12 min) are unchanged.

## Amendment 2026-10-13, 19:04 CDT (operational)
- The shared guard's daily cap rose from 16 to 24 calls per sport per UTC day. See the same-dated amendment in
  `docs/PREDICTIONS-NHL.md`. No MLB snapshot was affected.

## Amendment 2026-10-17, 09:50 CDT (drop rule for postponed games; written before the rescheduled game's result)
**Case.** ALCS Game 4, Rays @ Guardians (Odds API id `b9d2e07c`), listed for Fri 16 Oct 17:00 CDT.
- **What happened:** the start was pushed to 19:00, 19:30, 20:10 and then 20:40 CDT. The game had left the Odds API
  feed by 20:29.
- **Polymarket:** the market (`mlb-tb-cle-2026-10-16`) now reads "originally scheduled for 6:00 PM ET on October 16,
  2026 ... rescheduled to October 17, 2026 at 8:00 PM ET". Its price stayed at 0.495-0.515 from 18:00 Friday to 08:30
  Saturday, so the game did not finish.
- **Odds API:** it lists the rescheduled game under a new id (`bf41baae`) for Sat 17 Oct 19:00 CDT. Jev was asked
  about it at the 17 Oct early snapshot.
- **Game 5:** moved to Sun 18 Oct, 17:00 ET.

**Rule (applies equally to experiments 9 and 12):**
1. **Postponed listing:** dropped and counted as "postponed", with its snapshots and its Jev answer. A postponed
   listing is one whose game did not start on the listed date.
2. **Rescheduled game:** an ordinary game under its own listing. Its early snapshot, Jev answer, T−60 and T−5 are the
   ones taken for the new start. If the Odds API keeps the old id, only snapshots and a Jev answer taken after the
   listed start moved by more than 6 hours count.
3. **Suspended game** (it started, then finished on a later day): kept under its original listing. Its pre-game T−5
   and its final result stand.
4. **Polymarket matching:** a rescheduled game is matched to the market whose description names that game, here Game 4
   = `mlb-tb-cle-2026-10-16`. Start-time proximity alone does not decide the match. When `collect-poly` finds more
   than one candidate, the match is made by hand and recorded in this file.
5. **Before the analysis:** postponed versus suspended is checked against MLB's official game log. The Polymarket
   description is not the final word.

**Effect:** `b9d2e07c` is dropped as postponed, and MLB finished games go from 14 to 13. The rescheduled Game 4 is
collected tonight as `bf41baae`.

## Amendment 2026-10-18, 14:00 CDT (operational: credit guard)
- The guard now reads the credits left on the shared key from the newest snapshot of any sport, not from this arm's own
  last call, which could be hours old. The floor (25) and the daily cap (24) are unchanged.
- Until 11-06, the NCAA football arm also leaves 12 credits a day for this arm and the other arm. See the same-dated
  amendment in `docs/PREDICTIONS-NCAAF.md`.
