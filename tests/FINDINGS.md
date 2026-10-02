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
