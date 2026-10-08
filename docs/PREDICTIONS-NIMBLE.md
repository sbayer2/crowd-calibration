# Pre-registered plan — experiment 11: the tennis study (experiment 7) rerun on Nimble

Written 2026-10-08, before the full run. Seen beforehand:
- a one-match smoke test (Shimabukuro vs. Kecmanovic, the same match as experiment 7's smoke test);
- a one-off Georgia @ Alabama comparison, in which Nimble was more extreme than Jev on every question (choice 92% vs
  82%).

Code: `nimble.py` (transport) and `tennis_jev.py --arm nimble` (run, report), `tennis_jev.py compare`.

**Why.** T-001 found that, where Jev knows the players, all five question types reach the same AUC (0.68-0.69), and
that Jev's skill drops to near chance on players it does not know. Both are claims about one model. Nimble is a second,
unrelated model with Jev's API:
- Bespoke Labs, fine-tuned from Qwen3.5-9B, Apache 2.0;
- local through Ollama 0.40, temperature 0, so deterministic.

A finding that holds on both is about this kind of model; one that holds only on Jev is about Jev.

**Design (identical to experiment 7 except the model).**
- Same frozen 1,250 matches (`runs/tennis-sample.json`: 625 tour-level, 625 lower-level).
- Same state, the same five question types with byte-identical wording, and the same value definitions.
- One run per type, since Nimble is deterministic.
- Choice criteria are sent as `{key: description}` (Nimble's format) with the same description text.

**Measures.** Per tier and type: Nimble AUC; the paired bootstrap 95% CI of Nimble − Jev and of market − Nimble
(2,000 resamples, seed 7); the rank correlation between Nimble and Jev, and between Nimble and the market; the choice
lean (mean |P(A) − 0.5|); Nimble's strength-level distribution.

**Predictions.**
- **N1. Nimble knows less than Jev.** On tour-level matches, Nimble's AUC is below Jev's for at least 4 of the 5
  types. Mechanism: Nimble's fine-tuning teaches reasoning over the given text, not world knowledge; what it knows about
  players comes from a 9B base.
- **N2. The crowd stays ahead.** Market − Nimble AUC is positive with the CI excluding 0, for every type in both
  tiers.
- **N3. T-001 replicates: question type barely matters.** Nimble's AUC spread across the five types is ≤ 0.03 on
  tour-level matches.
- **N4. The two models share a prior.** On tour-level matches, the rank correlation between Nimble and Jev is ≥ 0.5
  for every type.
- **N5. Nimble's choice question leans harder than Jev's.** The mean |P(A) − 0.5| for choice_both is larger for Nimble
  in both tiers. This prediction came from the Georgia @ Alabama observation, so it is tested here on new data.
- **N6. Nimble flags unknown players too.** On lower-level matches, its most common rounded strength level is 0
  ("unknown or lower-level").

**What would change the reading.**
- If N1 fails (Nimble ≥ Jev), the 9B base knows tennis as well as Jev, and Jev's knowledge is not special.
- If N3 fails, the T-001 finding is specific to Jev.
