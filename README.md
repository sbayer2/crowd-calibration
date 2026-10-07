# crowd-calibration

**Does a language model know what the crowd knows? And who is "the crowd" in a prediction market?**

[Jev](https://docs.typesafe.ai) (TypeSafe's System One) answers structured questions (yes/no, choice, score) with
probabilities. This project asks Jev about real Polymarket events **without showing it the price**, then compares its
answers with the market and with what actually happened. Every experiment is pre-registered (predictions committed
before any data), run on fresh, independent Jev calls, and recorded in `tests/FINDINGS.md`, including the predictions
that failed.

## Now running: is Polymarket's sports price the crowd or the bookmaker? (experiments 9 and 10)

Polymarket pays market makers to quote near its price, and practitioners say sports quotes are copied from sharp
sportsbooks such as Pinnacle. If so, the "wisdom of the crowd" Jev was being compared with may be largely a
bookmaker's line. A **live collector** records three forecasters for every game, going forward:

| Source | What | When |
|---|---|---|
| **Pinnacle** (+ Matchbook exchange) | no-vig moneyline, via The Odds API | early in the day, 60 min and 5 min before each start |
| **Polymarket** | 1-minute price history and the result | fetched after the games |
| **Jev** | blind answer: told only the league, "Away vs. Home" and the date | once per game, before it starts |

- **Experiment 9:** NHL, 2026-10-06 to 11-05, about 400 games ([pre-registration](docs/PREDICTIONS-NHL.md)).
- **Experiment 10:** MLB postseason, Division Series through the World Series, a pilot of about 40 games
  ([pre-registration](docs/PREDICTIONS-MLB.md)).

Pre-registered tests:
- **Crowd or book.**
  - **C1:** do Polymarket and Pinnacle agree?
  - **C2:** does Polymarket predict anything beyond Pinnacle?
  - **C3:** when they disagree an hour before the start, which one moves toward the other?
- **What Jev agrees with.**
  - **J1:** does Jev side with the crowd or the book where they differ?
  - **J2:** is Jev closer to the early line (mostly a strength rating) than to the close (which adds game-day news)?

Agreement alone cannot separate copying from two good forecasters reaching the same answer, so C2 and C3 are the
decisive tests.

## Headline findings so far

| # | Question | Finding |
|---|---|---|
| C-001 | Does blind Jev track Polymarket on long-range markets? | Moderately: ρ 0.52 on contested markets (p = 0.002). Misses are events after its training cutoff. |
| H-001 | Where does Jev's knowledge end? | AUC against outcomes about 0.82 on 2024 markets, falling to about 0.63 in 2025 Q2 onward; the crowd stays at 0.90-0.98. No memory of surprises. |
| B-001, O-001 | Can rewording the question make Jev match the market on Braves games? | No. 220 request configurations, none matched Polymarket in every part of the season; the best was within luck. The wording changes Jev's numbers, not its accuracy. |
| T-001, T-002 | Tennis: does Jev know the players? | Where it knows them, yes: AUC 0.69 on tour-level matches (market 0.78), about 0.55 on Challenger/ITF. All question types score alike once Jev has knowledge. Jev adds nothing to the market, and its strength score flags players it doesn't know. |
| S-001 | Does the Braves-optimal wording carry over to MLB, NFL, NBA, NHL? | No. It never helps, and it significantly hurts MLB. Jev can't infer home team from "A vs. B" (Polymarket lists away first). |

**What carries across:** with only a matchup in the state, Jev expresses a **reputational prior**. The question type
and wording decide how that prior is expressed, not what it knows. The crowd's edge is current information: 2026
form, injuries, lineups.

## Run it locally

```bash
python3 -m venv .venv && .venv/bin/pip install python-dotenv     # + torch transformers huggingface_hub for the openjev arm
printf 'AI_GATEWAY_API_KEY=...\nODDS_API_KEY=...\n' > .env        # Vercel AI Gateway key (Jev); The Odds API key (free tier)
.venv/bin/python live_odds.py --sport nhl tick            # one collection pass (run every 5 min by a LaunchAgent)
.venv/bin/python live_odds.py --sport nhl status
.venv/bin/python live_odds.py --sport nhl collect-poly    # after games: Polymarket prices and results
.venv/bin/python tennis_jev.py report                     # any finished experiment re-reports from runs/
```

No Polymarket account is needed: its Gamma and CLOB APIs are public. Results in `runs/` are regenerable and gitignored.
The Odds API free tier has no historical odds, so the Pinnacle comparison is collected going forward.

## Architecture

- **Transport:** `jev.py` (gateway, retries); `openjev_arm.py` (a local open 4B Jev-like model as a control).
- **Market data:**
  - `markets.py` / `history.py`: long-range markets;
  - `braves.py`, `tennis.py collect`: resolved games with pre-match prices;
  - `live_odds.py`: live Pinnacle collection.
- **Experiments**, one module each:
  - `run.py` / `analyze.py`: experiments 1 and 4;
  - `braves_iter.py`: experiment 5;
  - `braves_opt.py`: experiment 6, the 220-config search;
  - `tennis_jev.py`: experiment 7;
  - `sports_jev.py`: experiment 8;
  - `live_odds.py`: experiments 9 and 10.
- **Method:**
  - every Jev request is fresh and stateless (no cache, no session);
  - pick cut-offs are fitted on held-out time blocks;
  - paired bootstrap CIs;
  - a shuffled-outcome null for any search.

## Practical applications

- **Judging an LLM forecaster honestly.** Agreement with a market is not skill. Score against outcomes, against a
  sharp book, and across a knowledge cutoff.
- **Prompt design for structured-output models.** Question type mattered only when the model had little to go on. An
  instruction about information the model can't see (e.g. "consider home field") made its ordering worse, not better.
- **Reading prediction markets.** Experiments 9 and 10 measure how much of a sports market's price is its own crowd
  and how much is a relayed bookmaker line.

## Research directions

- **Did Jev learn bookmaker lines in pretraining?** Compare Jev with Pinnacle closing odds on soccer matches before
  and after its cutoff (free historical CSVs).
- **Does the order book carry information beyond the price?** Record depth and imbalance as well as the midpoint.
- **Framing in markets:** the partition dependence that Sonnemann et al. found, tested on Polymarket's bucketed and
  multi-outcome markets.

## Code structure

```
crowd-calibration/
  jev.py  openjev_arm.py  vendor/            model transports
  markets.py  history.py  braves.py  braves_season.py  tennis.py  games.py  resolve.py   data
  run.py  analyze.py  analyze_history.py  analyze_games.py  questions.py  game_questions.py  culture.py
  braves_iter.py  braves_opt.py  tennis_jev.py  sports_jev.py  live_odds.py               experiments
  docs/PREDICTIONS-*.md   pre-registrations (committed before each run)
  docs/ADC.md             architecture decisions
  tests/FINDINGS.md       the empirical record, including failed predictions and corrections
  tests/test_stats.py
```

## Literature

- Wolfers, J. & Zitzewitz, E. (2006). *Interpreting prediction market prices as probabilities.* NBER w12200.
- Manski, C. (2006). *Interpreting the predictions of prediction markets.* Economics Letters 91(3).
- Hanson, R. (2003). *Combinatorial information market design.* Information Systems Frontiers 5(1).
- Sonnemann, U., Camerer, C., Fox, C. & Langer, T. (2013). *How psychological framing affects economic market prices
  in the lab and field.* PNAS 110(29).
- Snowberg, E. & Wolfers, J. (2010). *Explaining the favorite-longshot bias.* Journal of Political Economy 118(4).
- TypeSafe, *Jev documentation and jaggedness notes*, docs.typesafe.ai.

License: MIT.
