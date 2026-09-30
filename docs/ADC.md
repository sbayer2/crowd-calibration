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
