"""Experiment 5: can prompt changes alone make blind Jev match Polymarket on Braves games? Tune, then one held-out test.

Jev's inputs never change: league, matchup ("A vs. B" as Polymarket lists it), start time, date. No price, no result,
no game facts. Only the question changes.

  V0 plain          one yes/no, Braves named (the earlier baseline)
  V1 both-sides     yes/no about each team, P(Braves) = mean of P(Braves win) and 1 - P(opponent wins)
  V2 neutral-choice "Who wins this game?" with both teams as options, asked in both option orders, averaged
  V3 bins           the 7-bin win-probability Score about each team, expected values, both sides averaged
  V4 forced-60/40   the forced 60/40 call about each team, both framings averaged
  V5 strength       V2 with the instruction to judge each team's typical strength and treat one game as uncertain
  V6 composite      TypeSafe's composite-scoring pattern: one descriptive-level Score of club strength per team, combined
                    in code as logistic(k * (strength difference)); k fitted on tuning
Confidence: per variant, a stretch p' = 0.5 + k (p - 0.5), k fitted on the tuning set (grid 0.5-6) to minimise Brier.

Split (frozen in runs/braves-split.json before any variant runs): tuning = the 26 games already examined + the 15
before them; hold-out = all earlier games. Selection: the variant with the lowest stretched Brier on tuning. The hold-out
is scored once, for that variant only, against the market and a coin flip.

    .venv/bin/python braves_iter.py split          # freeze the split
    .venv/bin/python braves_iter.py tune           # all variants on tuning, 3 runs each; table
    .venv/bin/python braves_iter.py holdout        # the selected variant, once, on the hold-out
"""

from __future__ import annotations

import argparse
import json
import statistics
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from questions import BINS, summarise_bins

ROOT = Path(__file__).parent
TEAM, RUNS, KNOWN, EXTRA = "Atlanta Braves", 3, 26, 15
SPLIT = ROOT / "runs" / "braves-split.json"
K_GRID = [0.5 + 0.25 * i for i in range(23)]


def state(g: dict[str, Any]) -> dict[str, str]:
    return {"league": "MLB", "game": g["matchup"], "starts": g["start"][:16].replace("T", " ") + " UTC", "today": g["start"][:10]}


def ask(st: dict[str, str], qs: dict[str, Any]) -> dict[str, Any]:
    import jev
    return jev.ask(st, qs)["answers"]


def noul(team: str, other: str) -> dict[str, Any]:
    return {"type": "noul", "instructions": f"Will the {team} win this game?",
            "criteria": {"true": f"The {team} win the game.", "false": f"The {team} lose; the {other} win."}}


def v0(g):
    return float(ask(state(g), {"q": noul(TEAM, g["opponent"])})["q"]["noul"])


def v1(g):
    a = ask(state(g), {"b": noul(TEAM, g["opponent"]), "o": noul(g["opponent"], TEAM)})
    return (float(a["b"]["noul"]) + 1 - float(a["o"]["noul"])) / 2


def choice(g, order, instr="Who wins this game?"):
    crit = {t: {"what": f"The {t} win the game."} for t in order}
    p = ask(state(g), {"c": {"type": "choice", "instructions": instr, "criteria": crit}})["c"]["probabilities"]
    return float(p[TEAM]) / (float(p[TEAM]) + float(p[g["opponent"]]))


def v2(g):
    return (choice(g, [TEAM, g["opponent"]]) + choice(g, [g["opponent"], TEAM])) / 2


def v3(g):
    def bins(team):
        return {"type": "score", "instructions": f"How likely is it that the {team} win this game?", "criteria": [l for l, _ in BINS]}
    a = ask(state(g), {"b": bins(TEAM), "o": bins(g["opponent"])})
    get = lambda k: [float(a[k]["probabilities"].get(str(i), a[k]["probabilities"].get(i, 0.0))) for i in range(len(BINS))]
    return (summarise_bins(get("b"))["forecast"] + 1 - summarise_bins(get("o"))["forecast"]) / 2


def v4(g):
    import braves
    return (braves.ask_jev_forced(g, TEAM) + 1 - braves.ask_jev_forced(g, g["opponent"])) / 2


def v5(g):
    instr = ("Who wins this game? Judge each team's typical strength as a club; a single baseball game is close to a "
             "coin flip, so lean only as far as the difference in strength justifies.")
    return (choice(g, [TEAM, g["opponent"]], instr) + choice(g, [g["opponent"], TEAM], instr)) / 2


STRENGTH_LEVELS = ["Rebuilding: one of the weakest clubs in the league",
                   "Below average: more likely to lose than win against a typical opponent",
                   "Average: a .500-type club",
                   "Good: a playoff-calibre club",
                   "Elite: a championship contender and one of the best clubs in baseball"]


def v6(g):
    """Composite scoring (docs pattern): one atomic Score per team, combined in code. Returns the raw strength
    difference in level units (-4..4); fit_k maps it to a probability with a logistic slope fitted on tuning."""
    def q(team):
        return {"type": "score", "instructions": f"How strong is the {team} as a baseball club?", "criteria": STRENGTH_LEVELS}
    a = ask({"league": "MLB", "teams": [TEAM, g["opponent"]], "today": g["start"][:10]}, {"b": q(TEAM), "o": q(g["opponent"])})
    return float(a["b"]["score"]) - float(a["o"]["score"])


VARIANTS: dict[str, Callable[[dict], float]] = {"V0 plain": v0, "V1 both-sides": v1, "V2 neutral-choice": v2,
                                                "V3 bins": v3, "V4 forced-60/40": v4, "V5 strength": v5,
                                                "V6 composite": v6}
DIFF_VARIANTS = {"V6 composite"}        # outputs a strength difference, mapped by a fitted logistic slope


def brier(p: list[float], y: list[int]) -> float:
    return statistics.mean((a - b) ** 2 for a, b in zip(p, y))


def stretch(p: float, k: float, diff: bool = False) -> float:
    """Confidence map fitted on tuning: a linear stretch around 0.5 for probabilities, a logistic for differences."""
    import math
    x = 1 / (1 + math.exp(-k * p)) if diff else 0.5 + k * (p - 0.5)
    return min(max(x, 0.02), 0.98)


def fit_k(p: list[float], y: list[int], diff: bool = False) -> float:
    return min(K_GRID, key=lambda k: brier([stretch(x, k, diff) for x in p], y))


def run_variant(name: str, games: list[dict]) -> list[float]:
    runs = []
    for _ in range(RUNS):
        with ThreadPoolExecutor(3) as pool:
            runs.append(list(pool.map(VARIANTS[name], games)))
    return [statistics.mean(xs) for xs in zip(*runs)]


def score_line(label: str, p: list[float], y: list[int]) -> str:
    picks = sum((x >= 0.5) == bool(t) for x, t in zip(p, y))
    return f"{label:26} picks {picks:2}/{len(y)} ({picks / len(y):.0%})  Brier {brier(p, y):.3f}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("split", "tune", "holdout"))
    cmd = ap.parse_args().cmd
    games = json.loads((ROOT / "runs" / "braves-season.json").read_text())["rows"]
    if cmd == "split":
        if SPLIT.exists():
            raise SystemExit(f"{SPLIT.name} exists; the split is frozen")
        tuning, hold = games[-(KNOWN + EXTRA):], games[: -(KNOWN + EXTRA)]
        SPLIT.write_text(json.dumps({"tuning": [g["id"] for g in tuning], "holdout": [g["id"] for g in hold]}, indent=1))
        print(f"tuning {len(tuning)} ({tuning[0]['start'][:10]} to {tuning[-1]['start'][:10]}); "
              f"hold-out {len(hold)} ({hold[0]['start'][:10]} to {hold[-1]['start'][:10]})")
        return
    split = json.loads(SPLIT.read_text())
    by_id = {g["id"]: g for g in games}
    if cmd == "tune":
        tune = [by_id[i] for i in split["tuning"]]
        y = [int(g["braves_won"]) for g in tune]
        print(score_line("Polymarket", [g["market_p"] for g in tune], y))
        print(score_line("coin flip", [0.5] * len(y), y))
        results = {}
        for name in VARIANTS:
            raw = run_variant(name, tune)
            diff = name in DIFF_VARIANTS
            k = fit_k(raw, y, diff)
            p = [stretch(x, 1.0, True) for x in raw] if diff else raw          # unfitted view for the raw columns
            results[name] = {"raw": raw, "p": p, "k": k, "diff": diff, "brier_raw": brier(p, y),
                             "brier_stretched": brier([stretch(x, k, diff) for x in raw], y)}
            print(score_line(name, p, y) + f"  | fitted k={k:.2f}: Brier {results[name]['brier_stretched']:.3f}"
                  f"  range {min(p):.2f}-{max(p):.2f}  corr w/ market {statistics.correlation(p, [g['market_p'] for g in tune]):+.2f}")
        best = min(results, key=lambda n: results[n]["brier_stretched"])
        (ROOT / "runs" / "braves-tune.json").write_text(json.dumps({"best": best, "results": results}, indent=1))
        print(f"\nselected (lowest stretched Brier on tuning): {best}, k={results[best]['k']:.2f}")
    else:
        tuned = json.loads((ROOT / "runs" / "braves-tune.json").read_text())
        best, k = tuned["best"], tuned["results"][tuned["best"]]["k"]
        diff = tuned["results"][best]["diff"]
        hold = [by_id[i] for i in split["holdout"]]
        y = [int(g["braves_won"]) for g in hold]
        raw = run_variant(best, hold)
        p = [stretch(x, 1.0, True) for x in raw] if diff else raw
        ps = [stretch(x, k, diff) for x in raw]
        (ROOT / "runs" / "braves-holdout.json").write_text(json.dumps({"variant": best, "k": k, "p": p, "ids": split["holdout"]}, indent=1))
        print(f"hold-out, {len(hold)} games, scored once")
        print(score_line("Polymarket", [g["market_p"] for g in hold], y))
        print(score_line("coin flip", [0.5] * len(y), y))
        print(score_line(f"{best} (raw)", p, y))
        print(score_line(f"{best} (k={k:.2f})", ps, y))
        print(score_line("always pick Braves", [1.0] * len(y), y).split("  Brier")[0])


if __name__ == "__main__":
    main()
