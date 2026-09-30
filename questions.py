"""What every arm is asked about a market: the state and two questions. No price, volume or liquidity is ever shown.

Q1 (noul): will it resolve Yes? One probability; for a noul, "confidence" is only its distance from 0.5.
Q2 (score over probability bins): the expected value over bin midpoints is the forecast, and the spread of the
distribution over bins is the confidence, measured separately from the forecast. That makes "58% with high vs
low confidence" measurable.
"""

from __future__ import annotations

import math
from typing import Any

# (label shown to the model, bin midpoint used for the forecast)
BINS: list[tuple[str, float]] = [
    ("Under 5%: almost certainly will not happen.", 0.025),
    ("5-20%: unlikely.", 0.125),
    ("20-40%: less likely than not.", 0.30),
    ("40-60%: roughly a coin flip.", 0.50),
    ("60-80%: more likely than not.", 0.70),
    ("80-95%: likely.", 0.875),
    ("Over 95%: almost certainly will happen.", 0.975),
]
NOUL_TRUE = ("The event in the question will happen as described by the resolution rules before the close date, "
             "so the question resolves Yes.")
NOUL_FALSE = "The event will not happen as described before the close date, so the question resolves No."
NOUL_INSTR = "Will this prediction-market question resolve Yes?"
SCORE_INSTR = "How likely is it that this prediction-market question resolves Yes?"


def state(m: dict[str, Any], today: str) -> dict[str, str]:
    return {"question": m["question"], "resolution_rules": m["description"], "closes": m["closes"][:10], "today": today}


def jev_questions() -> dict[str, dict[str, Any]]:
    return {"yes": {"type": "noul", "instructions": NOUL_INSTR, "criteria": {"true": NOUL_TRUE, "false": NOUL_FALSE}},
            "bins": {"type": "score", "instructions": SCORE_INSTR, "criteria": [label for label, _ in BINS]}}


def summarise_bins(probs: list[float]) -> dict[str, float]:
    """Forecast = expected bin midpoint; spread = probability-weighted SD of the midpoints; entropy in nats."""
    total = sum(probs) or 1.0
    p = [x / total for x in probs]
    mids = [mid for _, mid in BINS]
    forecast = sum(pi * m for pi, m in zip(p, mids))
    spread = math.sqrt(sum(pi * (m - forecast) ** 2 for pi, m in zip(p, mids)))
    entropy = -sum(pi * math.log(pi) for pi in p if pi > 0)
    return {"forecast": forecast, "spread": spread, "entropy": entropy, "top_bin": max(range(len(p)), key=p.__getitem__)}
