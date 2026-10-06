# Pre-registered plan — experiment 7: blind Jev on tennis, by tier

Written 2026-10-05, after the market-only ceiling check and a one-match smoke test, before any full Jev run.
Code: `tennis.py` (data and ceiling), `tennis_jev.py` (Jev and report).

**Why tennis (after O-001).** Single MLB games leave almost no room for skill: the market's own AUC is 0.63 (all MLB,
45 days) and its rank correlation with Braves outcomes is +0.11. Tennis has more: market AUC 0.72 over 4,458 singles
matches. Its tiers also separate players Jev should know from players it mostly cannot.

**Already seen (market only).** Outcomes and pre-match prices of all matches.

| Tier | Matches | Favourite wins | Market AUC | Rank corr. with outcome |
|---|---|---|---|---|
| Tour-level | 602 | 69.8% | 0.78 | +0.49 |
| Lower-level | 3,856 | 65.5% | 0.71 | +0.37 |

This was measured before Cincinnati, Davis Cup and Laver Cup were moved to tour-level, which brought tour-level to
625 matches. Jev has not been asked about any match except one smoke-test match (Shimabukuro vs. Kecmanovic, not
reused).

**Sample** (frozen to `runs/tennis-sample.json`, seed 7):
- **Tour-level:** all 625 matches. Grand Slam main draws, ATP/WTA tour events, Cincinnati, Davis Cup, Laver Cup.
- **Lower-level:** a random 625 of 3,856. Challengers, ITF, WTA 125, Slam qualifying.

**Inputs.** Sport, tournament, "A vs. B" as Polymarket lists it, date. No price, ranking, seed or result.

**Question types** (plain wording; definitions in `tennis_jev.py`):
- yes/no about A;
- yes/no about each player;
- choice in both option orders;
- a descriptive 5-level strength Score per player, from "Unknown or lower-level" to "Elite: top 10";
- a 5-bin win-likelihood Score per player.

One fresh, stateless run per type. Experiment 6 measured run-to-run rank agreement at +0.97.

**Measures, per tier and type.**
- AUC of Jev's number against the outcome (primary: threshold-free, and blind to Jev's constant lean).
- Market AUC on the same matches; paired bootstrap 95% CI of market minus Jev (2,000 resamples).
- Rank correlation with the market price.
- Pick accuracy with a cut-off fitted on the other three of four chronological folds.

**Predictions.**
- **T1. Knowledge sets the ceiling.**
  - On tour-level matches, the best type reaches AUC ≥ 0.65.
  - On lower-level matches, every type stays at AUC ≤ 0.60.
  - Mechanism: Jev's priors cover players established before its cutoff (around spring 2025, H-001), not the
    Challenger/ITF field.
- **T2. The crowd stays ahead.** In both tiers the market's AUC exceeds every type's, with the paired CI excluding 0.
  Mechanism: the market knows 2026 form, injuries and surface; Jev does not.
- **T3. The strength Score again tracks the market best.** On tour-level matches, the strength Score has the highest
  rank correlation with the market of the five types (replicating O-001).
- **T4. The query matters more when Jev has knowledge.** The spread in AUC across the five types is larger on
  tour-level than on lower-level.
- **T5. Jev recognises what it does not know.** On lower-level matches, the most common strength level given is the
  lowest ("Unknown or lower-level").

**What would change the reading.**
- If lower-level AUC exceeds 0.60, Jev is reading something from names or tournaments beyond player knowledge, for
  example nationality or the tournament's location. That would be checked before any claim.
- If T2 fails on tour-level, blind Jev matches the crowd where it knows the players. That would be the first such
  result in this repo, and it gets a fresh second run before any claim.
