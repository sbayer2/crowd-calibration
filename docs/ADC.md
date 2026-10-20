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

## ADC-013 — Live analysis code is written before collection closes and tested on synthetic data — OPEN

**Context.** Experiments 9, 10, 12 and 13 have collectors but no analysis code. Running analysis code on partial real
data would show results before the plan's end point.

**Decision.** Write the analysis scripts now. Test them on synthetic data in the real file formats; on the real data,
look only at counts (usable games, drop reasons) until collection closes. Commit each script before its first real
run.

**Consequences.** Any bug found at the real run is fixed in a new commit and reported. Close this entry when every
script is committed.
