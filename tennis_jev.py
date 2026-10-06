"""Experiment 7: blind Jev on tennis matches, by tier, five question types.

Tennis leaves room to show skill (market AUC 0.78 on tour-level matches vs 0.63 on MLB games), and its tiers split
players Jev should know (tour-level main draws: Slams, ATP/WTA events, Davis/Laver Cup) from players it mostly cannot
(Challengers, ITF, qualifying), which tests what the query can do with and without knowledge.

Sample (frozen to runs/tennis-sample.json): every tour-level match + an equal random sample of lower-level matches,
from runs/matches-tennis.json (45 days to 2026-10-05, singles, volume >= $5k, priced 5 min before scheduled start).
State: sport, tournament, "A vs. B" as Polymarket lists it, date. No price, ranking, seed or result.

Question types (wording and criteria plain; the five from experiment 6, adapted to players):
  noul_a        "Will A win this match?"                        -> P(yes)
  noul_both     yes/no about each player                        -> mean of P(A wins), 1 - P(B wins)
  choice_both   "Who wins this match?", both option orders      -> mean P(A)
  strength      descriptive 5-level Score per player            -> level(A) - level(B)
  bins          5-bin win-likelihood Score per player           -> EV(A) - EV(B)
Every request is fresh and stateless (no cache, no uid). One run per type (experiment 6: run-to-run rank agreement
+0.97).

    .venv/bin/python tennis_jev.py sample
    .venv/bin/python tennis_jev.py run            # resumable; runs/tennis-jev/<type>.jsonl
    .venv/bin/python tennis_jev.py report
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from analyze import ranks, spearman

ROOT = Path(__file__).parent
OUT = ROOT / "runs" / "tennis-jev"
SAMPLE = ROOT / "runs" / "tennis-sample.json"
SEED, WORKERS, BOOT = 7, 8, 2000
TOUR_EVENTS = {"US Open ATP", "US Open WTA", "China Open", "Winston-Salem Open", "Sao Paulo Open", "Korea Open",
               "Chengdu Open", "Hangzhou Open", "Guadalajara Open Akron", "Japan Open Tennis Championships",
               "Monterrey Open", "Singapore Open", "Cincinnati Open", "Davis Cup", "Laver Cup"}
TYPES = ["noul_a", "noul_both", "choice_both", "strength", "bins"]
STRENGTH = ["Unknown or lower-level: plays mainly ITF or Challenger events",
            "Fringe tour-level: around the top 100-200",
            "Solid tour-level: around the top 50-100",
            "Strong: around the top 20-50",
            "Elite: top 10, a Grand Slam contender"]
BINS = [("Very unlikely", .1), ("Unlikely", .3), ("Even", .5), ("Likely", .7), ("Very likely", .9)]


def tournament(m: dict[str, Any]) -> str:
    return m["event"].split(":")[0].strip()


def tier(m: dict[str, Any]) -> str:
    return "tour" if tournament(m) in TOUR_EVENTS else "lower"


def state(m: dict[str, Any]) -> dict[str, str]:
    return {"sport": "Tennis", "tournament": tournament(m), "match": f"{m['a']} vs. {m['b']}", "date": m["start"][:10]}


def noul(p: str, q: str) -> dict[str, Any]:
    return {"type": "noul", "instructions": f"Will {p} win this match?",
            "criteria": {"true": f"{p} wins the match.", "false": f"{p} loses the match; {q} wins."}}


def choice(order: list[str]) -> dict[str, Any]:
    return {"type": "choice", "instructions": "Who wins this match?",
            "criteria": {p: {"what": f"{p} wins the match."} for p in order}}


def score(instr: str, levels: list[str]) -> dict[str, Any]:
    return {"type": "score", "instructions": instr, "criteria": levels}


def requests_for(t: str, m: dict[str, Any]) -> list[dict[str, Any]]:
    a, b = m["a"], m["b"]
    if t == "noul_a":
        return [{"a": noul(a, b)}]
    if t == "noul_both":
        return [{"a": noul(a, b), "b": noul(b, a)}]
    if t == "choice_both":
        return [{"c": choice([a, b])}, {"c": choice([b, a])}]
    if t == "strength":
        q = lambda p: score(f"How strong is {p} as a tennis player?", STRENGTH)
        return [{"a": q(a), "b": q(b)}]
    q = lambda p: score(f"How likely is it that {p} wins this match?", [l for l, _ in BINS])
    return [{"a": q(a), "b": q(b)}]


def value(t: str, m: dict[str, Any], ans: list[dict[str, Any]]) -> dict[str, Any]:
    """The number that favours player A, plus raw parts kept for the report."""
    if t == "noul_a":
        return {"v": float(ans[0]["a"]["noul"])}
    if t == "noul_both":
        return {"v": (float(ans[0]["a"]["noul"]) + 1 - float(ans[0]["b"]["noul"])) / 2}
    if t == "choice_both":
        return {"v": statistics.mean(float(x["c"]["probabilities"][m["a"]]) for x in ans)}
    if t == "strength":
        la, lb = float(ans[0]["a"]["score"]), float(ans[0]["b"]["score"])
        return {"v": la - lb, "level_a": la, "level_b": lb}
    ev = lambda x: sum(float(x["probabilities"].get(str(i), x["probabilities"].get(i, 0.0))) * mid for i, (_, mid) in enumerate(BINS))
    return {"v": ev(ans[0]["a"]) - ev(ans[0]["b"])}


def ask(st: dict[str, str], qs: dict[str, Any]) -> dict[str, Any]:
    """One fresh, stateless Jev request."""
    import jev
    return jev.ask(st, qs)["answers"]


def sample() -> None:
    if SAMPLE.exists():
        raise SystemExit(f"{SAMPLE.name} exists; the sample is frozen")
    rows = json.loads((ROOT / "runs" / "matches-tennis.json").read_text())["rows"]
    tour = [r for r in rows if tier(r) == "tour"]
    lower = random.Random(SEED).sample([r for r in rows if tier(r) == "lower"], len(tour))
    ms = sorted(tour + lower, key=lambda r: r["start"])
    SAMPLE.write_text(json.dumps({"seed": SEED, "rows": [{**r, "tier": tier(r)} for r in ms]}, indent=1))
    print(f"frozen {len(ms)} matches: {len(tour)} tour-level, {len(lower)} lower-level")


def run() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ms = json.loads(SAMPLE.read_text())["rows"]
    for t in TYPES:
        path = OUT / f"{t}.jsonl"
        done = {json.loads(l)["id"] for l in path.open(encoding="utf-8")} if path.exists() else set()
        todo = [m for m in ms if m["id"] not in done]

        def one(m):
            ans = [ask(state(m), qs) for qs in requests_for(t, m)]
            return {"id": m["id"], **value(t, m, ans), "answers": ans}
        with ThreadPoolExecutor(WORKERS) as pool, path.open("a", encoding="utf-8") as fh:
            for i, rec in enumerate(pool.map(one, todo), 1):
                fh.write(json.dumps(rec) + "\n")
                fh.flush()
                if i % 200 == 0:
                    print(f"  {t}: {len(done) + i}/{len(ms)}", flush=True)
        print(f"{t}: done ({len(todo)} new)", flush=True)


def auc(p: list[float], y: list[int]) -> float:
    r, npos = ranks(p), sum(y)
    return (sum(ri for ri, t in zip(r, y) if t) - npos * (npos - 1) / 2) / (npos * (len(y) - npos))


def cv_acc(v: list[float], y: list[int], folds: int = 4) -> float:
    """Pick A when v >= a cut-off fitted on the other folds (folds by start order)."""
    from braves_opt import cutoff
    n, right = len(v), 0
    size = -(-n // folds)
    for s in range(0, n, size):
        test = set(range(s, min(s + size, n)))
        t = cutoff([v[i] for i in range(n) if i not in test], [y[i] for i in range(n) if i not in test])
        right += sum((v[i] >= t) == bool(y[i]) for i in test)
    return right / n


def report() -> None:
    ms = json.loads(SAMPLE.read_text())["rows"]
    vals = {t: {(r := json.loads(l))["id"]: r for l in (OUT / f"{t}.jsonl").open(encoding="utf-8")} for t in TYPES
            if (OUT / f"{t}.jsonl").exists()}
    rng = random.Random(SEED)
    for tr in ("tour", "lower"):
        sub = [m for m in ms if m["tier"] == tr]
        y, mk = [m["a_won"] for m in sub], [m["p_a"] for m in sub]
        print(f"\n{tr}-level: {len(sub)} matches | market: AUC {auc(mk, y):.3f}, picks {statistics.mean((p >= .5) == bool(t) for p, t in zip(mk, y)):.1%}")
        print(f"  {'type':12} {'n':>4} {'AUC':>6} {'mkt-Jev AUC [95% CI]':>24} {'rho mkt':>8} {'picks (CV)':>11}")
        boots = [[rng.randrange(len(sub)) for _ in sub] for _ in range(BOOT)]
        for t, d in vals.items():
            idx = [i for i, m in enumerate(sub) if m["id"] in d]
            if len(idx) < len(sub):
                print(f"  {t:12} {len(idx):4} (incomplete)")
                continue
            v = [d[m["id"]]["v"] for m in sub]
            diffs = sorted(auc([mk[i] for i in b], [y[i] for i in b]) - auc([v[i] for i in b], [y[i] for i in b])
                           for b in boots if 0 < sum(y[i] for i in b) < len(b))
            lo, hi = diffs[int(.025 * len(diffs))], diffs[int(.975 * len(diffs)) - 1]
            print(f"  {t:12} {len(v):4} {auc(v, y):6.3f} {auc(mk, y) - auc(v, y):+9.3f} [{lo:+.3f}, {hi:+.3f}] "
                  f"{spearman(v, mk):+8.2f} {cv_acc(v, y):11.1%}")
        if "strength" in vals:
            lv = [round(vals["strength"][m["id"]][k]) for m in sub for k in ("level_a", "level_b")]     # Score is an expected level
            print(f"  strength level per player, rounded (0 = unknown/lower ... 4 = elite): "
                  + " ".join(f"{i}:{lv.count(i) / len(lv):.0%}" for i in range(5)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("sample", "run", "report"))
    {"sample": sample, "run": run, "report": report}[ap.parse_args().cmd]()
