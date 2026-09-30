"""Score the runs against the frozen market prices, as docs/PREDICTIONS.md specifies.

    .venv/bin/python analyze.py                      # latest snapshot, all arms found
"""

from __future__ import annotations

import argparse
import glob
import json
import random
import statistics
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
N_PERM, N_BOOT, SEED = 10_000, 2_000, 0


def ranks(x: list[float]) -> list[float]:
    order = sorted(range(len(x)), key=lambda i: x[i])
    r = [0.0] * len(x)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and x[order[j + 1]] == x[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2
        i = j + 1
    return r


def spearman(a: list[float], b: list[float]) -> float:
    return statistics.correlation(ranks(a), ranks(b))


def perm_p(a: list[float], b: list[float], n: int = N_PERM, seed: int = SEED) -> float:
    """One-sided permutation p-value for Spearman rho > 0 (H0: forecasts are unrelated to prices)."""
    rng = random.Random(seed)
    ra, rb = ranks(a), ranks(b)
    obs = statistics.correlation(ra, rb)
    rb = rb[:]
    hits = 0
    for _ in range(n):
        rng.shuffle(rb)
        hits += statistics.correlation(ra, rb) >= obs
    return (hits + 1) / (n + 1)


def boot_ci(a: list[float], b: list[float], n: int = N_BOOT, seed: int = SEED) -> tuple[float, float]:
    rng = random.Random(seed)
    idx = range(len(a))
    vals = []
    for _ in range(n):
        s = [rng.choice(idx) for _ in idx]
        xa, xb = [a[i] for i in s], [b[i] for i in s]
        if len(set(xa)) > 1 and len(set(xb)) > 1:
            vals.append(spearman(xa, xb))
    vals.sort()
    return vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals)) - 1]


def load(snapshot: Path) -> tuple[dict, dict[str, list[dict[str, Any]]]]:
    snap = json.loads(snapshot.read_text())
    arms: dict[str, list[dict[str, Any]]] = {}
    for f in sorted(glob.glob(str(ROOT / "runs" / f"*-{snap['stamp']}-run*.json"))):
        d = json.loads(Path(f).read_text())
        arms.setdefault(d["arm"], []).append(d["answers"])
    return snap, arms


def per_market(runs: list[dict[str, Any]], mid: str, key: str) -> float:
    return statistics.mean(r[mid][key] for r in runs)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", type=Path)
    args = ap.parse_args()
    snapshot = args.snapshot or sorted((ROOT / "runs").glob("snapshot-*.json"))[-1]
    snap, arms = load(snapshot)
    markets = snap["markets"]
    contested = [m for m in markets if m["stratum"] == "contested"]
    print(f"snapshot {snap['stamp']}: {len(markets)} markets ({len(contested)} contested); arms "
          + ", ".join(f"{a} x{len(r)}" for a, r in arms.items()) + "\n")

    results: dict[str, Any] = {}
    for arm, runs in arms.items():
        results[arm] = {}
        print(f"== {arm}")
        for label, ms in (("contested", contested), ("all 60", markets)):
            price = [m["price"] for m in ms]
            for readout in ("forecast", "noul"):
                f = [per_market(runs, m["id"], readout) for m in ms]
                rho, (lo, hi), p = spearman(f, price), boot_ci(f, price), perm_p(f, price)
                pear = statistics.correlation(f, price)
                mae = statistics.mean(abs(x - y) for x, y in zip(f, price))
                results[arm][f"{label}/{readout}"] = {"rho": rho, "ci": [lo, hi], "p": p, "pearson": pear, "mae": mae}
                print(f"  {label:9} {readout:8} Spearman {rho:+.2f} [{lo:+.2f}, {hi:+.2f}]  p={p:.4f}  "
                      f"Pearson {pear:+.2f}  mean |error| {mae:.3f}")
        err = [abs(per_market(runs, m["id"], "forecast") - m["price"]) for m in markets]
        spread = [per_market(runs, m["id"], "spread") for m in markets]
        rho_c = spearman(spread, err)
        results[arm]["spread_vs_error"] = {"rho": rho_c, "p": perm_p(spread, err)}
        print(f"  confidence: Spearman(spread, |forecast - price|) {rho_c:+.2f}  p={results[arm]['spread_vs_error']['p']:.4f}"
              "  (positive = confident answers sit closer to the market)")
        agree = spearman([per_market(runs, m["id"], "noul") for m in markets],
                         [per_market(runs, m["id"], "forecast") for m in markets])
        print(f"  noul vs forecast agreement (Spearman, all 60): {agree:+.2f}")
        if len(runs) > 1:
            sd = [statistics.stdev(r[m["id"]]["forecast"] for r in runs) for m in markets]
            print(f"  run-to-run SD of the forecast: mean {statistics.mean(sd):.3f}, max {max(sd):.3f}")
        print("  by stratum: mean price -> mean forecast")
        for s in ("<0.05", "0.05-0.15", "contested", "0.85-0.95", ">0.95"):
            ms = [m for m in markets if m["stratum"] == s]
            if ms:
                print(f"    {s:10} n={len(ms):2}  {statistics.mean(m['price'] for m in ms):.3f} -> "
                      f"{statistics.mean(per_market(runs, m['id'], 'forecast') for m in ms):.3f}")
        print()

    if {"jev", "openjev"} <= set(arms):
        fj = [per_market(arms["jev"], m["id"], "forecast") for m in contested]
        fo = [per_market(arms["openjev"], m["id"], "forecast") for m in contested]
        print(f"Jev vs openjev forecast on contested markets: Spearman {spearman(fj, fo):+.2f}")
    med_err = statistics.median(abs(per_market(arms["jev"], m["id"], "noul") - m["price"]) for m in markets) if "jev" in arms else None
    if med_err is not None:
        print(f"Leakage guard: median |Jev P(yes) - price| over all 60 = {med_err:.3f} "
              f"({'INVESTIGATE before any claim' if med_err < 0.02 else 'no sign of leakage'})")
    (ROOT / "runs" / f"analysis-{snap['stamp']}.json").write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
