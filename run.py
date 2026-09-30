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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", type=Path)
    ap.add_argument("--arms", default="jev,openjev")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--tag", default="")
    ap.add_argument("--jev-concurrency", type=int, default=2)
    args = ap.parse_args()
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
