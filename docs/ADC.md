# Architecture Decision Cycle — crowd-calibration

---

## ADC-001 — Public data only, no Polymarket account — DONE

**Decision.** Market questions and prices come from Polymarket's public Gamma API (read-only, no key). Jev runs on
the existing Vercel AI Gateway credit; openjev runs locally.

**Consequences.** Anyone can reproduce the selection, but prices move, so each run is pinned to a frozen snapshot.
The API returns at most 100 markets per page and refuses offsets past a cap (between 2,000 and 5,000); the selector
stops there, having seen 2,100 active markets on 2026-09-30.

---

## ADC-002 — Measure confidence apart from the forecast — DONE

**Context.** The original post asks whether Jev answers "58% with high or low confidence". A noul returns a single
probability, whose only "confidence" is its distance from 0.5.

**Decision.** Also ask a Score question over 7 probability bins. Forecast = the expected bin midpoint; confidence =
the spread of the distribution over bins.

---

## ADC-003 — Contested markets are the primary test; clusters are capped — DONE

**Context.** Most active markets are longshots near 0.2%, which any model gets right. Near-identical questions
(state-by-state data center moratoria, 2028 nominations) would make 30 markets behave like far fewer independent ones.

**Decision.** The primary test uses the 30 contested markets (0.15-0.85). At most 3 markets per event and 3 per
question template (the question with names and numbers removed).

**Consequences.** Near-complementary pairs remain (R vs D Senate control, R vs D 2028), so the effective n is below
30; the write-up says so.

---

## ADC-004 — openjev as the control arm — DONE

**Decision.** openjev 4B v5 (an open Qwen3.5 model with a Jev-like interface) answers the same questions. If it tracks
prices as well as Jev does, the correlation is a general language-model prior, not something specific to Jev.

---

## ADC-005 — Live sports data collected going forward, three sources per game — DONE

**Context.** Experiments 7-8 compared blind Jev with Polymarket. Polymarket's sports prices may be a sportsbook's line
relayed by paid market makers, so "the crowd" may really be the book. The Odds API's free tier has no history.

**Decision.** Collect forward (experiment 9, 2026-10-06): Pinnacle and Matchbook moneylines at early, T−60 and T−5;
Polymarket's 1-minute history and result fetched after the game; blind Jev once per game before the start.

**Consequences.** Samples grow only in real time, and the Mac must be awake for each window. Missed windows are logged,
never filled. Plans: `docs/PREDICTIONS-NHL.md`, `-MLB.md`, `-NCAAF.md`.

---

## ADC-006 — One collector for every sport, one LaunchAgent each, every 2 minutes — DONE

**Decision.** `live_odds.py --sport nhl|mlb|ncaaf` (2026-10-07). Each sport keeps its own state in `runs/<sport>/`.
Ticks run every 2 minutes, not 5, after a missed MLB T−5, and write a heartbeat line so gaps can be diagnosed.

**Consequences.** One code change reaches all arms at the next tick, so changes are tested before saving.

---

## ADC-007 — A shared credit guard on the free key — DONE

**Context.** 500 credits a month, shared by every arm, with an undocumented reset date.

**Decision.** At most 24 odds calls per sport per UTC day (raised from 16 on 10-13, after the cap cost four windows),
and no call below 25 credits left. Since 10-18 the guard reads the credits left from the newest snapshot of any sport,
and until 11-06 the NCAA football arm keeps 12 credits a day in reserve for the NHL arm.

**Consequences.** A cut window is recorded as missed. Experiment 13's 2-credit calls run under the same guard.

---

## ADC-008 — Start times are followed from every snapshot — DONE

**Decision.** Each odds snapshot updates a game's start time (2026-10-10), not only the hourly schedule refresh, after
a moved kickoff lost its T−5.

**Consequences.** A move that creates a new start-time slot costs an extra credit.

---

## ADC-009 — Postponed, rescheduled and suspended games — DONE

**Decision.** A postponed listing is dropped and counted; the rescheduled game counts under its own start; a suspended
game keeps its listing (2026-10-17, after ALCS Game 4 moved). The full rule is in `docs/PREDICTIONS-MLB.md`.

---

## ADC-010 — Polymarket matching: names, start within 3 hours, exactly one candidate — DONE

**Decision.** Both team names inside the Odds API names, in away/home order, with a start within 3 hours. Anything
else is no match. Two later widenings were recorded after the results were known: a trailing state tag may be dropped
("Miami (FL)", 10-18), and open playoff events are read too (ALCS Game 5, 10-19).

**Consequences.** Results come only from Polymarket's own resolution. A match by hand would be recorded in the plan.

---

## ADC-011 — NCAA football: Top 25 Saturdays, pooled with sport as a fixed effect — DONE

**Decision.** Games with an AP Top 25 team, with the poll frozen at each Saturday's first tick (2026-10-10). Extended on
10-18 to every Saturday through 12-05, with bowls excluded. C2 and J1 pool NHL, MLB and NCAA football with a sport
indicator. Verdicts on C1, J3 and J4 require at least 100 usable games.

---

## ADC-012 — Experiment 13: one three-day-out snapshot of every source — DONE

**Decision.** Wednesday 11:00 Central before each Top 25 Saturday (2026-10-18): Pinnacle spreads and totals (2
credits), Kalshi and Polymarket ladders turned into one line each (usable rungs, monotone fit, 0.5 crossing), and blind
Jev Score questions for the margin and the total. Kalshi's line is the market line when usable, otherwise
Polymarket's. Plan: `docs/PREDICTIONS-SPREADS.md`.

**Consequences.** One snapshot means no line movement. Jev is not told home field, so part of any gap with Pinnacle is
home advantage by construction.

---

## ADC-013 — Live analysis code is written before collection closes and tested on synthetic data — DONE

**Context.** Experiments 9, 10, 12 and 13 have collectors but no analysis code. Running analysis code on partial real
data would show results before the plan's end point.

**Decision.** Write the analysis scripts now. Test them on synthetic data in the real file formats; on the real data,
look only at counts (usable games, drop reasons) until collection closes. Commit each script before its first real
run.

**Consequences.** Any bug found at the real run is fixed in a new commit and reported.

**Closed 2026-10-20.** `analyze_live.py` (experiments 9, 10, 12) and `analyze_spreads.py` (experiment 13) are committed,
with synthetic tests in `tests/`. The first real count found that the Odds API rewrites a live game's start time, so
windows are timed against the last pre-game listing; it also surfaced missed windows now recorded in the plans.

---

## ADC-014 — Outcomes that resolve together are resampled together — DONE

**Context.** In experiment 3 the options of one event resolve together: exactly one wins an exclusive event. A
bootstrap over single options treats them as independent and gives intervals that are too narrow. The plan named no
CI, and the clustered interval was chosen at scoring time, after the point estimates were seen (2026-10-20).

**Decision.** When outcomes share a cluster (an event's options; later, perhaps, a game's spread and total), the
bootstrap resamples whole clusters. When that choice is made after seeing results, the unclustered interval is
reported next to it, and the entry says the choice was post hoc.

**Consequences.** K-001 gives both: K1 [+0.072, +0.166] by event and [+0.080, +0.158] by option. K1 holds either way.
`culture.py compare` prints both. Adding the second bootstrap moved the K2 event interval slightly ([+0.101, +0.284]
to [+0.098, +0.283]), because both draw from one seeded generator. Future plans name the resampling unit before the
data come in.

---

## ADC-015 — Experiment 9 will be about half the planned size — DONE (extended to 12-05)

**Context.** The NHL plan expected about 400 games from 10-06 to 11-05. Through 10-19, 97 games were played (about 7 a
day) and 89 were usable (92%). That projects to about 215 games and about 200 usable by 11-05. The 400 overstated the
schedule.

**Decision so far.** The end date and every threshold stay as pre-registered. The README states the projection.

**Consequences.** Every confidence interval will be about 1.4 times wider than planned (√2), so small effects in C1,
C2, J1 and J3 are less likely to be detected. Pooling with MLB and NCAA football for C2 and J1 (ADC-011) recovers some
power.

**Open.** Whether to extend collection past 11-05 is the user's decision. Any extension must be written as a plan
amendment before any measure is computed. Credits are the limit: the NCAA football arm holds credits in reserve for the NHL arm only until 11-06 (ADC-007).

**Closed 2026-11-17.** The user extended experiment 9 to 2026-12-05, the day NCAA football and NBA close. The plan
amendment (`docs/PREDICTIONS-NHL.md`, 11-17) was written before any NHL measure was computed; only counts had been
run. The collector had kept running after 11-05 with unchanged code, so 11-06 to 11-16 counts. `NHL_DAYS` in
`analyze_live.py` is the only code change. On 11-17: 253 usable games (193 + 60 after 11-05), with about 360
projected by 12-05. The extension costs about 130 credits against 325 left plus the 12-01 reset. The NHL+MLB pooled
test runs once, after 12-05.

---

## ADC-016 — A fourth sport from free sources only: NBA moneylines — DONE

**Context.** The user asked to add NBA moneylines (2026-10-22). A Pinnacle arm like the NHL one would cost about 10
credits a night, and the free key's remaining credits are committed to experiments 9, 10, 12 and 13 (ADC-007, ADC-015).

**Decision.** The user chose free sources only. ESPN gives the schedule and results; Polymarket and Kalshi give
1-minute price histories after the games; blind Jev is asked before tip-off. A separate module (`nba_free.py`) and a
fourth LaunchAgent (`com.sbayer2.crowd-calibration.nba`), which never calls the Odds API. Plan:
`docs/PREDICTIONS-NBA.md`.

**Consequences.** No sportsbook, so no crowd-or-book test for the NBA. In exchange, the exchange-vs-exchange tests (E1,
E2) and a cross-sport test of Jev (X6) cost nothing. Because prices are read after the games, only Jev's answer
depends on the Mac being awake. Analysis: `analyze_nba.py`, run on real data only as counts until 12-05.

---

## ADC-017 — The MLB report is run alone, before the other sports close — DONE

**Context.** MLB collection ended with the World Series (10-29). `analyze_live.py report` has no per-sport option and
computes every sport it finds, which ADC-013 forbids for NHL (closes 11-05) and NCAA football (closes 12-05).

**Decision.** Run the report once with `--root` pointing at a tree that contains only a link to `runs/mlb` (user's
request, 2026-11-03). The script is unchanged. Its MLB-only counts matched the real tree (18 usable, 6 dropped) before
the report ran.

**Consequences.** No NHL or NCAA football measure was computed; the pooled C2 and J1 (ADC-011) still run at NHL's close
with the same code. Results: M-001 in `tests/FINDINGS.md`. The drop review also identified the cause of the Rays @
Yankees miss (10-07), not recorded before: the MLB collector ran no ticks from 5:52 to 7:34 PM CDT.

---

## ADC-018 — An NCAA football game moved off its Saturday is dropped as postponed — DONE

**Context.** Ole Miss @ Oklahoma was listed for Saturday 11-14 when that day's Top 25 was frozen, so it entered the
experiment 12 scope. It was then rescheduled to Sunday 11-15. The scope is sticky, but the collector snapshots only
Saturday Top 25 games, so the game had no T-5 and counted as a collector miss ("no Pinnacle T-5"). It was first
misreported as a spreads-only game that the t72 collector had added; the t72 collector never writes the scope.

**Decision.** A scope game whose last listing falls on a day without a frozen Top 25 is dropped as postponed, applying
the 10-17 postponed-game rule. It is not counted as a missed T-5. The drop total is unchanged; only the reason moves.
This is applied in `analyze_live.games` and tested on synthetic data. The plan amendment is in
`docs/PREDICTIONS-NCAAF.md` (11-17).

**Consequences.** The NCAA football drops read 14 "no Pinnacle T-5" plus 1 postponed. Later reschedules are classed the
same way without a manual list. Spreads (experiment 13) are unaffected: they read their own t72 files.

## ADC-019 — NHL replication sample to the end of the regular season (Experiment 9b) — OPEN

**Context.** On 2026-11-18 the user asked to extend NHL collection through the full season. The NHL schedule API gives
the 2026-27 regular season end as Saturday 2027-04-10 (1,344 games in all). About 1,040 games remain after 11-17;
at the current usable rate (about 88%) that is about 900 more usable games. NHL alone costs about 7.5 Odds API
credits a day (about 230 a month against 500), so credits are not the constraint. Two designs were weighed: move the
experiment 9 close to 04-10, or keep the 12-05 close and add a separate sample.

**Decision (user, 11-18).** Keep experiment 9's close at 12-05 and run its report in December as planned. Games from
2026-12-06 to 2027-04-10 form a new pre-registered replication sample, Experiment 9b. It tests the same predictions
(C1-C3, J1-J3) with the same methods on new games, and its analysis runs once, after 04-10. Keeping the samples
separate also keeps any drift in the unpinnable Jev gateway alias (`typesafe-ai/jev`) out of experiment 9.

**To do before 12-06 (not yet done):**
- Write the 9b amendment in `docs/PREDICTIONS-NHL.md` before any NHL measure is computed. It must say what counts as
  replicated (for example, the same sign and the same decision threshold as experiment 9).
- `analyze_live.py`: add a 9b window (`2026-12-06` to `2027-04-10`) as its own sample, plus a synthetic test.
- `live_odds.py`: run `collect-poly` daily inside the NHL tick at a quiet hour (about 04:00 CT). Today it runs only
  from the session-only hourly check or on "update", and an unmatched game is retried for only 3 days. A 5-month run
  cannot depend on a Claude session. It must not run near a T-5 window.
- README, `tests/FINDINGS.md` and the project memory.

**Consequences.** The NHL LaunchAgent keeps collecting past 12-05 with no change (it has no stop date). The Mac must
stay awake and online on game evenings through 04-10. The Jev gateway cost for about 1,000 more games x 2 configs has
not been measured.
