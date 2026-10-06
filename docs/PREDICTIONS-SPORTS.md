# Pre-registered plan — experiment 8: does the Braves-optimal request carry over to other sports?

Written 2026-10-06, after collecting the games and the market-only ceilings, and after a one-game smoke test (2025
NFL opener). No full Jev run yet. Code: `sports_jev.py`.

**Question (from the user).** Experiment 6 searched 220 request configs on the Braves season, with Polymarket's
per-block pick accuracy as the target. The best was config 182:
- win-likelihood bins asked about each team;
- the instruction "Consider home-field advantage and travel for this matchup.";
- plain criteria;
- the game as a one-sentence string.

Its edge was within luck (O-001). Does that wording, type and criteria do anything on other sports?

**Games** (all priced and resolved moneylines from `tennis.py collect`; volume ≥ $5k; price 5 minutes before start):

| Sport | Games | Window | Favourite wins | Market AUC |
|---|---|---|---|---|
| MLB, all teams | 507 | 2026-08-22 to 10-04 | 59.6% | 0.63 |
| NFL | 393 | 2025-09-05 to 2026-10-05 | 63.1% | 0.69 |
| NBA | 373 | 2026-01-28 to 04-12 | 74.0% | 0.83 |
| NHL | 290 | 2026-01-31 to 04-15 | 59.7% | 0.64 |

- Polymarket lists games "away vs. home". Checked: "Cowboys vs. Eagles", the 2025 opener in Philadelphia; "Eagles
  vs. Chiefs", 2025-09-14 in Kansas City. The first-listed team wins 46-48% in every sport.
- Jev is not told which team is at home.

**Configs.** Each is one fresh, stateless request per game.
- `c182`: the Braves optimum.
- `bins_plain`: c182 without the venue instruction. It differs by one thing, so it isolates the wording.
- `noul_both`: plain yes/no about each team, object state; the plain baseline.

**Measures, per sport and config.**
- AUC against the outcome.
- Rank correlation with the market.
- Pick accuracy with a cut-off fitted on the other three of four chronological blocks.
- Per-block margin over the market (the experiment 6 target).
- Raw lean to the home team.
- The paired bootstrap 95% CI of AUC(c182) − AUC(bins_plain), the venue-wording effect.

**Predictions.**
- **X1. The venue wording was luck.**
  - In no sport does c182 beat bins_plain on AUC with a paired CI excluding 0.
  - The mean effect across the four sports is within ±0.02.
- **X2. The crowd stays ahead.** The market's AUC exceeds every config's in every sport.
- **X3. Jev's skill follows what it knows and how predictable the sport is.**
  - Jev's best AUC is highest in the NBA (stable team-strength gaps, star players it knows), at ≥ 0.65.
  - In MLB and NHL it is ≤ 0.58.
- **X4. The experiment 6 target is not met.** No config reaches the market's pick accuracy in all four blocks of any
  sport.
- **X5. Jev does not read home field from "A vs. B".** c182's raw lean to the second-listed (home) team is within 5
  points of bins_plain's in every sport. Mechanism: the string does not say which team is at home. If the lean
  differs, the venue wording makes Jev guess, and the report shows whether the guess helps.

**What would change the reading.**
- If X1 fails in two or more sports in the same direction, the wording carries over and is not luck. It would then get
  a fresh second run.
- If X5 fails and c182's AUC rises with it, Jev knows the away-vs-home listing convention.
