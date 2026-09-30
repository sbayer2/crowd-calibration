"""Score experiment 2 (docs/PREDICTIONS-GAMES.md), pooled over every resolved games snapshot.

    .venv/bin/python analyze_games.py
"""

from __future__ import annotations

import glob
import json
import math
import random
import statistics
from pathlib import Path

from analyze import boot_ci, perm_p, spearman

ROOT = Path(__file__).parent
EPS = 1e-6


def brier(p: list[float], y: list[int]) -> float:
    return statistics.mean((pi - yi) ** 2 for pi, yi in zip(p, y))


def log_loss(p: list[float], y: list[int]) -> float:
    return statistics.mean(-math.log(min(max(pi if yi else 1 - pi, EPS), 1 - EPS)) for pi, yi in zip(p, y))


def paired_brier_ci(p1: list[float], p2: list[float], y: list[int], n: int = 2000, seed: int = 0) -> tuple[float, float]:
    """95% bootstrap CI of Brier(p1) - Brier(p2)."""
    rng = random.Random(seed)
    idx = range(len(y))
    diffs = []
    for _ in range(n):
        s = [rng.choice(idx) for _ in idx]
        diffs.append(brier([p1[i] for i in s], [y[i] for i in s]) - brier([p2[i] for i in s], [y[i] for i in s]))
    diffs.sort()
    return diffs[int(0.025 * n)], diffs[int(0.975 * n) - 1]


def brier_ci(p: list[float], y: list[int], n: int = 2000, seed: int = 0) -> tuple[float, float]:
    rng = random.Random(seed)
    idx = range(len(y))
    vals = sorted(brier([p[i] for i in s], [y[i] for i in s]) for s in ([rng.choice(idx) for _ in idx] for _ in range(n)))
    return vals[int(0.025 * n)], vals[int(0.975 * n) - 1]


def load() -> list[dict]:
    rows = []
    for snap_path in sorted(p for p in (ROOT / "runs").glob("games-2*.json") if not p.stem.endswith("resolved")):
        res_path = snap_path.with_name(snap_path.stem + "-resolved.json")
        if not res_path.exists():
            continue
        snap, res = json.loads(snap_path.read_text()), json.loads(res_path.read_text())["results"]
        arms = {}
        for f in glob.glob(str(ROOT / "runs" / f"*-games-{snap['stamp']}-run*.json")):
            d = json.loads(Path(f).read_text())
            arms.setdefault(d["arm"], []).append(d["answers"])
        for g in snap["games"]:
            if g["id"] not in res or not all(g["id"] in r for runs in arms.values() for r in runs):
                continue
            row = {**g, "y": int(res[g["id"]]["a_won"])}
            for arm, runs in arms.items():
                for key in ("p_a", "p_a_bins", "spread", "framing_gap", "noul_a"):
                    row[f"{arm}_{key}"] = statistics.mean(r[g["id"]][key] for r in runs)
            rows.append(row)
    return rows


def main() -> None:
    rows = load()
    n = len(rows)
    print(f"{n} resolved games with answers from every arm")
    if n < 5:
        return
    y, price = [r["y"] for r in rows], [r["price"] for r in rows]
    arms = sorted({k.split("_p_a")[0] for r in rows for k in r if k.endswith("_p_a")})
    print(f"\n{'forecaster':22} {'Brier':>7} {'95% CI':>17} {'log loss':>9}")
    fc = {"market": price, "coin flip (0.5)": [0.5] * n}
    for arm in arms:
        fc[f"{arm} (both sides)"] = [r[f"{arm}_p_a"] for r in rows]
        fc[f"{arm} (bins)"] = [r[f"{arm}_p_a_bins"] for r in rows]
        fc[f"{arm} (one side)"] = [r[f"{arm}_noul_a"] for r in rows]
    for name, p in fc.items():
        lo, hi = brier_ci(p, y) if len(set(p)) > 1 else (float("nan"), float("nan"))
        print(f"{name:22} {brier(p, y):7.3f} [{lo:6.3f}, {hi:6.3f}] {log_loss(p, y):9.3f}")
    for arm in arms:
        p = [r[f"{arm}_p_a"] for r in rows]
        lo, hi = paired_brier_ci(p, price, y)
        print(f"\n{arm}: agreement with price, Spearman {spearman(p, price):+.2f} (p={perm_p(p, price):.4f})")
        print(f"  Brier({arm}) - Brier(market): {brier(p, y) - brier(price, y):+.3f} [{lo:+.3f}, {hi:+.3f}]")
        err = [abs(pi - yi) for pi, yi in zip(p, y)]
        sp = [r[f"{arm}_spread"] for r in rows]
        print(f"  spread vs |error|: Spearman {spearman(sp, err):+.2f} (p={perm_p(sp, err):.4f})")
        print(f"  framing gap |P(A) - (1 - P(B))|: mean {statistics.mean(r[f'{arm}_framing_gap'] for r in rows):.3f}")
        picks = sum((pi > 0.5) == bool(yi) for pi, yi in zip(p, y) if pi != 0.5)
        print(f"  picked the winner: {picks} of {sum(pi != 0.5 for pi in p)}")
    mk = sum((pi > 0.5) == bool(yi) for pi, yi in zip(price, y) if pi != 0.5)
    print(f"\nmarket picked the winner: {mk} of {sum(pi != 0.5 for pi in price)}")


if __name__ == "__main__":
    main()
