"""Experiment 6: search over how Jev is asked (question type, instructions, criteria, state) for the request that
picks 172 Braves games as well as Polymarket does, consistently, with Jev blind to everything but the matchup.

Target (option a, chosen by the user): in EACH of four chronological blocks of 43 games, Jev's pick accuracy >= the
market's pick accuracy in that block (market picks the side priced >= 50%: 70 / 58 / 58 / 53%). Fitness = the worst
block's margin over the market (ties: overall accuracy). A config's pick cut-off for a block is fitted on the other
three blocks, so Jev's lean toward the Braves is removed and only the ORDER it puts the games in can score.

A config chooses one value per knob (Jev's inputs never include prices, results or game facts):
  qtype   noul_braves | noul_both | choice_both_orders | score_strength | score_bins
  style   six instruction wordings
  crit    three criteria variants per question type (descriptions, detail, number of Score levels)
  state   object with date | plain string | object without date
Each yields a raw "Braves-ness" r per game; the pick is Braves when r >= the fitted cut-off.

Independence: every evaluation is a fresh pass over all 172 games. Each request is stateless (no cache, no uid, no
session); Jev never sees another game, an earlier answer, a score or an iteration. Only the search uses scores.

Loop: 20 random seeds; then each iteration changes one knob of a top-5 config (75%) or crosses two (25%), and runs it.
Any config in the top 5 is re-run with fresh calls until it has RERUNS runs and is ranked on the mean of its runs, so a
lucky single run cannot hold the top. Report: leaderboard, per-setting breakdown, run-to-run agreement, and a null
control (every config re-scored on shuffled outcomes; no extra Jev calls).

    .venv/bin/python braves_opt.py run --iterations 220      # resumable; state in runs/braves-opt/
    .venv/bin/python braves_opt.py report
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from analyze import spearman

ROOT = Path(__file__).parent
OUT = ROOT / "runs" / "braves-opt"
TEAM, BLOCKS, SEEDS, TOPK, RERUNS, WORKERS = "Atlanta Braves", 4, 20, 5, 3, 8

QTYPES = ["noul_braves", "noul_both", "choice_both_orders", "score_strength", "score_bins"]
STYLES = {
    "plain": "",
    "strength": "Judge which club is the stronger team.",
    "form": "Consider each club's recent form and momentum.",
    "favourite": "Consider which team would be the favourite in this matchup.",
    "coinflip": "A single baseball game is close to a coin flip; lean only as far as the difference between the clubs justifies.",
    "venue": "Consider home-field advantage and travel for this matchup.",
}
CRITS = ["plain", "detailed", "boundary"]
STATES = ["object", "string", "object_nodate"]
KNOBS = {"qtype": QTYPES, "style": list(STYLES), "crit": CRITS, "state": STATES}

STRENGTH = {"plain": ["Weak club", "Average club", "Strong club"],
            "detailed": ["Rebuilding: one of the weakest clubs", "Below average", "Average: a .500-type club",
                         "Good: a playoff-calibre club", "Elite: a championship contender"],
            "boundary": ["Clearly among the worst clubs in baseball", "Worse than most clubs", "Slightly below average",
                         "About average", "Slightly above average", "Better than most clubs", "Clearly among the best clubs in baseball"]}
BINS = {"plain": [("Very unlikely", .1), ("Unlikely", .3), ("Even", .5), ("Likely", .7), ("Very likely", .9)],
        "detailed": [("Under 30%: clear underdog", .2), ("30-45%: slight underdog", .375), ("45-55%: toss-up", .5),
                     ("55-70%: slight favourite", .625), ("Over 70%: clear favourite", .8)],
        "boundary": [("Will almost certainly lose", .1), ("Probably loses", .3), ("Could go either way", .5),
                     ("Probably wins", .7), ("Will almost certainly win", .9)]}


def key(cfg: dict[str, str]) -> str:
    return "|".join(cfg[k] for k in KNOBS)


def state(g: dict[str, Any], shape: str) -> Any:
    if shape == "string":
        return f"MLB game: {g['matchup']}, {g['start'][:10]}."
    s = {"league": "MLB", "game": g["matchup"]}
    if shape == "object":
        s.update({"starts": g["start"][:16].replace("T", " ") + " UTC", "today": g["start"][:10]})
    return s


def instr(base: str, style: str) -> str:
    return f"{base} {STYLES[style]}".strip()


def noul(team: str, other: str, style: str, crit: str) -> dict[str, Any]:
    q = {"type": "noul", "instructions": instr(f"Will the {team} win this game?", style)}
    if crit == "detailed":
        q["criteria"] = {"true": f"The {team} win the game (final score, including extra innings).",
                         "false": f"The {team} lose the game; the {other} win."}
    elif crit == "boundary":
        q["criteria"] = {"true": f"The {team} finish the game with more runs than the {other}.",
                         "false": f"The {team} finish with fewer runs; a postponed or suspended game does not count as a win."}
    return q


def choice(order: list[str], style: str, crit: str) -> dict[str, Any]:
    desc = {"plain": "win the game.", "detailed": "win this game, by the final score.",
            "boundary": "finish the game with more runs than their opponent."}[crit]
    return {"type": "choice", "instructions": instr("Who wins this game?", style),
            "criteria": {t: {"what": f"The {t} {desc}"} for t in order}}


def requests_for(cfg: dict[str, str], g: dict[str, Any]) -> list[tuple[Any, dict[str, Any]]]:
    """The Jev requests (state, questions) a config makes for one game."""
    st, opp, s, c = state(g, cfg["state"]), g["opponent"], cfg["style"], cfg["crit"]
    t = cfg["qtype"]
    if t == "noul_braves":
        return [(st, {"b": noul(TEAM, opp, s, c)})]
    if t == "noul_both":
        return [(st, {"b": noul(TEAM, opp, s, c), "o": noul(opp, TEAM, s, c)})]
    if t == "choice_both_orders":
        return [(st, {"c": choice([TEAM, opp], s, c)}), (st, {"c": choice([opp, TEAM], s, c)})]
    if t == "score_strength":
        lv = STRENGTH[c]
        mk = lambda team: {"type": "score", "instructions": instr(f"How strong is the {team} as a baseball club?", s), "criteria": lv}
        return [(st, {"b": mk(TEAM), "o": mk(opp)})]
    lv = [l for l, _ in BINS[c]]
    mk = lambda team: {"type": "score", "instructions": instr(f"How likely is it that the {team} win this game?", s), "criteria": lv}
    return [(st, {"b": mk(TEAM), "o": mk(opp)})]


def braves_value(cfg: dict[str, str], answers: list[dict[str, Any]]) -> float:
    t = cfg["qtype"]
    if t == "noul_braves":
        return float(answers[0]["b"]["noul"])
    if t == "noul_both":
        return (float(answers[0]["b"]["noul"]) + 1 - float(answers[0]["o"]["noul"])) / 2
    if t == "choice_both_orders":
        ps = [float(a["c"]["probabilities"][TEAM]) for a in answers]
        return sum(ps) / len(ps)
    if t == "score_strength":
        return float(answers[0]["b"]["score"]) - float(answers[0]["o"]["score"])
    mids = [m for _, m in BINS[cfg["crit"]]]
    ev = lambda a: sum(float(a["probabilities"].get(str(i), a["probabilities"].get(i, 0.0))) * m for i, m in enumerate(mids))
    return ev(answers[0]["b"]) - ev(answers[0]["o"])


def ask(st: Any, qs: dict[str, Any]) -> dict[str, Any]:
    """One fresh, stateless Jev request: no cache, no uid, no session, nothing from earlier games or iterations."""
    import jev
    return jev.ask(st, qs)["answers"]


def blocks(n: int) -> list[list[int]]:
    size = -(-n // BLOCKS)
    return [list(range(i, min(i + size, n))) for i in range(0, n, size)]


def cutoff(r: list[float], y: list[int]) -> float:
    """The cut-off t maximising picks right for "Braves when r >= t" (lowest t on ties; above max = never Braves)."""
    pairs, pos = sorted(zip(r, y)), sum(y)
    best, best_t, neg_below, pos_below, i = -1, 0.0, 0, 0, 0
    while i < len(pairs):
        v = pairs[i][0]
        if neg_below + pos - pos_below > best:
            best, best_t = neg_below + pos - pos_below, v
        while i < len(pairs) and pairs[i][0] == v:
            neg_below += 1 - pairs[i][1]
            pos_below += pairs[i][1]
            i += 1
    return float("inf") if neg_below > best else best_t


def cv_picks(r: list[float], y: list[int]) -> list[bool]:
    """Picks per game, each block's cut-off fitted on the other three blocks."""
    picks = [False] * len(r)
    for b in blocks(len(r)):
        bs = set(b)
        t = cutoff([r[i] for i in range(len(r)) if i not in bs], [y[i] for i in range(len(r)) if i not in bs])
        for i in b:
            picks[i] = r[i] >= t
    return picks


def block_acc(picks: list[bool], y: list[int]) -> list[float]:
    return [sum(picks[i] == bool(y[i]) for i in b) / len(b) for b in blocks(len(y))]


def score(runs: list[list[float]], y: list[int], market: list[float]) -> dict[str, Any]:
    """A config's per-block accuracy (mean over its runs), margin over the market, and share of Braves picks."""
    per_run = [cv_picks(r, y) for r in runs]
    accs = [statistics.mean(a) for a in zip(*(block_acc(p, y) for p in per_run))]
    mk = block_acc([m >= 0.5 for m in market], y)
    margin = min(a - m for a, m in zip(accs, mk))
    overall = statistics.mean(accs)
    return {"blocks": accs, "overall": overall, "margin": margin, "fitness": (margin, overall),
            "braves_rate": statistics.mean(sum(p) / len(p) for p in per_run), "consistent": margin >= 0}


def evaluate(cfg: dict[str, str], games: list[dict]) -> list[float]:
    """One independent run: fresh Jev calls for every game. Raw answers kept as an audit trail (never read back)."""
    def one(g):
        answers = [ask(st, qs) for st, qs in requests_for(cfg, g)]
        return braves_value(cfg, answers), answers
    with ThreadPoolExecutor(WORKERS) as pool:
        out = list(pool.map(one, games))
    with (OUT / "answers.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"cfg": cfg, "answers": [a for _, a in out]}) + "\n")
    return [v for v, _ in out]


def load() -> tuple[list[dict], list[int], list[float], dict[str, dict]]:
    games = json.loads((ROOT / "runs" / "braves-season.json").read_text())["rows"]
    pop: dict[str, dict] = {}
    log = OUT / "log.jsonl"
    for line in (log.open(encoding="utf-8") if log.exists() else []):
        e = json.loads(line)
        pop.setdefault(key(e["cfg"]), {"cfg": e["cfg"], "iteration": e["iteration"], "runs": []})["runs"].append(e["r"])
    return games, [int(g["braves_won"]) for g in games], [g["market_p"] for g in games], pop


def ranked(pop: dict[str, dict], y: list[int], market: list[float]) -> list[dict]:
    for e in pop.values():
        e.update(score(e["runs"], y, market))
    return sorted(pop.values(), key=lambda e: e["fitness"], reverse=True)


def mutate(top: list[dict], rng: random.Random, seen: set[str]) -> dict[str, str]:
    for _ in range(200):
        if rng.random() < 0.25 and len(top) > 1:                      # crossover of two top configs
            a, b = rng.sample(top, 2)
            cfg = {k: rng.choice([a["cfg"][k], b["cfg"][k]]) for k in KNOBS}
        else:                                                         # change one knob of one top config
            cfg = dict(rng.choice(top)["cfg"])
            k = rng.choice(list(KNOBS))
            cfg[k] = rng.choice([v for v in KNOBS[k] if v != cfg[k]])
        if key(cfg) not in seen:
            return cfg
    return {k: rng.choice(v) for k, v in KNOBS.items()}


def line(e: dict) -> str:
    return (f"{key(e['cfg']):50} runs {len(e['runs'])}  blocks {' '.join(f'{a:.0%}' for a in e['blocks'])}  "
            f"overall {e['overall']:.1%}  margin {e['margin']:+.1%}  Braves-picks {e['braves_rate']:.0%}"
            f"{'  CONSISTENT' if e['consistent'] else ''}")


def run(iterations: int) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    games, y, market, pop = load()
    rng = random.Random(sum(len(e["runs"]) for e in pop.values()))

    def record(cfg: dict[str, str], iteration: int, tag: str) -> None:
        r = evaluate(cfg, games)
        with (OUT / "log.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"cfg": cfg, "iteration": iteration, "r": r}) + "\n")
        e = pop.setdefault(key(cfg), {"cfg": cfg, "iteration": iteration, "runs": []})
        e["runs"].append(r)
        best = ranked(pop, y, market)[0]
        print(f"{tag:9} {line(e)}  | best margin {best['margin']:+.1%}", flush=True)

    while True:
        top = ranked(pop, y, market)[:TOPK]
        short = [e for e in top if len(e["runs"]) < RERUNS]
        if short and len(pop) >= SEEDS:                               # after the seeds, confirm top configs with fresh runs
            record(short[0]["cfg"], short[0]["iteration"], f"rerun {len(short[0]['runs']) + 1}")
            continue
        if len(pop) >= iterations:
            break
        n = len(pop) + 1
        cfg = {k: rng.choice(v) for k, v in KNOBS.items()} if len(pop) < SEEDS else mutate(top, rng, set(pop))
        if key(cfg) not in pop:
            record(cfg, n, f"it {n}")


def report(shuffles: int = 200) -> None:
    games, y, market, pop = load()
    rk = ranked(pop, y, market)
    mk = block_acc([m >= 0.5 for m in market], y)
    print(f"{len(rk)} configs, {sum(len(e['runs']) for e in rk)} independent runs of 172 games\n")
    print(f"  {'Polymarket (target per block)':50} blocks {' '.join(f'{a:.0%}' for a in mk)}  overall {statistics.mean(mk):.1%}")
    ab = block_acc([True] * len(y), y)
    print(f"  {'Always pick the Braves':50} blocks {' '.join(f'{a:.0%}' for a in ab)}  overall {statistics.mean(ab):.1%}")
    print("\nTop 10 (configs in the top 5 have 3 fresh runs; ranked on their mean):")
    for e in rk[:10]:
        print("  " + line(e))
    print(f"\nconsistent (>= market in every block): {sum(e['consistent'] for e in rk)} of {len(rk)}")

    print("\nPer setting (mean over all configs using it; r averaged over runs):")
    print(f"  {'setting':28} {'n':>4} {'overall':>8} {'margin':>8} {'rho mkt':>8} {'rho win':>8} {'Braves%':>8}")
    for e in rk:
        r = [statistics.mean(v) for v in zip(*e["runs"])]
        ok = len(set(r)) > 1
        e["rho_mkt"] = spearman(r, market) if ok else 0.0
        e["rho_win"] = spearman(r, [float(v) for v in y]) if ok else 0.0
    for k, vals in KNOBS.items():
        for v in vals:
            es = [e for e in rk if e["cfg"][k] == v]
            if es:
                m = lambda f: statistics.mean(e[f] for e in es)
                print(f"  {k + '=' + v:28} {len(es):4} {m('overall'):8.1%} {m('margin'):+8.1%} {m('rho_mkt'):+8.2f} "
                      f"{m('rho_win'):+8.2f} {m('braves_rate'):8.0%}")

    multi = [e for e in rk if len(e["runs"]) > 1]
    if multi:
        agree = [spearman(a, b) for e in multi for i, a in enumerate(e["runs"]) for b in e["runs"][i + 1:]
                 if len(set(a)) > 1 and len(set(b)) > 1]
        print(f"\nrun-to-run agreement (same config, fresh calls): mean rank correlation {statistics.mean(agree):+.2f} "
              f"over {len(agree)} pairs from {len(multi)} configs")

    rng, null = random.Random(0), []
    for _ in range(shuffles):
        ys = y[:]
        rng.shuffle(ys)
        null.append(max(score(e["runs"], ys, market)["margin"] for e in rk))
    null.sort()
    best = rk[0]["margin"]
    print(f"\nnull control ({shuffles} shuffles of win/loss, same configs and runs): best margin median {statistics.median(null):+.1%}, "
          f"95th pct {null[int(0.95 * shuffles) - 1]:+.1%}; real best {best:+.1%}; share of shuffles >= real: "
          f"{sum(n >= best for n in null) / shuffles:.2f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("run", "report"))
    ap.add_argument("--iterations", type=int, default=220)
    a = ap.parse_args()
    run(a.iterations) if a.cmd == "run" else report()
