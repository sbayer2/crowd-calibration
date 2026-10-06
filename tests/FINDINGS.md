# Findings

## C-001 — Jev tracks Polymarket prices moderately; confidence tracks error across the range; misses are post-cutoff events

**Date.** 2026-09-30. Snapshot `runs/snapshot-20260930-164430.json`: 60 markets (30 contested at 0.15-0.85, 30 tail),
from 2,100 active markets fetched, 989 passing the filters. Jev (`typesafe-ai/jev`, unpinned) 3 runs; openjev 4B v5
(26de23c) 1 run. Predictions M1-M5 pre-registered in `docs/PREDICTIONS.md` (7de191a) before the full run, with a
disclosed 2-market smoke test.

| | Jev | openjev |
|---|---|---|
| Contested, forecast vs price (primary) | **ρ 0.52** [0.20, 0.74], **p = 0.002**, mean abs error 0.160 | ρ 0.33 [−0.10, 0.65], p = 0.04 |
| Contested, P(yes) vs price | ρ 0.56, p = 0.0008 | ρ 0.54, p = 0.002 |
| All 60, forecast vs price | ρ 0.49, p = 0.0001, mean abs error 0.237 | ρ 0.47, p = 0.0003 |
| Spread vs abs error, all 60 | **ρ +0.66, p = 0.0001** | ρ +0.16, p = 0.11 |
| P(yes) vs forecast agreement | 0.97 | 0.70 |
| Run-to-run SD of the forecast | mean 0.010, max 0.079 | deterministic |

**Predictions.**
- **M1 held.** Contested ρ 0.52, p = 0.002.
- **M2 failed.** All 60 (0.49) did not beat contested (0.52), because Jev compresses the high tail (see below).
- **M3 failed, so the post's claim is supported for Jev**: wider spread goes with larger error. openjev does not show it.
- **M4 held on the primary readout** (Jev 0.52 against openjev 0.33), but **not on P(yes)** (0.56 against 0.54).
- **M5 failed.** Jev's two readouts agree at 0.97; the smoke-test disagreement was one market.
- **Leakage guard:** median abs error of P(yes) against price 0.166; no sign of leakage.

**Robustness of M3 (exploratory, after the data).** Spread is mechanically tied to how extreme a forecast is
(ρ −0.67), so the test was repeated with that effect removed:
- all 60, controlling for forecast extremity: **+0.53, p = 0.0003** (survives);
- contested only, raw: +0.27, p = 0.07;
- contested, controlling for forecast extremity: +0.17, p = 0.20.

The link between confidence and error is real **across the full range** and **weak among contested markets**.

**Where Jev misses (exploratory).** The largest errors are questions whose answer depends on events after Jev's
training cutoff:

| Question | Price | Jev |
|---|---|---|
| Kimi Antonelli, 2026 F1 champion | 0.91 | 0.31 |
| Mojtaba Khamenei head of state in Iran at end of 2026 | 0.87 | 0.33 |
| No Fed rate cuts in 2026 | 0.97 | 0.23 |
| Fed cuts 25 bps in October | 0.004 | 0.42 |
| Becerra wins California governor | 0.96 | 0.21 |

Its closest matches are questions whose shape was set before the cutoff:

| Question | Price | Jev |
|---|---|---|
| AOC wins the 2028 nomination | 0.19 | 0.17 |
| Le Pen wins in 2027 | 0.43 | 0.40 |
| Philippe wins in 2027 | 0.18 | 0.12 |
| Barcelona wins the Champions League | 0.23 | 0.16 |

Jev is also asymmetric:
- It prices longshots reasonably but overprices them more than the market does (tail mean 0.017 → 0.13).
- It will not say "very likely yes": markets above 0.85 average 0.36-0.50 from Jev.

**Reading.** Jev's agreement with the crowd looks like shared knowledge up to its training cutoff, not access to the
situation itself. Where the answer needs post-cutoff information, it neither agrees with the market nor knows that it
should defer, beyond a wider spread. The cutoff split is post hoc. **The next test should label questions as pre- or
post-cutoff before scoring them.**

**Limits.**
- One snapshot and 60 markets, with near-complementary pairs (R vs D Senate, R vs D 2028), so the effective n is
  below 60.
- Agreement with the market is not accuracy: nothing has resolved yet.
- The Jev alias is unpinned.

---

## C-002 — Screening: Jev mostly flags its own uninformed disagreements — EXPLORATORY (after the data)

**Date.** 2026-09-30. Same snapshot and runs as C-001. Not pre-registered: these questions were asked after seeing
C-001, as candidate uses of a Jev-like model against a market. None can be scored for accuracy until markets
resolve.

- **Screening mechanics.** Jev differs from the market by 0.15 or more on 31 of 60 markets. On **28 of those 31**,
  its spread is above 0.12: it flags the disagreement as uncertain. Only **3** are confident disagreements (gap ≥ 0.15,
  spread ≤ 0.12), which are what a screener would pass on for checking:

  | Question | Price | Jev | Spread | Closes |
  |---|---|---|---|---|
  | Missouri enacts a data center moratorium by end of 2027 | 0.385 | 0.08 | 0.08 | 2028-01-01 |
  | Indiana enacts a data center moratorium by end of 2027 | 0.295 | 0.09 | 0.08 | 2028-01-01 |
  | Democrats win the 2028 US presidential election | 0.645 | 0.48 | 0.09 | 2028-11-08 |

  Whether these are mispricings or gaps in Jev's knowledge (state bills introduced after its training cutoff) is
  unknown until they resolve. **The thresholds 0.15 and 0.12 were chosen after the data.**
- **Thin crowds.** Liquidity against the size of the disagreement: Spearman −0.47 (one-sided p < 0.001). Jev
  disagrees more with less-liquid markets. **This is confounded:** the less-liquid markets here are mostly the
  0.85-0.95 tail (House seats, the F1 title, Iran's leadership), which are also the questions that need
  post-cutoff news. The smallest market had $49k liquidity, so truly thin markets were not tested.
- **Combining Jev with the market.** Not testable without outcomes.

**Reading.** Jev largely knows when it does not know. That is a property a screener needs, but it is not evidence
that screening pays. Experiment 2 (games resolving nightly) can test it faster: do Jev's confident disagreements
beat the market after costs? A test with thresholds fixed in advance belongs in a pre-registration before that
analysis is run.

---

## H-001 — The seams study: Jev's knowledge thins after spring 2025; no memory of surprises; confidence is mostly mechanical

**Date.** 2026-10-02. Sample `runs/history-20261001-212350.json`: 1,125 binary Polymarket markets resolved 2023 Q1
to 2026-10-01 (20 after Jev's release). The crowd = the Yes price 7 days before close. Jev: 3 runs on all 1,125.
openjev: 1 run on 359 (about 30 per quarter). Both blind to price and outcome. Predictions H1-H6 pre-registered in
`docs/PREDICTIONS-HISTORY.md` (d1008d0) before any model answer.

**Seam 1 — accuracy by the quarter the market closed (AUC against the outcome):**

| Quarter | n | Crowd | Jev | openjev |
|---|---:|---:|---:|---:|
| 2024 Q1 / Q2 / Q3 / Q4 | 100 each | 0.94 / 0.96 / 0.96 / 0.93 | **0.91 / 0.80 / 0.87 / 0.69** | 0.96 / 0.68 / 0.46 / 0.71 |
| 2025 Q1 | 100 | 0.98 | **0.83** | 0.62 |
| 2025 Q2 / Q3 / Q4 | 100 / 62 / 100 | 0.93 / 0.94 / 0.92 | **0.64 / 0.64 / 0.63** | 0.74 / 0.53 / 0.62 |
| 2026 Q1 / Q2 | 93 / 100 | 0.95 / 0.90 | **0.66 / 0.60** | 0.49 / 0.74 |
| 2026 Q3 before release | 62 | 0.96 | 0.79 | 0.75 |
| After release (2026-09-15) | 20 | 0.92 | 0.84 | 0.64 |

Brier: crowd 0.090 against Jev 0.164 pre-release (openjev 0.228 on its subsample); coin flip 0.250.

**Predictions.**
- **H1 held.** Jev's 2024 AUC (mean about 0.82) exceeds its 2026 Q1-Q2 AUC (about 0.63) by about 0.19; the crowd
  varies by less than 0.05. **The drop sits between 2025 Q1 (0.83) and 2025 Q2 (0.64)** and stays down. That is
  outside evidence of where Jev's knowledge thins out. Caveats:
  - the two latest windows (2026 Q3 before release, after release; n = 62 and 20) recover to 0.79 and 0.84;
  - each quarter's topic mix and Yes rate differ.

  So the date is approximate.
- **H2 held.** Where the crowd was confidently wrong 7 days out (n = 56), Jev sided with the outcome on 5 (9%), with
  mean P(outcome) 0.26. Where the crowd was confidently right (n = 845), Jev agreed with the outcome on 86%. Jev
  forecasts in the crowd's direction, surprises included. There is **no sign of memorised outcomes**, against the
  "trained on resolved markets" hypothesis, at least for the cases that matter.
- **H3 held.** Jev's Brier is worse than the crowd's in every window with n ≥ 50.
- **H4 split.** Among 732 pre-release longshots (price < 0.15):

  | | Mean |
  |---|---|
  | Crowd price | 0.023 |
  | **Actually happened** | **0.052** |
  | Jev | 0.219 |

  - **Failed:** the market *under*priced longshots, the opposite of the predicted favourite-longshot bias.
  - **Held:** Jev overprices them far more than the crowd does.
- **H5 failed** as written.

  | Jev says | Happened |
  |---|---|
  | 0.11 | 0.13 |
  | 0.29 | 0.27 |
  | 0.49 | 0.36 |
  | 0.69 | 0.54 |
  | 0.88 | 0.97 |

  Jev is well calibrated at the low end, says yes too readily in the middle, and is too cautious at the top. That is
  not the symmetric compression predicted.
- **H6 held, weakly.** On the surprises (n = 19), openjev put more than 0.5 on the outcome in 7 (37%), but its
  forecasts sit near 0.5 throughout (mean P(outcome) 0.48; overall AUC 0.63; agreement with price ρ 0.22). It
  barely forecasts, so it shows no clear seam either.

**Correction: confidence vs error (exploratory, after the data).** The raw link between Jev's spread and its
error against the outcome is ρ +0.66. But spread is almost a function of how extreme the forecast is (ρ −0.85).
Controlling for that:

| | Partial ρ |
|---|---|
| All 1,125 | **+0.04** (p = 0.0005, but negligible) |
| Contested markets (crowd 0.15-0.85, n = 265) | raw +0.04, partial +0.01, p = 0.43 |

**This revises C-001 (M3) and C-002.**
- M3's "confidence tracks error" was measured against the *market price*, on 60 markets, and survived a similar
  control (+0.53).
- Against **outcomes**, on 1,125 markets, it nearly vanishes.
- Jev's uncertainty mostly mirrors how extreme its answer is. It is not an independent signal of when it is wrong.
- The screener hypothesis therefore lacks support on outcomes. Its live test in experiment 2 is 1 win in 4
  confident flags so far.

**Reading.**
- Jev's agreement with prediction markets looks like **world knowledge up to about spring 2025**, applied with
  roughly honest but not self-aware uncertainty.
- It is not a memory of market answers, and not crowd wisdom beyond shared knowledge.
- **Open questions:**
  - Why does the seam fall in spring 2025?
  - Why is Jev over-eager in the middle of the scale?
  - Why do markets underprice longshots in this sample?

---

## B-001 — Experiment 5: prompt changes alone do not improve blind Jev on Braves games; Jev and the market tie a "good team" baseline

**Date.** 2026-10-05. 172 Braves moneyline games this season, priced on Polymarket and resolved. Market =
the price 5 minutes before first pitch. Tuning set: 41 games (2026-08-19 to 10-05), including the 26 examined
earlier. Hold-out: 131 games (2026-03-20 to 08-18), untouched until one final run. Plan, variants, selection rule
and predictions B1-B4 committed before any variant ran (4d48de2). Prompt-only: Jev never saw prices, results,
standings, pitchers or home/away facts.

**Tuning set (41 games; the market picked 23/41 right, Brier 0.243):**

| Variant | Picks right | Brier, raw | Brier, fitted | ρ with market |
|---|---|---|---|---|
| V0 plain yes/no | 15 | 0.256 | 0.253 | +0.48 |
| V1 both sides | 18 | 0.255 | 0.252 | +0.42 |
| V2 neutral two-team choice, both orders | 18 | 0.346 | 0.280 | +0.29 |
| **V3 probability bins, both sides** | 18 | 0.251 | **0.250** | +0.36 |
| V4 forced 60/40, both framings | 16 | 0.309 | 0.268 | +0.43 |
| V5 "typical strength" instruction | 18 | 0.423 | 0.305 | +0.39 |
| V6 composite strength Scores (docs pattern) | 18 | 0.330 | 0.280 | +0.51 |

- Every variant's fitted confidence slope hit the grid floor (k = 0.5): on tuning, Jev's opinion was best shrunk
  toward 50%.
- The variants without named-team framing (V2, V5, V6) commit harder and score worse.
- V6 tracks the market best (ρ +0.51) but is badly calibrated.
- **V3 was selected** by lowest fitted Brier.

**Hold-out (131 games, one run):**

| | Picks right | Brier |
|---|---|---|
| Polymarket | 80 (61%) | 0.243 |
| Jev V3, raw | 78 (60%) | 0.242 |
| Jev V3, fitted | 78 (60%) | 0.245 |
| Coin flip | — | 0.250 |
| Always pick the Braves | 78 (60%) | — |
| Constant "Braves 60%" | — | about 0.241 |

- Brier(Jev fitted) − Brier(market) = **+0.002**, 95% bootstrap CI [−0.009, +0.013]: indistinguishable.
- Jev's forecasts span 0.48-0.63 and lean Braves almost every game. Its picks equal "always pick the Braves". The
  Braves went 78-53 in this half.
- The market beats a coin flip on picks (80/131, p = 0.007), but not the constant base-rate forecast.

**Predictions.**
- **B1:** directionally true (0.245 vs 0.243), not significant.
- **B2 held:** Jev 60%, the market 61%.
- **B3 failed:** the numeric-bins variant was selected, by staying closest to 0.5.
- **B4 failed:** neutral wording scored worse than the plain question.

**Reading.**
- Without game information, prompt changes alter how boldly Jev states a team-reputation prior, not what it knows.
- Over half a season, that prior was about as good as the market on single games, because the Braves were good and
  single games are close to coin flips. The market's per-game information did not show up as a measurable Brier
  edge in 131 games.
- When the Braves were average (tuning, mid-August onward), the same prior looked bad.

**Limits.** One team. The hold-out may include up to 5 spring-training games before March 26. The tuning and
hold-out periods differ in the Braves' form, so the selected variant's tuning advantage reflects that period.

## O-001 — Experiment 6: 220 ways of asking Jev change how its ordering follows the market, not whether it predicts the outcome

**Run 2026-10-05, after pre-registration** (`docs/PREDICTIONS-OPTIMIZE.md`, commit 48af96f).

**Setup.**
- Search space: 220 of the 270 request configs (question type × instruction wording × criteria × state shape).
- Each config was asked about all 172 Braves games of 2026 in fresh, stateless runs. 291 runs in total; every top-5
  config re-run until it had 3 runs.
- Picks: "Braves" when the config's number is at or above a cut-off fitted on the other three time blocks.
- Target (option a): pick accuracy at least the market's in every block. Market: 70 / 58 / 58 / 53%, 59.9% overall.

**Result.**

| | Blocks | Overall | Worst-block margin | Picks Braves |
|---|---|---|---|---|
| Polymarket | 70 / 58 / 58 / 53% | 59.9% | 0 | — |
| Best config, 3-run mean: `score_bins \| venue \| plain \| string` | 67 / 58 / 59 / 56% | 60.1% | −2.3 | 87% |
| Runner-up: `noul_both \| favourite \| plain \| object` | 70 / 55 / 58 / 53% | 58.9% | −3.1 | 99% |
| Always pick the Braves | 70 / 53 / 58 / 53% | 58.7% | −4.7 | 100% |

- **The best config:** win-likelihood bins about each team, the instruction to "consider home-field advantage and
  travel", and the matchup as one sentence.
- **Configs meeting the target:** 0 of 220 on their mean; 1 of 291 single runs. That run was the best config's
  first run (72 / 60 / 58 / 56%); its two confirmation runs fell back to 67% in March-May.
- **Null control:** the same configs and runs scored on 200 shufflings of win/loss.
  - Best margin: median +0.0, 95th percentile +9.3.
  - 78% of shuffles reach or beat the real best (−2.3).
  - The search found nothing that luck over 220 configs would not produce.
- **Run-to-run agreement:** mean rank correlation +0.97 over 97 pairs of repeated runs. Jev is close to deterministic
  in how it orders games, so differences between configs come from the query, not sampling noise.

**How each setting moves Jev** (mean over the configs using it):

| Setting | Values | Rank corr. with market | Rank corr. with outcome | Picks Braves |
|---|---|---|---|---|
| Question type | yes/no Braves, yes/no both, choice both orders, strength Score, bins Score | +0.24 / +0.29 / +0.28 / **+0.42** / +0.31 | +0.02 to +0.05 | 95% → 89% |
| Instruction wording | plain, strength, form, favourite, coin flip, venue | +0.22 (venue) to +0.34 | +0.02 to +0.04 | 89% to 94% |
| Criteria | plain, detailed, boundary | +0.28 to +0.32 | +0.02 to +0.03 | 90% to 93% |
| State shape | object, string, object without date | +0.29 to +0.32 | +0.02 to +0.03 | 91% to 92% |

- Across configs, the rank correlation with market price spans −0.04 to +0.50 (mean +0.31).
- The rank correlation with the outcome spans −0.09 to +0.10 (mean +0.03). No config reaches the market's own
  +0.11.

**Predictions.**
- **O1 held:** no config met the target on its mean.
- **O2 held:** the best config is well inside the null distribution.
- **O3 held.**
  - Question type has the largest spread in market correlation (0.18) and Braves-pick share (6 points).
  - The spreads within wording (0.12), criteria (0.04) and state (0.03) are all under 0.15.
  - **Correction:** at 20 configs I said wording "points against O3" (range 0.18-0.42 then). With 33-40 configs per
    wording the range narrowed to 0.22-0.34. The early read was small-sample noise.
- **O4 held:** 218 of 220 configs (99%) correlate positively with the market.
- **O5 held:** the mean correlation with the outcome is +0.03.
- **O6 held:** run-to-run agreement (+0.97) far exceeds agreement with the market (+0.31).

**Reading (the user's question: how does the architecture of the query change the prediction?).**
- **The query sets how closely Jev's ordering of games follows the crowd's.**
  - The question type matters most: asking for each club's strength as a Score, the docs' composite pattern,
    roughly doubles the market correlation of a plain yes/no (+0.42 vs +0.24).
  - Wording comes next; criteria and state shape barely matter.
  - Mechanism: with only a matchup in the state, every query draws on the same team-reputation prior. The question
    type decides how much of that prior's gradation reaches the answer.
    - A strength Score exposes it level by level.
    - A yes/no about one team compresses it to around 0.5 with a constant lean.
- **No query architecture reaches the outcomes.** The prior Jev expresses tracks the crowd's reputational view, but
  not the extra information the market adds (its +0.11 against Jev's best +0.10 and mean +0.03).
- **This contrasts with emoji-pile.** There, the items being sorted are in the state, so the task acts on visible
  information. Here the state is two names and a date. The query can reshape the prior, not add evidence.
- **The fitted cut-off pushed most configs to "always Braves".** Where the ordering carried no outcome information,
  the best use of it was to ignore it. Only the leader (87% Braves picks) used its ordering to pick against the
  Braves in some games, and its 3-run mean ties the market overall by one game in 172.

**Limits.**
- One team, one season.
- Mutation search, not the full grid: 50 configs unvisited, mostly near poor regions.
- The cut-off is fitted per block on the other three, which costs a forecaster with real information too (the
  market's own price scored −9.3 this way).

**Open.**
- The same grid with a richer state (e.g. last season's records, home/away stated explicitly) would test whether the
  query matters more once Jev has something to sort on.

## T-001 — Experiment 7: blind Jev predicts tennis winners where it knows the players; the question type barely matters

**Run 2026-10-05, after pre-registration** (`docs/PREDICTIONS-TENNIS.md`, commit 990f351).

**Setup.**
- Sample: 1,250 singles matches over 45 days, 625 tour-level and 625 lower-level (random, seed 7).
- Jev was told only the sport, tournament, "A vs. B" and the date.
- Five question types, one fresh run each.
- Primary measure: AUC against the outcome.

**Result.**

| | Tour-level AUC | Rank corr. with market | Picks (CV cut-off) | Lower-level AUC | Rank corr. with market | Picks (CV cut-off) |
|---|---|---|---|---|---|---|
| **Polymarket** | **0.784** | — | 69.6% (at 50%) | **0.734** | — | 68.6% (at 50%) |
| yes/no about A | 0.683 | +0.59 | 62.1% | 0.569 | +0.20 | 55.7% |
| yes/no about each | **0.692** | +0.60 | 61.1% | 0.560 | +0.20 | 56.8% |
| choice, both orders | 0.690 | +0.60 | 62.6% | **0.570** | +0.22 | 57.3% |
| strength Score | 0.682 | +0.54 | 64.0% | 0.542 | +0.24 | 53.3% |
| win-likelihood bins | 0.688 | +0.58 | 62.6% | 0.568 | +0.19 | 56.2% |

- **Market minus Jev AUC** (paired bootstrap, 2,000 resamples):
  - tour-level +0.09 to +0.10, every CI from about +0.05 to +0.14;
  - lower-level +0.16 to +0.19, every CI from about +0.11 to +0.24.
- **Strength levels Jev gave** (per player, rounded; 0 = "unknown or lower-level" ... 4 = "elite"):

  | | 0 | 1 | 2 | 3 | 4 | Mean |
  |---|---|---|---|---|---|---|
  | Tour-level | 9% | 26% | 29% | 24% | 11% | 2.00 |
  | Lower-level | 76% | 18% | 5% | 0% | 0% | 0.37 |

- **For comparison (O-001, Braves):** Jev's best correlation with outcomes +0.10, the market's +0.11. Tennis is the
  first setting in this repo where blind Jev clearly predicts outcomes.

**Predictions.**
- **T1 held.** Tour-level best AUC 0.692 (≥ 0.65); lower-level best 0.570 (≤ 0.60).
- **T2 held.** The market leads every type in both tiers; every CI excludes 0.
- **T3 failed.** The strength Score had the *lowest* rank correlation with the market on tour-level matches (+0.54
  vs +0.58 to +0.60). The O-001 ordering did not replicate.
- **T4 failed.**
  - The AUC spread across types is 0.010 on tour-level and 0.028 on lower-level, larger where Jev knows less.
  - The lower-level spread is the strength Score falling behind (0.542).
- **T5 held strongly.** Jev put 76% of lower-level players at "unknown or lower-level", and spread tour-level players
  across all five levels.

**Reading.**
- **Knowledge sets the result; the query does not.**
  - Where Jev knows the players, all five question types reach the same AUC (0.68-0.69) and the same agreement with
    the market (+0.54 to +0.60).
  - Where it does not, all five fall to 0.54-0.57.
  - The tier moves AUC by about 0.12; the question type moves it by at most 0.03.
- **Revised view of O-001 (post hoc, not pre-registered).**
  - In baseball, the question type mattered for agreement with the market (+0.24 to +0.42) because there was almost
    no signal; the query decided how much of a weak prior showed.
  - With a strong prior, every query extracts it equally.
  - Prediction T4 assumed the opposite and failed.
- **Why the strength Score lags (post hoc).**
  - It rates each player in general, not the matchup, so it cannot use anything specific to the pairing.
  - On lower-level matches it puts 76% of players on the same "unknown" level, so most pairs tie and nothing orders
    them.
  - The probability-style types keep finer gradations.
- **Jev recognises the edge of its knowledge** (T5). That makes the strength level a usable "does Jev know these
  players?" flag; experiment 4's seams finding (H-001) suggested this, and here it is direct.
- **The lower-level AUC is above chance (0.54-0.57).** Some lower-level draws include players known before the cutoff
  (veterans in Challengers, Slam qualifiers). Not checked.
- **The crowd stays well ahead.** About 0.10 AUC on tour-level matches, about 7 points in pick accuracy: 2026 form,
  injuries, surface and fatigue are priced, and Jev cannot see them.

**Limits.**
- One run per type (O-001 measured run-to-run rank agreement at +0.97 in baseball; not re-measured on tennis).
- 45 days of matches, mostly hard courts (US Open and the Asian swing).
- The tier is assigned by tournament, not by each player's ranking.
- Market prices are taken 5 minutes before the *scheduled* start; tennis starts often slip later, so the market may
  have had more time than intended. If anything, that favours the market.

**Open.**
- Does Jev add anything to the market? E.g. a logistic model of the outcome on market price + Jev, cross-validated.
- Split lower-level matches by Jev's strength level, to test whether the above-chance AUC comes from the known players.
