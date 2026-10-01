# Pre-registered predictions — experiment 4: the seams study

Written 2026-10-01, after the sample was frozen (`runs/history-20261001-212350.json`) and **before Jev or openjev answered any of its
questions**. Seen so far: the sample's composition, its outcomes and prices (they define it), and none of the models'
answers.

## Design

- **Sample.** 1,125 binary Polymarket markets that resolved cleanly between 2023 Q1 and 2026-10-01 (`history.py`).
  The highest-volume markets per quarter with volume ≥ $50k, a life of at least 14 days, at most 3 per event and 3 per
  question template. Windows are the quarters by close date; "post-release" = closed after Jev's release on
  2026-09-15 (n = 20).
- **Crowd.** The Yes price 7 days before the market closed (public CLOB daily price history).
- **Models.** Jev (3 runs, mean) and openjev (about 30 per window, 1 run, deterministic) get the question, the
  resolution rules, the close date, and "today" = the date 7 days before close. **Never the price or the outcome.**
  Same questions as experiment 1 (noul and 7-bin Score); `forecast` = the expected bin midpoint.
- **Scores.** Brier and AUC against the outcome, per window, for the crowd, Jev, openjev and a coin flip.

## Predictions (the seams)

- **H1 — The knowledge seam.** Jev's AUC against outcomes is higher for markets that closed in 2024 than for those in
  2026 (before release), by at least 0.05, while the crowd's AUC changes by less than that.
  *Mechanism:* Jev knows more about older events; the drop marks where its training data thins out.
  *Falsified if* Jev's AUC is flat across years, or tracks the crowd's.
- **H2 — No memory of surprises.** On pre-release markets where the crowd was confidently wrong 7 days out (price
  ≥ 0.8 resolved No, or ≤ 0.2 resolved Yes), Jev puts more than 0.5 on what actually happened in **at most 40%**
  of them.
  *If it is 60% or more,* Jev remembers outcomes the crowd did not have: evidence of training on results.
  The crowd-confidently-right markets are the baseline.
- **H3 — Jev beats the crowd nowhere.** Jev's Brier is worse than the crowd's (price 7 days out) in every window with
  n ≥ 50. *Falsified by* any such window where Jev's Brier is lower. That would be the clearest sign of memory.
- **H4 — Longshots.** Among pre-release markets priced below 0.15:
  - they resolve Yes less often than their mean price (the market's favourite-longshot bias);
  - Jev's mean forecast is **higher** than the crowd's (Jev overprices longshots more, as in C-001).
- **H5 — Calibration.** Jev's forecasts are compressed toward 0.5: forecasts below 0.2 resolve Yes less often than
  forecast; forecasts above 0.6 resolve Yes more often than forecast.
- **H6 — openjev as control.** On H2's surprise markets, openjev also puts more than 0.5 on the outcome in at most 40%.

## Power and limits, stated now

- 2023 quarters are small (7-31). Post-release n = 20, so pre/post contrasts are descriptive. The across-years seam
  (H1) has n ≈ 100 per quarter from 2024.
- High accuracy on old markets cannot separate "trained on market outcomes" from "trained on news that reported the
  outcomes". H2 narrows it but cannot close it.
