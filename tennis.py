"""Experiment 7 groundwork: how predictable are tennis matches for the crowd, against MLB games over the same dates?

Before any Jev call, this measures the ceiling: the market's own skill on resolved match markets. A sport where the
market barely beats a coin flip (MLB: Braves rank correlation +0.11) leaves no room to tell a good forecaster from a
lucky one.

Selection (same rules for both sports): closed moneyline markets with a game start in the window, two outcomes, a
clean 1/0 resolution, volume >= MIN_VOLUME; tennis singles only (no "/" in the names). Price = the first-listed
side's last trade at or before 5 minutes ahead of the scheduled start (tennis start times are scheduled, so the
price is pre-match).

    .venv/bin/python tennis.py collect --sport tennis --days 45     # -> runs/matches-tennis.json
    .venv/bin/python tennis.py collect --sport mlb --days 45
    .venv/bin/python tennis.py ceiling                               # the market's skill per sport
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import statistics
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from analyze import spearman
import braves
from braves import EVENTS, HIST, ts

ROOT = Path(__file__).parent
PRE_GAME_MIN, MIN_VOLUME = 5, 5000.0


def get(url: str) -> Any:
    """braves.get with retries on timeouts and dropped connections."""
    import time
    for attempt in range(5):
        try:
            return braves.get(url)
        except (TimeoutError, OSError):
            if attempt == 4:
                raise
            time.sleep(2 * (attempt + 1))


def candidates(sport: str, days: int, now: dt.datetime) -> list[dict[str, Any]]:
    out: dict[str, dict] = {}
    d = now - dt.timedelta(days=days + 1)
    while d < now + dt.timedelta(days=3):                # end dates can fall days after the start
        d2 = d + dt.timedelta(days=3)
        for off in range(0, 3000, 100):
            evs = get(EVENTS.format(tag=sport, off=off, a=d.strftime("%Y-%m-%dT%H:%M:%SZ"), b=d2.strftime("%Y-%m-%dT%H:%M:%SZ")))
            if not evs:
                break
            for e in evs:
                for m in e.get("markets", []):
                    names = json.loads(m.get("outcomes") or "[]")
                    if (m.get("sportsMarketType") == "moneyline" and len(names) == 2 and m.get("closed")
                            and m.get("gameStartTime") and float(m.get("volume") or 0) >= MIN_VOLUME
                            and not (sport == "tennis" and any("/" in n for n in names))):
                        out[str(m["id"])] = {**m, "event": e.get("title", "")}
            if len(evs) < 100:
                break
        d = d2
    lo = now - dt.timedelta(days=days)
    return [m for m in out.values() if lo <= ts(m["gameStartTime"]) <= now]


def row(m: dict[str, Any]) -> dict[str, Any] | None:
    names, prices = json.loads(m["outcomes"]), [float(p) for p in json.loads(m["outcomePrices"])]
    if sorted(prices) != [0.0, 1.0]:
        return None                                     # unresolved, voided or split
    start = ts(m["gameStartTime"])
    at = start - dt.timedelta(minutes=PRE_GAME_MIN)
    token = json.loads(m["clobTokenIds"])[0]
    hist = (get(HIST.format(token=token, a=int((at - dt.timedelta(hours=12)).timestamp()), b=int(at.timestamp()))) or {}).get("history", [])
    if not hist:
        return None
    return {"id": str(m["id"]), "event": m["event"], "start": start.isoformat(), "a": names[0], "b": names[1],
            "p_a": float(hist[-1]["p"]), "a_won": int(prices[0] == 1.0), "volume": float(m["volume"])}


def collect(sport: str, days: int) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    ms = candidates(sport, days, now)
    with ThreadPoolExecutor(8) as pool:
        rows = sorted((r for r in pool.map(row, ms) if r), key=lambda r: r["start"])
    out = ROOT / "runs" / f"matches-{sport}.json"
    out.write_text(json.dumps({"sport": sport, "days": days, "fetched_at": now.isoformat(), "rows": rows}, indent=1))
    print(f"{sport}: {len(ms)} candidate markets, {len(rows)} priced and resolved -> {out.name}")


def auc(p: list[float], y: list[int]) -> float:
    pos, neg = [x for x, t in zip(p, y) if t], [x for x, t in zip(p, y) if not t]
    return sum((a > b) + 0.5 * (a == b) for a in pos for b in neg) / (len(pos) * len(neg))


def skill(p: list[float], y: list[int]) -> dict[str, float]:
    fav_won = [int((x >= 0.5) == bool(t)) for x, t in zip(p, y)]
    acc = statistics.mean(fav_won)
    clip = [min(max(x, 0.01), 0.99) for x in p]
    return {"n": len(p), "fav_win": acc, "se": math.sqrt(acc * (1 - acc) / len(p)),
            "brier": statistics.mean((x - t) ** 2 for x, t in zip(p, y)),
            "logloss": -statistics.mean(math.log(x if t else 1 - x) for x, t in zip(clip, y)),
            "auc": auc(p, y), "rho": spearman(p, [float(t) for t in y]),
            "lopsided": statistics.mean(max(x, 1 - x) >= 0.70 for x in p)}


def ceiling() -> None:
    print(f"{'set':28} {'n':>5} {'fav wins':>13} {'Brier':>6} {'logloss':>8} {'AUC':>5} {'rho':>6} {'fav >= 70%':>11}")
    sets = {}
    for f in sorted((ROOT / "runs").glob("matches-*.json")):
        d = json.loads(f.read_text())
        sets[f"{d['sport']} ({d['days']} days)"] = ([r["p_a"] for r in d["rows"]], [r["a_won"] for r in d["rows"]])
    braves = json.loads((ROOT / "runs" / "braves-season.json").read_text())["rows"]
    sets["Braves 2026 (reference)"] = ([g["market_p"] for g in braves], [int(g["braves_won"]) for g in braves])
    for name, (p, y) in sets.items():
        s = skill(p, y)
        print(f"{name:28} {s['n']:5} {s['fav_win']:7.1%} ±{s['se']:4.1%} {s['brier']:6.3f} {s['logloss']:8.3f} "
              f"{s['auc']:5.2f} {s['rho']:+6.2f} {s['lopsided']:11.0%}")
    print("\ncoin flip: Brier 0.250, log loss 0.693, AUC 0.50")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("collect", "ceiling"))
    ap.add_argument("--sport", default="tennis")
    ap.add_argument("--days", type=int, default=45)
    a = ap.parse_args()
    collect(a.sport, a.days) if a.cmd == "collect" else ceiling()
