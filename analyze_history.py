"""Score experiment 4 (the seams study), as docs/PREDICTIONS-HISTORY.md specifies.

    .venv/bin/python analyze_history.py

Per window (the quarter a market closed in; "post-release" = after 2026-09-15, outcomes Jev cannot have seen):
Brier and AUC against the outcome for the crowd's price 7 days out, Jev's forecast and P(yes), and a coin flip.
  Seam 1  cutoff: Jev's Brier and AUC by window, against the crowd's
  Seam 2  crowd confidently wrong (price >= 0.8 resolved No, or <= 0.2 resolved Yes): does Jev side with the
          outcome or with the price? Compared with crowd-confidently-right markets as the baseline
  Seam 3  longshots (price < 0.15): realised Yes rate against the mean price and Jev's mean forecast
  Seam 4  calibration of Jev's forecast against outcomes, pre- vs post-release
"""

from __future__ import annotations

import glob
import json
import statistics
from collections import defaultdict
from pathlib import Path

from analyze import boot_ci, spearman
from analyze_games import brier

ROOT = Path(__file__).parent


def auc(score: list[float], y: list[int]) -> float:
    pos = [s for s, t in zip(score, y) if t]
    neg = [s for s, t in zip(score, y) if not t]
    if not pos or not neg:
        return float("nan")
    return sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg))


def load() -> tuple[dict, list[dict]]:
    snap_path = sorted((ROOT / "runs").glob("history-2*.json"))[-1]
    snap = json.loads(snap_path.read_text())
    arms: dict[str, list[dict]] = defaultdict(list)
    for f in sorted(glob.glob(str(ROOT / "runs" / f"*-history-{snap['stamp']}-run*.json"))):
        d = json.loads(Path(f).read_text())
        arms[d["arm"]].append(d["answers"])
    rows = []
    for m in snap["markets"]:
        r = {**m, "y": int(m["yes_won"])}
        for arm, runs in arms.items():
            got = [run[m["id"]] for run in runs if m["id"] in run]
            if got:
                r[f"{arm}_forecast"] = statistics.mean(g["forecast"] for g in got)
                r[f"{arm}_noul"] = statistics.mean(g["noul"] for g in got)
                r[f"{arm}_spread"] = statistics.mean(g["spread"] for g in got)
        rows.append(r)
    return snap, rows


def table(rows: list[dict], arms: list[str]) -> None:
    by = defaultdict(list)
    for r in rows:
        by[r["window"]].append(r)
    order = sorted(by, key=lambda w: (w == "post-release", w))
    print(f"{'window':16} {'n':>4} {'Yes%':>5} | {'Brier: crowd':>12} " + " ".join(f"{a:>10}" for a in arms)
          + f" {'coin':>6} | {'AUC: crowd':>10} " + " ".join(f"{a:>10}" for a in arms))
    for w in order:
        rs = by[w]
        y = [r["y"] for r in rs]
        cells = [f"{brier([r['price'] for r in rs], y):12.3f}"]
        aucs = [f"{auc([r['price'] for r in rs], y):10.2f}"]
        for a in arms:
            sub = [r for r in rs if f"{a}_forecast" in r]
            cells.append(f"{brier([r[a + '_forecast'] for r in sub], [r['y'] for r in sub]):10.3f}" if sub else f"{'-':>10}")
            aucs.append(f"{auc([r[a + '_forecast'] for r in sub], [r['y'] for r in sub]):10.2f}" if sub else f"{'-':>10}")
        print(f"{w:16} {len(rs):4} {statistics.mean(y):5.0%} | " + " ".join(cells) + f" {0.25:6.3f} | " + " ".join(aucs))


def main() -> None:
    snap, rows = load()
    arms = [a for a in ("jev", "openjev") if any(f"{a}_forecast" in r for r in rows)]
    print(f"history snapshot {snap['stamp']}: {len(rows)} resolved markets; arms {arms}\n")
    print("Seam 1 — accuracy by the quarter the market closed (lower Brier / higher AUC = better)")
    table(rows, arms)

    for a in arms:
        rs = [r for r in rows if f"{a}_forecast" in r]
        pre = [r for r in rs if r["window"] != "post-release"]
        post = [r for r in rs if r["window"] == "post-release"]
        f, p = [r[a + "_forecast"] for r in rs], [r["price"] for r in rs]
        lo, hi = boot_ci(f, p)
        print(f"\n== {a}: agreement with the crowd's price, Spearman {spearman(f, p):+.2f} [{lo:+.2f}, {hi:+.2f}];"
              f" with the outcome, AUC {auc(f, [r['y'] for r in rs]):.2f}")
        for label, sub in (("pre-release", pre), ("post-release", post)):
            if sub:
                print(f"   {label:12} n={len(sub):4}  Brier {a} {brier([r[a + '_forecast'] for r in sub], [r['y'] for r in sub]):.3f}"
                      f"  crowd {brier([r['price'] for r in sub], [r['y'] for r in sub]):.3f}")

        print(f"\n   Seam 2 — when the crowd was confidently wrong, which side does {a} take?")
        for label, cond in (("crowd confidently WRONG", lambda r: (r["price"] >= 0.8 and not r["y"]) or (r["price"] <= 0.2 and r["y"])),
                            ("crowd confidently right", lambda r: (r["price"] >= 0.8 and r["y"]) or (r["price"] <= 0.2 and not r["y"]))):
            sub = [r for r in pre if cond(r)]
            if not sub:
                print(f"     {label:24} none")
                continue
            p_out = [r[a + "_forecast"] if r["y"] else 1 - r[a + "_forecast"] for r in sub]   # Jev's P(what happened)
            sides = sum(x > 0.5 for x in p_out)
            print(f"     {label:24} n={len(sub):3}  {a} sided with the OUTCOME on {sides} ({sides / len(sub):.0%}), "
                  f"mean P(outcome) {statistics.mean(p_out):.2f}")

        print(f"\n   Seam 3 — longshots (crowd price < 0.15, pre-release)")
        ls = [r for r in pre if r["price"] < 0.15]
        if ls:
            print(f"     n={len(ls)}  crowd mean {statistics.mean(r['price'] for r in ls):.3f}  {a} mean "
                  f"{statistics.mean(r[a + '_forecast'] for r in ls):.3f}  actually happened {statistics.mean(r['y'] for r in ls):.3f}")

        print(f"\n   Seam 4 — calibration of {a}'s forecast (bins: mean forecast -> share that happened, n)")
        for label, sub in (("pre-release", pre), ("post-release", post)):
            bins = defaultdict(list)
            for r in sub:
                bins[min(int(r[a + "_forecast"] * 5), 4)].append(r)
            print(f"     {label:12} " + "  ".join(
                f"{statistics.mean(r[a + '_forecast'] for r in b):.2f}->{statistics.mean(r['y'] for r in b):.2f} (n={len(b)})"
                for _, b in sorted(bins.items())))
        err = [abs(r[a + "_forecast"] - r["y"]) for r in rs]
        print(f"   confidence: Spearman(spread, |forecast - outcome|) {spearman([r[a + '_spread'] for r in rs], err):+.2f}")


if __name__ == "__main__":
    main()
