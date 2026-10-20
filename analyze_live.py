"""Score experiments 9 (NHL), 10 (MLB postseason) and 12 (NCAA football): docs/PREDICTIONS-NHL.md, -MLB.md, -NCAAF.md.

Run `report` once, after collection closes (NHL 11-05, MLB at the last World Series game, NCAA football 12-05). Until
then only `counts` is run on the real data: usable games and drop reasons, no measures (ADC-013).

    .venv/bin/python analyze_live.py counts
    .venv/bin/python analyze_live.py report                 # every measure, per sport and pooled; runs/live-analysis/
    .venv/bin/python analyze_live.py report --root DIR      # another data tree (tests/test_analyze_live.py)

Choices the plans leave open, fixed here before any measure was computed on real data (2026-10-20):
  - A game's start is its listing in the last snapshot taken before that listed start (the Odds API keeps listing a
    game once it is live, with the actual start time; the collector also follows only moves to future times). Moments
    are timed against it:
      T-5   the latest snapshot 1-12 min before the start that has a Pinnacle price
      T-60  the snapshot 45-70 min before the start, closest to 60 min, that has a Pinnacle price
      early the latest early snapshot before the start that has a Pinnacle price
  - Polymarket at a moment: the last 1-minute price at or before the snapshot, at most 10 minutes older.
  - Drops, in this order: postponed listing, no Pinnacle T-5, no unique Polymarket match, no Polymarket price at T-5,
    no clean result (Polymarket resolved to exactly 0 or 1). Jev is not a drop rule; J measures use games with Jev.
  - "Jev" is reported for both configs (noul_both, bins_plain), and each config gets its own verdict.
  - Bootstrap: 2000 resamples of games, seed 7, percentile 95% CIs. Pooled CIs resample within sport.
  - C2: logistic regression (Newton's method) on logit-prices clipped to [0.01, 0.99]; 5 folds = consecutive blocks in
    start order; per-game out-of-fold log loss; the CI resamples games, not refits. Pooled: sport indicators added.
  - C3: the share of the T-60 gap each source closes by T-5, (move toward the other's T-60 price) / |gap|. Needs a
    Polymarket price at T-60 under the same 10-minute rule.
  - J1 pooled: partial correlations within sport, averaged with weights proportional to games.
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
from typing import Any, Callable
from zoneinfo import ZoneInfo

import numpy as np

from analyze import spearman
from tennis_jev import auc

ROOT = Path(__file__).parent
CT = ZoneInfo("America/Chicago")
SPORTS = ("nhl", "mlb", "ncaaf")
CONFIGS = ("noul_both", "bins_plain")
NHL_DAYS = ("2026-10-06", "2026-11-05")
PILOT_DAYS = {"2026-10-10", "2026-10-17"}                     # experiment 12's original two Saturdays
POSTPONED = {"b9d2e07cf437b5643307aba274c45a74"}              # ALCS Game 4's first listing (MLB amendment, 10-17)
T5, T60, POLY_STALE = (1, 12), (45, 70), 600
B, SEED, FOLDS, MIN_C3, MIN_NCAAF = 2000, 7, 5, 30, 100
iso = lambda s: dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def novig(e: dict[str, Any]) -> float | None:
    """Pinnacle's no-vig probability that the away team wins."""
    b = next((b for b in e.get("bookmakers", []) if b["key"] == "pinnacle"), None)
    m = next((m for m in (b or {}).get("markets", []) if m["key"] == "h2h"), None)
    o = {x["name"]: x["price"] for x in (m or {}).get("outcomes", [])}
    if e["away_team"] not in o or e["home_team"] not in o:
        return None
    a, h = 1 / o[e["away_team"]], 1 / o[e["home_team"]]
    return a / (a + h)


def poly_at(hist: list[dict[str, float]], t: dt.datetime) -> float | None:
    ts = t.timestamp()
    ok = [x for x in hist if ts - POLY_STALE <= x["t"] <= ts]
    return max(ok, key=lambda x: x["t"])["p"] if ok else None


def games(root: Path, sport: str, now: dt.datetime | None = None) -> tuple[list[dict[str, Any]], Counter]:
    """Usable games (sorted by start) and the drop counts for one sport."""
    d = root / "runs" / sport
    st = json.loads((d / "state.json").read_text())
    poly = json.loads((d / "poly.json").read_text()) if (d / "poly.json").exists() else {}
    scores = json.loads((d / "scores.json").read_text()) if (d / "scores.json").exists() else {}
    jev: dict[str, dict] = {}
    if (d / "jev.jsonl").exists():
        for l in (d / "jev.jsonl").open():
            r = json.loads(l)
            jev.setdefault(r["id"], r)                                               # one answer per game
    seen: dict[str, list] = {}
    for l in (d / "snapshots.jsonl").open():
        s = json.loads(l)
        kinds = {k.split(":")[0] for k in s["keys"]}
        for e in s["events"]:
            seen.setdefault(e["id"], []).append((iso(s["fetched_at"]), kinds, e))
    now = now or dt.datetime.now(dt.timezone.utc)
    rows, drops = [], Counter()
    for gid, obs in seen.items():
        obs.sort(key=lambda x: x[0])
        pre = [o for o in obs if iso(o[2]["commence_time"]) > o[0]] or obs                # listings before the start
        last = pre[-1][2]
        start = iso(last["commence_time"])
        day = start.astimezone(CT).date().isoformat()
        if sport == "ncaaf" and gid not in st.get("scope", []):
            continue
        if sport == "nhl" and not NHL_DAYS[0] <= day <= NHL_DAYS[1]:
            continue
        if start > now - dt.timedelta(hours=5):                                        # not finished yet
            continue
        mins = lambda t: (start - t).total_seconds() / 60
        priced = [(t, k, novig(e)) for t, k, e in obs if novig(e) is not None]
        t5 = [(t, p) for t, k, p in priced if "t5" in k and T5[0] <= mins(t) <= T5[1]]
        t60 = sorted(((t, p) for t, k, p in priced if "t60" in k and T60[0] <= mins(t) <= T60[1]), key=lambda x: abs(mins(x[0]) - 60))
        early = [(t, p) for t, k, p in priced if "early" in k and t < start]
        pm = poly.get(gid, {})
        reason = ("postponed" if gid in POSTPONED else "no Pinnacle T-5" if not t5 else
                  "no unique Polymarket match" if "market_id" not in pm else
                  "no Polymarket price at T-5" if poly_at(pm.get("history_away", []), t5[-1][0]) is None else
                  "no clean result" if pm.get("away_won") not in (0, 1) else None)
        if reason:
            drops[reason] += 1
            continue
        hist = pm["history_away"]
        j = jev.get(gid)
        rows.append({"id": gid, "sport": sport, "start": start.isoformat(), "day": day, "away": last["away_team"],
                     "home": last["home_team"], "y": pm["away_won"],
                     "pin5": t5[-1][1], "poly5": poly_at(hist, t5[-1][0]),
                     "pin60": t60[0][1] if t60 else None, "poly60": poly_at(hist, t60[0][0]) if t60 else None,
                     "early": early[-1][1] if early else None,
                     "jev": {c: j["v_away"][c] for c in CONFIGS if c in j.get("v_away", {})} if j else {},
                     "ranks": (j or {}).get("ranks"), "neutral": scores.get(gid, {}).get("neutral")})
    rows.sort(key=lambda r: r["start"])
    return rows, drops


# --- statistics -------------------------------------------------------------------------------------------------------

def ci(stat: Callable[[list[int]], float], groups: list[list[int]], rng: random.Random, b: int = B) -> tuple[float, float]:
    """Percentile CI, resampling indices within each group (one group per sport)."""
    out = []
    for _ in range(b):
        idx = [g[rng.randrange(len(g))] for g in groups for _ in g]
        try:
            v = stat(idx)
        except (statistics.StatisticsError, ZeroDivisionError, ValueError):
            continue
        if v is not None and not math.isnan(v):
            out.append(v)
    out.sort()
    return (out[int(0.025 * len(out))], out[int(0.975 * len(out)) - 1]) if out else (math.nan, math.nan)


def partial(x: list[float], y: list[float], z: list[float]) -> float:
    """Partial rank correlation of x and y holding z fixed."""
    rxy, rxz, ryz = spearman(x, y), spearman(x, z), spearman(y, z)
    return (rxy - rxz * ryz) / math.sqrt((1 - rxz ** 2) * (1 - ryz ** 2))


def logit(p: float) -> float:
    p = min(max(p, 0.01), 0.99)
    return math.log(p / (1 - p))


def fit(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    w = np.zeros(X.shape[1])
    for _ in range(100):
        p = 1 / (1 + np.exp(-X @ w))
        step = np.linalg.solve(X.T @ (X * (p * (1 - p))[:, None]) + 1e-6 * np.eye(len(w)), X.T @ (y - p))
        w += step
        if np.abs(step).max() < 1e-10:
            break
    return w


def oof_loss(X: np.ndarray, y: np.ndarray, folds: int = FOLDS) -> np.ndarray:
    """Per-row out-of-fold log loss; folds are consecutive blocks of the rows as given (start order)."""
    n, size = len(y), -(-len(y) // folds)
    loss = np.empty(n)
    for s in range(0, n, size):
        te = np.arange(s, min(s + size, n))
        tr = np.setdiff1d(np.arange(n), te)
        p = np.clip(1 / (1 + np.exp(-X[te] @ fit(X[tr], y[tr]))), 1e-6, 1 - 1e-6)
        loss[te] = -(y[te] * np.log(p) + (1 - y[te]) * np.log(1 - p))
    return loss


# --- measures ---------------------------------------------------------------------------------------------------------

def groups_of(rows: list[dict[str, Any]], keep: Callable[[dict], bool] = lambda r: True) -> list[list[int]]:
    by: dict[str, list[int]] = {}
    for i, r in enumerate(rows):
        if keep(r):
            by.setdefault(r["sport"], []).append(i)
    return list(by.values())


def c1(rows, rng, b=B):
    pin, pol = [r["pin5"] for r in rows], [r["poly5"] for r in rows]
    rho, mad = spearman(pol, pin), statistics.mean(abs(a - c) for a, c in zip(pol, pin))
    g = groups_of(rows)
    return {"n": len(rows), "rho": rho, "rho_ci": ci(lambda ix: spearman([pol[i] for i in ix], [pin[i] for i in ix]), g, rng, b),
            "mad": mad, "mad_ci": ci(lambda ix: statistics.mean(abs(pol[i] - pin[i]) for i in ix), g, rng, b),
            "holds": rho >= 0.95 and mad <= 0.03}


def c2(rows, rng, b=B):
    sports = sorted({r["sport"] for r in rows})
    fe = [[float(r["sport"] == s) for s in sports[1:]] for r in rows]                # sport fixed effects when pooled
    y = np.array([r["y"] for r in rows], float)
    xa = np.array([[1.0, logit(r["pin5"])] + f for r, f in zip(rows, fe)])
    xb = np.array([[1.0, logit(r["pin5"]), logit(r["poly5"])] + f for r, f in zip(rows, fe)])
    diff = oof_loss(xb, y) - oof_loss(xa, y)                                         # < 0: Polymarket helps
    lo, hi = ci(lambda ix: float(np.mean(diff[ix])), groups_of(rows), rng, b)
    return {"n": len(rows), "diff": float(diff.mean()), "ci": (lo, hi), "holds": lo <= 0 <= hi,
            "reading": "Polymarket adds out of fold" if hi < 0 else "Polymarket worse out of fold" if lo > 0 else "no difference"}


def c3(rows, rng, b=B):
    sub = [r for r in rows if r["pin60"] is not None and r["poly60"] is not None and abs(r["poly60"] - r["pin60"]) >= 0.03]
    if len(sub) < 2:
        return {"n": len(sub), "descriptive": True}
    gap = [r["poly60"] - r["pin60"] for r in sub]
    d = [(r["poly60"] - r["poly5"]) / g - (r["pin5"] - r["pin60"]) / g for r, g in zip(sub, gap)]   # poly share - pin share
    lo, hi = ci(lambda ix: statistics.mean(d[i] for i in ix), groups_of(sub), rng, b)
    return {"n": len(sub), "poly_closes": statistics.mean((r["poly60"] - r["poly5"]) / g for r, g in zip(sub, gap)),
            "pin_closes": statistics.mean((r["pin5"] - r["pin60"]) / g for r, g in zip(sub, gap)),
            "diff": statistics.mean(d), "ci": (lo, hi), "descriptive": len(sub) < MIN_C3, "holds": lo > 0}


def j1(rows, cfg, rng, b=B):
    sub = [r for r in rows if cfg in r["jev"]]
    g = groups_of(sub)

    def both(ix):
        out = []
        for grp in ({sub[i]["sport"] for i in ix}):
            k = [i for i in ix if sub[i]["sport"] == grp]
            jv, pol, pin = [sub[i]["jev"][cfg] for i in k], [sub[i]["poly5"] for i in k], [sub[i]["pin5"] for i in k]
            out.append((len(k), partial(jv, pol, pin), partial(jv, pin, pol)))
        n = sum(w for w, _, _ in out)
        return sum(w * a for w, a, _ in out) / n, sum(w * c for w, _, c in out) / n
    poly_p, pin_p = both(list(range(len(sub))))
    return {"n": len(sub), "jev_poly_given_pin": poly_p, "jev_pin_given_poly": pin_p,
            "poly_ci": ci(lambda ix: both(ix)[0], g, rng, b), "pin_ci": ci(lambda ix: both(ix)[1], g, rng, b),
            "holds": abs(poly_p) <= 0.10 and abs(pin_p) <= 0.10}


def j2(rows, cfg, rng, b=B):
    sub = [r for r in rows if cfg in r["jev"] and r["early"] is not None]
    jv = [r["jev"][cfg] for r in sub]
    col = {k: [r[k] for r in sub] for k in ("early", "pin5", "poly5")}
    rho = lambda k, ix: spearman([jv[i] for i in ix], [col[k][i] for i in ix])
    g, out = groups_of(sub), {"n": len(sub)}
    for k in ("early", "pin5", "poly5"):
        out[f"rho_{k}"] = rho(k, range(len(sub)))
    for k in ("pin5", "poly5"):
        out[f"early_minus_{k}"] = out["rho_early"] - out[f"rho_{k}"]
        out[f"early_minus_{k}_ci"] = ci(lambda ix: rho("early", ix) - rho(k, ix), g, rng, b)
    los = [out[f"early_minus_{k}_ci"][0] for k in ("pin5", "poly5")]
    his = [out[f"early_minus_{k}_ci"][1] for k in ("pin5", "poly5")]
    out["reading"] = "supported" if min(los) > 0 else "contradicted" if min(his) < 0 else "null (a CI includes 0)"
    return out


def j3(rows, cfg, rng, b=B):
    sub = [r for r in rows if cfg in r["jev"]]
    y, jv = [r["y"] for r in sub], [r["jev"][cfg] for r in sub]
    src = {"pin5": [r["pin5"] for r in sub], "poly5": [r["poly5"] for r in sub]}
    a = lambda v, ix: auc([v[i] for i in ix], [y[i] for i in ix])
    g, out = groups_of(sub), {"n": len(sub), "auc_jev": auc(jv, y)}
    for k, v in src.items():
        out[f"auc_{k}"] = auc(v, y)
        out[f"jev_minus_{k}_ci"] = ci(lambda ix: a(jv, ix) - a(v, ix), g, rng, b)
    out["holds"] = out["auc_jev"] < out["auc_pin5"] and out["auc_jev"] < out["auc_poly5"]
    return out


def j4(ncaaf, nhl, cfg, rng, b=B):
    s1, s2 = [r for r in ncaaf if cfg in r["jev"]], [r for r in nhl if cfg in r["jev"]]
    rho = lambda s, ix: spearman([s[i]["jev"][cfg] for i in ix], [s[i]["pin5"] for i in ix])
    diffs = []
    for _ in range(b):
        try:
            diffs.append(rho(s1, [rng.randrange(len(s1)) for _ in s1]) - rho(s2, [rng.randrange(len(s2)) for _ in s2]))
        except statistics.StatisticsError:
            continue
    diffs.sort()
    d = rho(s1, range(len(s1))) - rho(s2, range(len(s2)))
    return {"n_ncaaf": len(s1), "n_nhl": len(s2), "rho_ncaaf": rho(s1, range(len(s1))), "rho_nhl": rho(s2, range(len(s2))),
            "diff": d, "ci": (diffs[int(0.025 * len(diffs))], diffs[int(0.975 * len(diffs)) - 1]), "holds": d > 0}


# --- commands ---------------------------------------------------------------------------------------------------------

def load(root: Path, now: dt.datetime | None = None) -> dict[str, tuple[list, Counter]]:
    return {s: games(root, s, now) for s in SPORTS if (root / "runs" / s / "state.json").exists()}


def counts(root: Path = ROOT) -> None:
    for s, (rows, drops) in load(root).items():
        jev = sum(bool(r["jev"]) for r in rows)
        print(f"{s.upper():6} usable {len(rows):4} | Jev {jev} | early {sum(r['early'] is not None for r in rows)} | "
              f"T-60 pair {sum(r['pin60'] is not None and r['poly60'] is not None for r in rows)} | dropped {dict(drops)}")


def report(root: Path = ROOT, b: int = B, now: dt.datetime | None = None, out: Path | None = None) -> dict[str, Any]:
    rng = random.Random(SEED)
    data = load(root, now)
    res: dict[str, Any] = {"drops": {s: dict(d) for s, (_, d) in data.items()}}
    verdicts = {"nhl": True, "mlb": False, "ncaaf": len(data.get("ncaaf", ([], 0))[0]) >= MIN_NCAAF}
    sets = {s: rows for s, (rows, _) in data.items()}
    if "ncaaf" in sets:
        sets["ncaaf-pilot"] = [r for r in sets["ncaaf"] if r["day"] in PILOT_DAYS]
    for name, rows in sets.items():
        if len(rows) < 5:
            res[name] = {"n": len(rows), "skipped": "too few games"}
            continue
        r = {"n": len(rows), "verdicts": verdicts.get(name, False), "C1": c1(rows, rng, b), "C2": c2(rows, rng, b),
             "C3": c3(rows, rng, b)}
        for cfg in CONFIGS:
            r[f"J1 {cfg}"], r[f"J2 {cfg}"], r[f"J3 {cfg}"] = j1(rows, cfg, rng, b), j2(rows, cfg, rng, b), j3(rows, cfg, rng, b)
        res[name] = r
    pooled = [x for s in SPORTS for x in sets.get(s, [])]
    pooled.sort(key=lambda r: r["start"])
    if len({r["sport"] for r in pooled}) > 1:
        res["pooled"] = {"n": len(pooled), "C2": c2(pooled, rng, b), **{f"J1 {c}": j1(pooled, c, rng, b) for c in CONFIGS}}
    if "ncaaf" in sets and "nhl" in sets:
        res["J4"] = {c: j4(sets["ncaaf"], sets["nhl"], c, rng, b) for c in CONFIGS}
    if out:
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.json").write_text(json.dumps(res, indent=1, default=str))
    show(res)
    return res


def show(res: dict[str, Any]) -> None:
    f = lambda x: f"{x:+.3f}" if isinstance(x, float) else str(x)
    c = lambda p: f"[{p[0]:+.3f}, {p[1]:+.3f}]"
    print("drops:", res["drops"])
    for name in (*SPORTS, "ncaaf-pilot"):
        r = res.get(name)
        if not r or "skipped" in r:
            print(f"\n{name.upper()}: {r}") if r else None
            continue
        tag = "verdicts" if r["verdicts"] else "descriptive"
        print(f"\n{name.upper()} ({r['n']} games, {tag})")
        x = r["C1"]; print(f"  C1 rho {f(x['rho'])} {c(x['rho_ci'])}  MAD {x['mad']:.3f} {c(x['mad_ci'])}  holds: {x['holds']}")
        x = r["C2"]; print(f"  C2 log-loss (with - without Polymarket) {f(x['diff'])} {c(x['ci'])}  {x['reading']}")
        x = r["C3"]
        if "diff" in x:
            print(f"  C3 n={x['n']}{' (descriptive)' if x['descriptive'] else ''}: Polymarket closes {x['poly_closes']:.2f}, "
                  f"Pinnacle {x['pin_closes']:.2f}, diff {f(x['diff'])} {c(x['ci'])}  holds: {x['holds']}")
        for cfg in CONFIGS:
            a, b2, d = r[f"J1 {cfg}"], r[f"J2 {cfg}"], r[f"J3 {cfg}"]
            print(f"  {cfg:10} J1 partial poly|pin {f(a['jev_poly_given_pin'])} {c(a['poly_ci'])}, pin|poly {f(a['jev_pin_given_poly'])} "
                  f"{c(a['pin_ci'])} holds: {a['holds']}")
            print(f"  {'':10} J2 rho early {f(b2['rho_early'])}, pin5 {f(b2['rho_pin5'])}, poly5 {f(b2['rho_poly5'])} (n={b2['n']}): {b2['reading']}")
            print(f"  {'':10} J3 AUC Jev {d['auc_jev']:.3f}, Pinnacle {d['auc_pin5']:.3f}, Polymarket {d['auc_poly5']:.3f}  holds: {d['holds']}")
    if "pooled" in res:
        p = res["pooled"]
        print(f"\nPOOLED ({p['n']} games, sport fixed effects)")
        print(f"  C2 {f(p['C2']['diff'])} {c(p['C2']['ci'])}  {p['C2']['reading']}")
        for cfg in CONFIGS:
            a = p[f"J1 {cfg}"]
            print(f"  {cfg:10} J1 poly|pin {f(a['jev_poly_given_pin'])} {c(a['poly_ci'])}, pin|poly {f(a['jev_pin_given_poly'])} {c(a['pin_ci'])} holds: {a['holds']}")
    for cfg, x in res.get("J4", {}).items():
        print(f"J4 {cfg}: rho(Jev, Pinnacle T-5) NCAAF {f(x['rho_ncaaf'])} vs NHL {f(x['rho_nhl'])}, diff {f(x['diff'])} {c(x['ci'])}  holds: {x['holds']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("counts", "report"))
    ap.add_argument("--root", type=Path, default=ROOT)
    a = ap.parse_args()
    if a.cmd == "counts":
        counts(a.root)
    else:
        report(a.root, out=a.root / "runs" / "live-analysis")
