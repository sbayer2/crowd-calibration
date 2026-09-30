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
