"""Ask each arm about every market in a frozen snapshot. Jev: 3 runs (the gateway alias is unpinned and not
deterministic). openjev: 1 run (deterministic). Output runs/<arm>-<snapshot stamp>-run<k>.json.

    .venv/bin/python run.py --arms jev,openjev            # latest snapshot
    .venv/bin/python run.py --arms jev --limit 2 --tag smoke
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import jev
from questions import jev_questions, state, summarise_bins

ROOT = Path(__file__).parent
RUNS = {"jev": 3, "openjev": 1}


def latest_snapshot() -> Path:
    return sorted((ROOT / "runs").glob("snapshot-*.json"))[-1]


def ask_jev(st: dict[str, str]) -> dict[str, Any]:
    r = jev.ask(st, jev_questions())
    a = r["answers"]
    probs = a["bins"]["probabilities"]
    ordered = [float(probs.get(str(i), probs.get(i, 0.0))) for i in range(len(jev_questions()["bins"]["criteria"]))]
    return {"noul": float(a["yes"]["noul"]), "bins": ordered, "jev_score": a["bins"].get("score"),
            "jev_confidence": a["bins"].get("confidence"), "latency_s": r["latency_s"], "attempts": r["attempts"],
            "model": r.get("model")}


def ask_openjev(st: dict[str, str]) -> dict[str, Any]:
    import openjev_arm
    t0 = time.time()
    noul, bins = openjev_arm.ask(st)
    return {"noul": noul, "bins": bins, "latency_s": round(time.time() - t0, 3), "model": f"openjev@{openjev_arm.REVISION[:7]}"}


def ask_game(arm: str, g: dict[str, Any], today: str) -> dict[str, Any]:
    import game_questions as gq
    st, qs = gq.state(g, today), gq.jev_questions(g)
    t0 = time.time()
    if arm == "jev":
        r = jev.ask(st, qs)
        a = r["answers"]
        get = lambda name: [float(a[name]["probabilities"].get(str(i), a[name]["probabilities"].get(i, 0.0)))
                            for i in range(len(qs[name]["criteria"]))]
        res = gq.combine(float(a["win_a"]["noul"]), float(a["win_b"]["noul"]), get("bins_a"), get("bins_b"))
        return {**res, "jev_confidence": (a["bins_a"].get("confidence", 0) + a["bins_b"].get("confidence", 0)) / 2,
                "latency_s": r["latency_s"], "attempts": r["attempts"], "model": r.get("model")}
    import openjev_arm
    a = openjev_arm.ask_questions(st, qs)
    return {**gq.combine(a["win_a"], a["win_b"], a["bins_a"], a["bins_b"]), "latency_s": round(time.time() - t0, 3),
            "model": f"openjev@{openjev_arm.REVISION[:7]}"}


def run_games(args) -> None:
    path = args.snapshot or sorted(p for p in (ROOT / "runs").glob("games-2*.json") if not p.stem.endswith("resolved"))[-1]
    snap = json.loads(path.read_text())
    today, gs = snap["fetched_at"][:10], snap["games"][: args.limit]
    for arm in args.arms.split(","):
        for k in range(1, RUNS[arm] + 1):
            t0 = time.time()
            with ThreadPoolExecutor(args.jev_concurrency if arm == "jev" else 1) as pool:
                answers = list(pool.map(lambda g: ask_game(arm, g, today), gs))
            out = ROOT / "runs" / f"{arm}-games-{snap['stamp']}{'-' + args.tag if args.tag else ''}-run{k}.json"
            out.write_text(json.dumps({"arm": arm, "run": k, "snapshot": path.name, "date": time.strftime("%Y-%m-%d %H:%M:%S"),
                                       "answers": {g["id"]: a for g, a in zip(gs, answers)}}, indent=1))
            print(f"{arm} run{k}: {len(gs)} games in {time.time() - t0:.0f}s -> {out.name}", flush=True)


def run_history(args) -> None:
    """Experiment 4: each resolved market asked as of its horizon date (7 days before it closed), blind to the result.
    openjev answers every k-th market per window (deterministic subsample, --openjev-per-window)."""
    path = args.snapshot or sorted((ROOT / "runs").glob("history-2*.json"))[-1]
    snap = json.loads(path.read_text())
    ms = snap["markets"][: args.limit]
    for arm in args.arms.split(","):
        todo = ms
        if arm == "openjev":
            by: dict[str, list] = {}
            for m in ms:
                by.setdefault(m["window"], []).append(m)
            todo = [m for w in by.values() for m in w[:: max(1, -(-len(w) // args.openjev_per_window))]]
        fn = ask_jev if arm == "jev" else ask_openjev
        for k in range(1, RUNS[arm] + 1):
            out = ROOT / "runs" / f"{arm}-history-{snap['stamp']}{'-' + args.tag if args.tag else ''}-run{k}.json"
            done = json.loads(out.read_text())["answers"] if out.exists() else {}
            rest = [m for m in todo if m["id"] not in done]
            t0 = time.time()
            with ThreadPoolExecutor(args.jev_concurrency if arm == "jev" else 1) as pool:
                for m, a in zip(rest, pool.map(lambda m: fn(state(m, m["horizon_at"][:10])), rest)):
                    done[m["id"]] = {**a, **summarise_bins(a["bins"])}
                    if arm == "openjev" and len(done) % 20 == 0:      # resumable: save as it goes
                        out.write_text(json.dumps({"arm": arm, "run": k, "snapshot": path.name, "answers": done}))
            out.write_text(json.dumps({"arm": arm, "run": k, "snapshot": path.name,
                                       "date": time.strftime("%Y-%m-%d %H:%M:%S"), "answers": done}, indent=1))
            print(f"{arm} run{k}: {len(done)} of {len(todo)} markets ({len(rest)} new) in {time.time() - t0:.0f}s -> {out.name}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", type=Path)
    ap.add_argument("--arms", default="jev,openjev")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--tag", default="")
    ap.add_argument("--jev-concurrency", type=int, default=2)
    ap.add_argument("--set", choices=("markets", "games", "history"), default="markets")
    ap.add_argument("--openjev-per-window", type=int, default=30)
    args = ap.parse_args()
    if args.set == "games":
        return run_games(args)
    if args.set == "history":
        return run_history(args)
    snap_path = args.snapshot or latest_snapshot()
    snap = json.loads(snap_path.read_text())
    today = snap["fetched_at"][:10]
    markets = snap["markets"][: args.limit]
    for arm in args.arms.split(","):
        fn = ask_jev if arm == "jev" else ask_openjev
        for k in range(1, RUNS[arm] + 1):
            t0 = time.time()
            with ThreadPoolExecutor(args.jev_concurrency if arm == "jev" else 1) as pool:
                answers = list(pool.map(lambda m: fn(state(m, today)), markets))
            out = {m["id"]: {**a, **summarise_bins(a["bins"])} for m, a in zip(markets, answers)}
            path = ROOT / "runs" / f"{arm}-{snap['stamp']}{'-' + args.tag if args.tag else ''}-run{k}.json"
            path.write_text(json.dumps({"arm": arm, "run": k, "snapshot": snap_path.name,
                                        "date": time.strftime("%Y-%m-%d %H:%M:%S"), "answers": out}, indent=1))
            print(f"{arm} run{k}: {len(out)} markets in {time.time() - t0:.0f}s -> {path.name}", flush=True)


if __name__ == "__main__":
    main()
