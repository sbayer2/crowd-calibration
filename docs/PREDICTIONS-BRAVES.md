# Pre-registered plan — experiment 5: can prompt changes alone make blind Jev match Polymarket?

Written 2026-10-05, before the season sample was split and before any variant ran. Seen beforehand: the 26 Braves
games of the last 30 days, with Jev's plain, 60%, forced and opponent-framed answers and their outcomes (the earlier
head-to-head; Polymarket 15/26, Jev at best 13/26). Those 26 games are therefore in the **tuning** set, never the
hold-out.

**Inputs (prompt-only, decided by the user).** League, the matchup as Polymarket lists it, start time, date. No
price, no result, no standings, pitchers or home/away facts. Only the question changes.

**Variants** (`braves_iter.py`). V0 plain yes/no (baseline); V1 yes/no both sides; V2 neutral two-team choice in both
option orders; V3 7-bin win-probability Score both sides; V4 forced 60/40 call both framings; V5 V2 with a
"typical strength, one game is near a coin flip" instruction; V6 composite scoring per TypeSafe's docs (one
descriptive-level club-strength Score per team, combined in code). Jev 3 runs each, mean.

**Confidence.** Per variant, one map fitted on tuning only: a linear stretch around 0.5 (V0-V5) or a logistic slope on
the strength difference (V6), grid k = 0.5-6.

**Split.** Tuning = the 26 known games + the 15 before them; hold-out = all earlier priced and resolved games of the
season. Frozen to `runs/braves-split.json` before any variant runs.

**Selection rule.** The variant with the lowest fitted Brier on tuning. Only that variant runs on the hold-out,
once.

**Predictions.**
- **B1.** On the hold-out, the selected variant's Brier is worse than the market's (prompt changes cannot supply game
  information).
- **B2.** On the hold-out, its pick accuracy is within 10 points of 50%; the market's is above it.
- **B3.** On tuning, V3 (numeric bins) is among the two worst variants, as TypeSafe's docs warn about numeric levels.
- **B4.** On tuning, V2/V5/V6 (no named-team framing) beat V0 on Brier.

With about 40 hold-out games, only large differences are detectable; differences are reported with that caveat.
