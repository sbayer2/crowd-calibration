"""Score experiment 13 (docs/PREDICTIONS-SPREADS.md): NCAA football spreads and totals three days out.

Run `report` once, after the 12-05 games are final. Until then only `counts` is run on the real data (ADC-013).

    .venv/bin/python analyze_spreads.py counts
    .venv/bin/python analyze_spreads.py report              # runs/spreads-analysis/report.json
    .venv/bin/python analyze_spreads.py report --root DIR   # another data tree (tests/test_analyze_spreads.py)

Inputs: runs/ncaaf/t72.jsonl ("market" and "jev" records, written by live_odds.py) and runs/ncaaf/scores.json (ESPN
finals). Margin = away - home throughout. Choices the plan leaves open, fixed before any measure was computed:
  - One market record per game (the first); one Jev record per game (the first).
  - A game counts for the result-based measures (S3, S4, J8) when ESPN has it final. A game ESPN never lists as final
    (postponed, cancelled) is dropped and counted.
  - Market line per measure: Kalshi's when its ladder gave a line, otherwise Polymarket's.
  - Jev's primary line is the median; the expected value is reported as secondary for every Jev measure.
  - S3 holds when |MAE difference| <= 0.5 and its 95% CI includes 0. S4 holds when Jev's MAE exceeds Pinnacle's by
    >= 1.5 and the CI excludes 0. J6 holds when r <= 0.40 and the CI of r(J5) - r(J6) is above 0.
  - J8: Jev's side = away covers when Jev's margin > Pinnacle's line (over when Jev's total > the line). A push (result
    exactly on the line) is left out. 95% Wilson interval for the cover rate.
  - Home term (secondary): h = mean(Jev margin - actual margin) over non-neutral games in the other 5 folds (start
    order); Jev's margin minus h is scored for non-neutral games.
  - Bootstrap: 2000 resamples of games, seed 7, percentile 95% CIs.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).parent
B, SEED, FOLDS, BIG_GAP = 2000, 7, 5, 7.0


def load(root: Path) -> tuple[list[dict[str, Any]], Counter]:
    d = root / "runs" / "ncaaf"
    markets: dict[str, dict] = {}
    jev: dict[str, dict] = {}
    if (d / "t72.jsonl").exists():
        for l in (d / "t72.jsonl").open():
            r = json.loads(l)
            if r["kind"] == "market":
                markets.setdefault(r["id"], r)
            elif r["kind"] == "jev":
                jev.setdefault(r["id"], r)
    scores = json.loads((d / "scores.json").read_text()) if (d / "scores.json").exists() else {}
    rows, notes = [], Counter()
    line = lambda src, k: ((src or {}).get(k) or {}).get("line")
    for gid, m in markets.items():
        sc, pin, j = scores.get(gid, {}), m.get("pinnacle") or {}, jev.get(gid)
        final = bool(sc.get("completed")) and sc.get("away_score") is not None
        notes["final" if final else "not final"] += 1
        row = {"id": gid, "key": m["key"], "start": m["commence"], "away": m["away"], "home": m["home"],
               "late": m.get("late"), "lead_h": m.get("lead_h"), "neutral": sc.get("neutral"),
               "margin": sc["away_score"] - sc["home_score"] if final else None,
               "total": sc["away_score"] + sc["home_score"] if final else None,
               "pin_spread": pin.get("spread"), "pin_total": pin.get("total"),
               "k_spread": line(m.get("kalshi"), "spread"), "k_total": line(m.get("kalshi"), "total"),
               "p_spread": line(m.get("polymarket"), "spread"), "p_total": line(m.get("polymarket"), "total"),
               "jev_margin": j["margin_median"] if j else None, "jev_margin_ev": j["margin_ev"] if j else None,
               "jev_total": j["total_median"] if j else None, "jev_total_ev": j["total_ev"] if j else None}
        row["m_spread"] = row["k_spread"] if row["k_spread"] is not None else row["p_spread"]
        row["m_total"] = row["k_total"] if row["k_total"] is not None else row["p_total"]
        rows.append(row)
    rows.sort(key=lambda r: r["start"])
    return rows, notes


def ci(stat: Callable[[list[int]], float], n: int, rng: random.Random, b: int = B) -> tuple[float, float]:
    out = []
    for _ in range(b):
        try:
            out.append(stat([rng.randrange(n) for _ in range(n)]))
        except (statistics.StatisticsError, ZeroDivisionError):
            continue
    out.sort()
    return (out[int(0.025 * len(out))], out[int(0.975 * len(out)) - 1]) if out else (math.nan, math.nan)


def wilson(k: int, n: int) -> tuple[float, float]:
    if not n:
        return (math.nan, math.nan)
    p, z = k / n, 1.96
    c, h = (p + z * z / (2 * n)) / (1 + z * z / n), z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (c - h, c + h)


def pairs(rows, a, b, need=()):
    sub = [r for r in rows if r[a] is not None and r[b] is not None and all(r[k] is not None for k in need)]
    return sub, [r[a] for r in sub], [r[b] for r in sub]


def agree(rows, a, b, rng, b_=B):
    """Mean absolute difference and Pearson r between two lines."""
    sub, x, y = pairs(rows, a, b)
    if len(sub) < 3:
        return {"n": len(sub)}
    mad = statistics.mean(abs(u - v) for u, v in zip(x, y))
    return {"n": len(sub), "mad": mad, "mad_ci": ci(lambda ix: statistics.mean(abs(x[i] - y[i]) for i in ix), len(sub), rng, b_),
            "r": statistics.correlation(x, y), "r_ci": ci(lambda ix: statistics.correlation([x[i] for i in ix], [y[i] for i in ix]), len(sub), rng, b_)}


def mae_diff(rows, a, b, truth, rng, b_=B):
    """MAE(a) - MAE(b) against the result, paired by game."""
    sub = [r for r in rows if r[a] is not None and r[b] is not None and r[truth] is not None]
    if len(sub) < 3:
        return {"n": len(sub)}
    ea, eb = [abs(r[a] - r[truth]) for r in sub], [abs(r[b] - r[truth]) for r in sub]
    return {"n": len(sub), "mae_a": statistics.mean(ea), "mae_b": statistics.mean(eb),
            "diff": statistics.mean(ea) - statistics.mean(eb),
            "ci": ci(lambda ix: statistics.mean(ea[i] - eb[i] for i in ix), len(sub), rng, b_)}


def cover(rows, jev, line, truth, gap=0.0):
    k = n = 0
    for r in rows:
        if None in (r[jev], r[line], r[truth]) or r[jev] == r[line] or abs(r[jev] - r[line]) < gap or r[truth] == r[line]:
            continue
        n += 1
        k += (r[jev] > r[line]) == (r[truth] > r[line])
    return {"n": n, "rate": k / n if n else math.nan, "ci": wilson(k, n), "holds": n > 0 and wilson(k, n)[0] <= 0.5 <= wilson(k, n)[1]}


def home_term(rows, jev="jev_margin"):
    """Jev's margin minus a home edge fitted out of fold on non-neutral games; None for neutral or unscored games."""
    idx = [i for i, r in enumerate(rows) if not r["neutral"] and r[jev] is not None and r["margin"] is not None]
    out = [None] * len(rows)
    size = -(-len(idx) // FOLDS) if idx else 1
    for s in range(0, len(idx), size):
        test, train = idx[s:s + size], idx[:s] + idx[s + size:]
        if not train:
            continue
        h = statistics.mean(rows[i][jev] - rows[i]["margin"] for i in train)
        for i in test:
            out[i] = rows[i][jev] - h
    return out


def report(root: Path = ROOT, b: int = B, out: Path | None = None) -> dict[str, Any]:
    rng = random.Random(SEED)
    rows, notes = load(root)
    res: dict[str, Any] = {"games": len(rows), "notes": dict(notes),
                           "usable_ladders": {k: sum(r[k] is not None for r in rows) for k in ("k_spread", "k_total", "p_spread", "p_total")},
                           "late": sum(bool(r["late"]) for r in rows)}
    s1k, s1p = agree(rows, "k_spread", "pin_spread", rng, b), agree(rows, "p_spread", "pin_spread", rng, b)
    s2k, s2p = agree(rows, "k_total", "pin_total", rng, b), agree(rows, "p_total", "pin_total", rng, b)
    res["S1"] = {"kalshi": s1k, "polymarket": s1p, "holds": s1k.get("mad", 9) <= 1.0 and s1k.get("r", 0) >= 0.97 and s1p.get("mad", 9) <= 2.0}
    res["S2"] = {"kalshi": s2k, "polymarket": s2p, "holds": s2k.get("mad", 9) <= 1.5 and s2p.get("mad", 9) <= 2.5}
    s3 = mae_diff(rows, "pin_spread", "m_spread", "margin", rng, b)
    s3["holds"] = "diff" in s3 and abs(s3["diff"]) <= 0.5 and s3["ci"][0] <= 0 <= s3["ci"][1]
    res["S3"] = s3
    res["S3 totals (descriptive)"] = mae_diff(rows, "pin_total", "m_total", "total", rng, b)
    for jv in ("jev_margin", "jev_margin_ev"):
        s4 = mae_diff(rows, jv, "pin_spread", "margin", rng, b)
        s4["holds"] = "diff" in s4 and s4["diff"] >= 1.5 and s4["ci"][0] > 0
        res[f"S4 {jv}"] = s4
    for jm, jt in (("jev_margin", "jev_total"), ("jev_margin_ev", "jev_total_ev")):
        sub = [r for r in rows if None not in (r[jm], r[jt], r["pin_spread"], r["pin_total"])]
        if len(sub) < 3:
            res[f"J5-J7 {jm}"] = {"n": len(sub)}
            continue
        r5 = lambda ix: statistics.correlation([sub[i][jm] for i in ix], [sub[i]["pin_spread"] for i in ix])
        r6 = lambda ix: statistics.correlation([sub[i][jt] for i in ix], [sub[i]["pin_total"] for i in ix])
        al = list(range(len(sub)))
        d = ci(lambda ix: r5(ix) - r6(ix), len(sub), rng, b)
        sd = lambda k: statistics.stdev(r[k] for r in sub)
        res[f"J5-J7 {jm}"] = {"n": len(sub), "J5_r": r5(al), "J5_ci": ci(r5, len(sub), rng, b), "J5_holds": r5(al) >= 0.60,
                             "J6_r": r6(al), "J6_ci": ci(r6, len(sub), rng, b), "J5_minus_J6_ci": d,
                             "J6_holds": r6(al) <= 0.40 and d[0] > 0,
                             "sd": {"jev_margin": sd(jm), "pin_spread": sd("pin_spread"), "jev_total": sd(jt), "pin_total": sd("pin_total")},
                             "J7_holds": sd(jm) < sd("pin_spread") and sd(jt) < sd("pin_total")}
    for jm, jt in (("jev_margin", "jev_total"), ("jev_margin_ev", "jev_total_ev")):
        res[f"J8 {jm}"] = {"spread": cover(rows, jm, "pin_spread", "margin"), "total": cover(rows, jt, "pin_total", "total"),
                           "spread_gap7": cover(rows, jm, "pin_spread", "margin", BIG_GAP), "total_gap7": cover(rows, jt, "pin_total", "total", BIG_GAP)}
    st = json.loads((root / "runs" / "ncaaf" / "state.json").read_text()) if (root / "runs" / "ncaaf" / "state.json").exists() else {}
    scope, days = set(st.get("scope", [])), {r["key"].split(":")[1] for r in rows}
    seen12 = {}
    if (root / "runs" / "ncaaf" / "snapshots.jsonl").exists():
        for l in (root / "runs" / "ncaaf" / "snapshots.jsonl").open():
            for e in json.loads(l)["events"]:
                if e["id"] in scope:
                    seen12[e["id"]] = f"{e['away_team']} @ {e['home_team']}", e["commence_time"]
    from live_odds import CT, iso
    res["only_in_13"] = [f"{r['away']} @ {r['home']}" for r in rows if r["id"] not in scope]
    res["only_in_12"] = sorted(n for gid, (n, t) in seen12.items() if gid not in {r["id"] for r in rows}
                               and iso(t).astimezone(CT).date().isoformat() in days)
    adj = home_term(rows)
    for r, a in zip(rows, adj):
        r["jev_margin_home"] = a
    res["S4 jev_margin with home term (secondary)"] = mae_diff(rows, "jev_margin_home", "pin_spread", "margin", rng, b)
    if out:
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res, indent=1, default=lambda x: round(x, 3) if isinstance(x, float) else str(x)))
    return res


def counts(root: Path = ROOT) -> None:
    rows, notes = load(root)
    by: dict[str, list] = {}
    for r in rows:
        by.setdefault(r["key"], []).append(r)
    for k, rs in sorted(by.items()):
        n = lambda f: sum(r[f] is not None for r in rs)
        print(f"{k}: {len(rs)} games | Pinnacle {n('pin_spread')}/{n('pin_total')} | Kalshi lines {n('k_spread')}/{n('k_total')} | "
              f"Polymarket {n('p_spread')}/{n('p_total')} | Jev {n('jev_margin')} | final {n('margin')} | late {sum(bool(r['late']) for r in rs)}")
    print(dict(notes))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("counts", "report"))
    ap.add_argument("--root", type=Path, default=ROOT)
    a = ap.parse_args()
    counts(a.root) if a.cmd == "counts" else report(a.root, out=a.root / "runs" / "spreads-analysis")
