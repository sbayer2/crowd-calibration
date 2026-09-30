"""What every arm is asked about a game. No price is ever shown.

Both sides are asked ("Will A win?" and "Will B win?"), each as a noul and as the 7-bin Score from questions.py.
Experiment 1 (C-001) found Jev will not say "very likely yes"; averaging P(A wins) with 1 - P(B wins) cancels a bias
that depends on which side the question names. The one-sided answers are kept as well.
"""

from __future__ import annotations

from typing import Any

from questions import BINS, summarise_bins

WIN_INSTR = "Will {team} win this game?"
SCORE_INSTR = "How likely is it that {team} wins this game?"


def state(g: dict[str, Any], today: str) -> dict[str, str]:
    return {"league": g["league"], "game": f"{g['team_a']} vs. {g['team_b']}", "starts": g["starts"][:16] + " UTC",
            "today": today, "resolution_rules": g["description"]}


def jev_questions(g: dict[str, Any]) -> dict[str, dict[str, Any]]:
    qs = {}
    for side, team in (("a", g["team_a"]), ("b", g["team_b"])):
        other = g["team_b"] if side == "a" else g["team_a"]
        qs[f"win_{side}"] = {"type": "noul", "instructions": WIN_INSTR.format(team=team),
                             "criteria": {"true": f"{team} wins the game.", "false": f"{team} does not win; {other} wins."}}
        qs[f"bins_{side}"] = {"type": "score", "instructions": SCORE_INSTR.format(team=team),
                              "criteria": [label for label, _ in BINS]}
    return qs


def combine(noul_a: float, noul_b: float, bins_a: list[float], bins_b: list[float]) -> dict[str, float]:
    """P(A wins) from both framings, plus the one-sided readouts and each side's spread."""
    sa, sb = summarise_bins(bins_a), summarise_bins(bins_b)
    return {"p_a": (noul_a + 1 - noul_b) / 2, "p_a_bins": (sa["forecast"] + 1 - sb["forecast"]) / 2,
            "noul_a": noul_a, "noul_b": noul_b, "forecast_a": sa["forecast"], "forecast_b": sb["forecast"],
            "spread": (sa["spread"] + sb["spread"]) / 2, "framing_gap": abs(noul_a - (1 - noul_b))}
