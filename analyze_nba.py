"""Score experiment 14 (NBA moneylines from free sources): docs/PREDICTIONS-NBA.md.

Run `report` once, after the 12-05 games are final. Until then only `counts` is run on the real data: usable games and
drop reasons, no measures (ADC-013).

    .venv/bin/python analyze_nba.py counts
    .venv/bin/python analyze_nba.py report                  # every measure; runs/nba-analysis/report.json
    .venv/bin/python analyze_nba.py report --root DIR       # another data tree (tests/test_analyze_nba.py)

Choices the plan leaves open, fixed here before any measure was computed on real data (2026-10-22):
  - A game's start is the one stored by nba_free.py (the last ESPN listing read before it). Moments: early = 14:00 UTC
    on the game's Central day; T-60 and T-5 = 60 and 5 minutes before the start.
  - Polymarket at a moment: the last 1-minute price at or before it, at most 10 minutes older (analyze_live.poly_at).
  - Kalshi at a moment: the last candle of the away team's market ending at or before it, at most 10 minutes older, with
    0 < bid <= ask < 1 and ask - bid <= 0.10; the price is the midpoint. Otherwise no Kalshi price.
  - Drops, in this order: postponed or cancelled (ESPN status); no Jev answer asked before the start (both configs);
    no unique Polymarket match; no Polymarket price at T-5; no clean result (ESPN final with scores and a resolved
    Polymarket market agreeing on the winner). A Kalshi result that disagrees is counted and leaves the Kalshi measures.
  - E1, E2 and E3 use the usable games with a Kalshi price at T-5 (and, for E3, prices from both at T-60).
  - E2: logistic regression on logit-prices (analyze_live.fit); 5 folds = consecutive blocks in start order; per-game
    out-of-fold log loss; difference = loss(Polymarket + Kalshi) - loss(Polymarket); the CI resamples games. The
    reverse (Polymarket added to Kalshi) is reported the same way.
  - E3: the share of the T-60 gap each closes by T-5, as experiment 9's C3; descriptive.
  - N1: AUC(Jev) - AUC(Polymarket T-5), paired bootstrap; holds when the CI is below 0. N2: rho(Jev, Polymarket
    early) - rho(Jev, Polymarket T-5), paired bootstrap; needs a Polymarket early price. N3: rho(Jev, Polymarket T-5)
    in (0, 0.45].
  - Home edge: Jev's mean noul_both value (the only config on a probability scale), Polymarket's mean T-5 price and the
    share of away wins, all for the away team.
  - X6: rho(Jev, Polymarket T-5) over experiment 12's usable NCAA football games (analyze_live.games) minus the same
    over the NBA games; each sport resampled on its own; holds when the CI is above 0. Verdict only with >= 100 usable
    games in each sport.
  - Verdicts need >= 100 usable NBA games. Bootstrap: 2000 resamples, seed 7, percentile 95% CIs.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import random
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

import analyze_live as L
from analyze import spearman
from tennis_jev import auc

ROOT = Path(__file__).parent
DAYS = ("2026-10-22", "2026-12-05")
CONFIGS = L.CONFIGS
B, SEED, MIN_N, MIN_E3, MAX_SPREAD, STALE = 2000, 7, 100, 30, 0.10, 600
SETTLE = dt.timedelta(hours=3.5)
iso = L.iso


def kalshi_at(candles: list[list], t: dt.datetime) -> float | None:
    ts = t.timestamp()
    ok = [c for c in candles if ts - STALE <= c[0] <= ts]
    if not ok:
        return None
    _, bid, ask, _ = max(ok, key=lambda c: c[0])
    if bid is None or ask is None:
        return None
    bid, ask = float(bid), float(ask)
    return (bid + ask) / 2 if 0 < bid <= ask < 1 and ask - bid <= MAX_SPREAD else None


def games(root: Path, now: dt.datetime | None = None) -> tuple[list[dict[str, Any]], Counter]:
    """Usable NBA games (sorted by start) and the drop counts."""
    d = root / "runs" / "nba"
    st = json.loads((d / "state.json").read_text())
    data = json.loads((d / "data.json").read_text()) if (d / "data.json").exists() else {}
    jev: dict[str, dict] = {}
    if (d / "jev.jsonl").exists():
        for l in (d / "jev.jsonl").open():
            r = json.loads(l)
            jev.setdefault(r["id"], r)
    now = now or dt.datetime.now(dt.timezone.utc)
    rows, drops = [], Counter()
    for gid, g in st["games"].items():
        if not DAYS[0] <= g["day"] <= DAYS[1]:
            continue
        start = iso(g["start"])
        if start > now - SETTLE:
            continue
        rec = data.get(gid, {})
        pm, es, ks = rec.get("poly", {}), rec.get("espn", {}), rec.get("kalshi", {})
        j = jev.get(gid)
        t5, t60, early = start - dt.timedelta(minutes=5), start - dt.timedelta(minutes=60), dt.datetime.combine(
            dt.date.fromisoformat(g["day"]), dt.time(14), dt.timezone.utc)
        hist = pm.get("history_away", [])
        winner = None
        if es.get("completed") and es.get("away_score") not in (None, "") and es.get("home_score") not in (None, ""):
            a, h = int(es["away_score"]), int(es["home_score"])
            winner = int(a > h) if a != h else None
        status = es.get("status") or g.get("status", "")
        reason = ("postponed" if "POSTPONED" in status or "CANCELED" in status else
                  "no Jev answer before the start" if not j or iso(j["asked_at"]) >= start
                  or any(c not in j.get("v_away", {}) for c in CONFIGS) else
                  "no unique Polymarket match" if "market_id" not in pm else
                  "no Polymarket price at T-5" if L.poly_at(hist, t5) is None else
                  "no clean result" if winner is None or pm.get("away_won") != winner else None)
        if reason:
            drops[reason] += 1
            continue
        kres = {"yes": 1, "no": 0}.get(ks.get("away_result"))
        kal_ok = kres is None or kres == winner
        if kres is not None and not kal_ok:
            drops["Kalshi result disagrees (kept, no Kalshi)"] += 1
        kc = ks.get("away_candles", []) if kal_ok else []
        rows.append({"id": gid, "sport": "nba", "start": start.isoformat(), "day": g["day"], "away": g["away"],
                     "home": g["home"], "y": winner,
                     "poly5": L.poly_at(hist, t5), "poly60": L.poly_at(hist, t60),
                     "polyE": L.poly_at(hist, early) if early < start else None,
                     "kal5": kalshi_at(kc, t5), "kal60": kalshi_at(kc, t60),
                     "jev": {c: j["v_away"][c] for c in CONFIGS}, "neutral": es.get("neutral")})
    rows.sort(key=lambda r: r["start"])
    return rows, drops


# --- measures ---------------------------------------------------------------------------------------------------------

def one(rows):
    return [list(range(len(rows)))]


def e1(rows, rng, b=B):
    sub = [r for r in rows if r["kal5"] is not None]
    pol, kal = [r["poly5"] for r in sub], [r["kal5"] for r in sub]
    rho, mad = spearman(pol, kal), statistics.mean(abs(a - c) for a, c in zip(pol, kal))
    return {"n": len(sub), "rho": rho, "rho_ci": L.ci(lambda ix: spearman([pol[i] for i in ix], [kal[i] for i in ix]), one(sub), rng, b),
            "mad": mad, "mad_ci": L.ci(lambda ix: statistics.mean(abs(pol[i] - kal[i]) for i in ix), one(sub), rng, b),
            "holds": rho >= 0.95 and mad <= 0.02}


def e2(rows, rng, b=B):
    sub = [r for r in rows if r["kal5"] is not None]
    y = np.array([r["y"] for r in sub], float)
    p = np.array([[1.0, L.logit(r["poly5"])] for r in sub])
    k = np.array([[1.0, L.logit(r["kal5"])] for r in sub])
    both = np.array([[1.0, L.logit(r["poly5"]), L.logit(r["kal5"])] for r in sub])
    out = {"n": len(sub)}
    for name, base in (("kalshi_added_to_poly", p), ("poly_added_to_kalshi", k)):
        diff = L.oof_loss(both, y) - L.oof_loss(base, y)                               # < 0: the added source helps
        lo, hi = L.ci(lambda ix: float(np.mean(diff[ix])), one(sub), rng, b)
        out[name] = {"diff": float(diff.mean()), "ci": (lo, hi),
                     "reading": "adds out of fold" if hi < 0 else "worse out of fold" if lo > 0 else "no difference"}
    lo, hi = out["kalshi_added_to_poly"]["ci"]
    out["holds"] = lo <= 0 <= hi
    return out


def e3(rows, rng, b=B):
    sub = [r for r in rows if None not in (r["kal5"], r["kal60"], r["poly60"]) and abs(r["poly60"] - r["kal60"]) >= 0.03]
    if len(sub) < 2:
        return {"n": len(sub), "descriptive": True}
    gap = [r["poly60"] - r["kal60"] for r in sub]
    poly_c = [(r["poly60"] - r["poly5"]) / g for r, g in zip(sub, gap)]
    kal_c = [(r["kal5"] - r["kal60"]) / g for r, g in zip(sub, gap)]
    d = [a - c for a, c in zip(poly_c, kal_c)]
    return {"n": len(sub), "poly_closes": statistics.mean(poly_c), "kalshi_closes": statistics.mean(kal_c),
            "diff": statistics.mean(d), "ci": L.ci(lambda ix: statistics.mean(d[i] for i in ix), one(sub), rng, b),
            "descriptive": True, "enough": len(sub) >= MIN_E3}


def n1(rows, cfg, rng, b=B):
    y, jv, pol = [r["y"] for r in rows], [r["jev"][cfg] for r in rows], [r["poly5"] for r in rows]
    a = lambda v, ix: auc([v[i] for i in ix], [y[i] for i in ix])
    lo, hi = L.ci(lambda ix: a(jv, ix) - a(pol, ix), one(rows), rng, b)
    return {"n": len(rows), "auc_jev": auc(jv, y), "auc_poly5": auc(pol, y), "ci": (lo, hi), "holds": hi < 0}


def n2(rows, cfg, rng, b=B):
    sub = [r for r in rows if r["polyE"] is not None]
    jv = [r["jev"][cfg] for r in sub]
    rho = lambda k, ix: spearman([jv[i] for i in ix], [sub[i][k] for i in ix])
    full = range(len(sub))
    lo, hi = L.ci(lambda ix: rho("polyE", ix) - rho("poly5", ix), one(sub), rng, b)
    d = rho("polyE", full) - rho("poly5", full)
    return {"n": len(sub), "rho_early": rho("polyE", full), "rho_poly5": rho("poly5", full), "diff": d, "ci": (lo, hi),
            "reading": "supported" if lo > 0 else "contradicted" if hi < 0 else "null (the CI includes 0)"}


def n3(rows, cfg, rng, b=B):
    jv, pol = [r["jev"][cfg] for r in rows], [r["poly5"] for r in rows]
    rho = spearman(jv, pol)
    return {"n": len(rows), "rho": rho, "ci": L.ci(lambda ix: spearman([jv[i] for i in ix], [pol[i] for i in ix]), one(rows), rng, b),
            "holds": 0 < rho <= 0.45}


def home(rows):
    return {"n": len(rows), "jev_noul_both_mean": statistics.mean(r["jev"]["noul_both"] for r in rows),
            "poly5_mean": statistics.mean(r["poly5"] for r in rows), "away_win_share": statistics.mean(r["y"] for r in rows)}


def x6(ncaaf, nba, cfg, rng, b=B):
    s1, s2 = [r for r in ncaaf if cfg in r["jev"]], nba
    rho = lambda s, ix: spearman([s[i]["jev"][cfg] for i in ix], [s[i]["poly5"] for i in ix])
    diffs = []
    for _ in range(b):
        try:
            diffs.append(rho(s1, [rng.randrange(len(s1)) for _ in s1]) - rho(s2, [rng.randrange(len(s2)) for _ in s2]))
        except (statistics.StatisticsError, ZeroDivisionError):
            continue
    diffs.sort()
    lo, hi = diffs[int(0.025 * len(diffs))], diffs[int(0.975 * len(diffs)) - 1]
    r1, r2 = rho(s1, range(len(s1))), rho(s2, range(len(s2)))
    return {"n_ncaaf": len(s1), "n_nba": len(s2), "rho_ncaaf": r1, "rho_nba": r2, "diff": r1 - r2, "ci": (lo, hi),
            "verdict": len(s1) >= MIN_N and len(s2) >= MIN_N, "holds": lo > 0}


# --- commands ---------------------------------------------------------------------------------------------------------

def counts(root: Path = ROOT) -> None:
    rows, drops = games(root)
    print(f"NBA    usable {len(rows):4} | Kalshi T-5 {sum(r['kal5'] is not None for r in rows)} | "
          f"Polymarket early {sum(r['polyE'] is not None for r in rows)} | "
          f"T-60 pair {sum(r['kal60'] is not None and r['poly60'] is not None for r in rows)} | dropped {dict(drops)}")


def report(root: Path = ROOT, b: int = B, now: dt.datetime | None = None, out: Path | None = None) -> dict[str, Any]:
    rng = random.Random(SEED)
    rows, drops = games(root, now)
    res: dict[str, Any] = {"n": len(rows), "drops": dict(drops), "verdicts": len(rows) >= MIN_N}
    if len(rows) < 5:
        res["skipped"] = "too few games"
        print(res)
        return res
    res.update(E1=e1(rows, rng, b), E2=e2(rows, rng, b), E3=e3(rows, rng, b), home=home(rows))
    for cfg in CONFIGS:
        res[f"N1 {cfg}"], res[f"N2 {cfg}"], res[f"N3 {cfg}"] = n1(rows, cfg, rng, b), n2(rows, cfg, rng, b), n3(rows, cfg, rng, b)
    others = {s: L.games(root, s, now)[0] for s in L.SPORTS if (root / "runs" / s / "state.json").exists()}
    if others.get("ncaaf"):
        res["X6"] = {c: x6(others["ncaaf"], rows, c, rng, b) for c in CONFIGS}
    res["X6 other sports (descriptive)"] = {
        s: {c: spearman([r["jev"][c] for r in rs if c in r["jev"]], [r["poly5"] for r in rs if c in r["jev"]])
            for c in CONFIGS} for s, rs in others.items() if s != "ncaaf" and len(rs) >= 5}
    if out:
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.json").write_text(json.dumps(res, indent=1, default=str))
    show(res)
    return res


def show(res: dict[str, Any]) -> None:
    rnd = lambda v: ({k: rnd(x) for k, x in v.items()} if isinstance(v, dict) else [rnd(x) for x in v]
                     if isinstance(v, (list, tuple)) else round(v, 3) if isinstance(v, float) else v)
    for k, v in res.items():
        print(f"{k}: {json.dumps(rnd(v), default=str)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("counts", "report"))
    ap.add_argument("--root", type=Path, default=ROOT)
    a = ap.parse_args()
    if a.cmd == "counts":
        counts(a.root)
    else:
        report(a.root, out=a.root / "runs" / "nba-analysis")
