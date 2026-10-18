"""Experiment 13: one spread line and one total line per game from each source (docs/PREDICTIONS-SPREADS.md).

Sign convention: margin = away score - home score. Every rung becomes P(margin > x) or P(total > x).
  - Kalshi (public API, no key): series KXNCAAFSPREAD ("Texas Tech wins by over 7.5 points") and KXNCAAFTOTAL
    ("Over 50.5 points"). Team names are short ("Georgia St."); ALIASES and kalshi_name() bring them to Odds API names.
  - Polymarket (Gamma API): the `spreads` ("Spread: Army (-16.5)") and `totals` ("O/U 51.5") markets of each `cfb`
    event. The moneyline's outcomes are [away, home] in Polymarket's own names; spread markets use the same names.
  - A rung is usable when it has a bid and an ask with ask - bid <= MAX_SPREAD; its price is the midpoint.
  - line(): average rungs at the same x, pool-adjacent-violators so the probability falls as x rises, then the x where
    it crosses 0.5 (linear interpolation). None with fewer than 3 usable rungs or nothing on each side of 0.5.
  - dist_line(): Jev's Score distribution over ordered bins -> (median interpolated within its bin, expected value).
"""

from __future__ import annotations

import datetime as dt
import json
import re
import urllib.request
from typing import Any

KALSHI = "https://api.elections.kalshi.com/trade-api/v2/markets?series_ticker={series}&status=open&limit=1000"
POLY = ("https://gamma-api.polymarket.com/events?tag_slug=cfb&closed=false&limit=100&offset={off}"
        "&end_date_min={a}&end_date_max={b}")
MAX_SPREAD, MIN_RUNGS = 0.10, 3
ALIASES = {"Miami (FL)": "Miami", "Hawai'i": "Hawaii", "Louisiana-Monroe": "UL Monroe",
           "Southern Miss": "Southern Mississippi"}
# Jev's bins, ascending, as (low, high) edges: the open-ended ones are 21-35 (margin) and 25-35 / 70-85 (total)
MARGIN_LEVELS = ["{a} by 21 or more", "{a} by 14-20", "{a} by 7-13", "{a} by 1-6",
                 "{h} by 1-6", "{h} by 7-13", "{h} by 14-20", "{h} by 21 or more"]       # question order: away first
MARGIN_BINS = [(21, 35), (14, 21), (7, 14), (0, 7), (-7, 0), (-14, -7), (-21, -14), (-35, -21)]   # same order
MARGIN_MIDS = [28, 17.5, 10.5, 3.5, -3.5, -10.5, -17.5, -28]
TOTAL_LEVELS = ["Under 35", "35-41", "42-48", "49-55", "56-62", "63-69", "70 or more"]
TOTAL_BINS = [(25, 35), (35, 42), (42, 49), (49, 56), (56, 63), (63, 70), (70, 85)]
TOTAL_MIDS = [30, 38.5, 45.5, 52.5, 59.5, 66.5, 77.5]


def get(url: str) -> Any:
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "crowd-calibration/0.1"}), timeout=60) as r:
        return json.load(r)


def rung(x: float, p_yes: float | None, bid: float | None, ask: float | None, flip: bool, label: str) -> dict[str, Any]:
    """One rung as P(value > x). `flip`: the yes side is the value falling below x, so P(value > x) = 1 - yes."""
    ok = bid is not None and ask is not None and 0 < bid <= ask < 1 and ask - bid <= MAX_SPREAD
    mid = (bid + ask) / 2 if ok else None
    return {"x": x, "p": (1 - mid if flip else mid) if ok else None, "bid": bid, "ask": ask, "flip": flip,
            "last": p_yes, "usable": ok, "label": label}


def line(rungs: list[dict[str, Any]]) -> dict[str, Any]:
    """The 0.5 crossing of a falling P(value > x) fitted to the usable rungs."""
    by_x: dict[float, list[float]] = {}
    for r in rungs:
        if r["usable"]:
            by_x.setdefault(r["x"], []).append(r["p"])
    n = sum(len(v) for v in by_x.values())
    out = {"line": None, "usable": n, "rungs": len(rungs)}
    if n < MIN_RUNGS:
        return out
    xs = sorted(by_x)
    blocks = []                                          # pool-adjacent-violators, non-increasing in x, equal weights
    for x in xs:
        blocks.append([sum(by_x[x]), len(by_x[x]), [x]])
        while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] < blocks[-1][0] / blocks[-1][1]:
            s, w, b = blocks.pop()
            blocks[-1][0] += s
            blocks[-1][1] += w
            blocks[-1][2] += b
    fit = [(x, s / w) for s, w, b in blocks for x in b]
    out["fit"] = [[x, round(f, 4)] for x, f in fit]
    if not (max(f for _, f in fit) > 0.5 > min(f for _, f in fit)):
        return out
    at = [x for x, f in fit if f == 0.5]
    if at:
        out["line"] = sum(at) / len(at)
        return out
    for (x0, f0), (x1, f1) in zip(fit, fit[1:]):
        if f0 > 0.5 > f1:
            out["line"] = round(x0 + (f0 - 0.5) / (f0 - f1) * (x1 - x0), 3)
            return out
    return out


def dist_line(probs: dict[Any, Any], bins: list[tuple[float, float]], mids: list[float]) -> tuple[float, float]:
    """Median (linear within the bin that holds it) and expected value of a Score distribution over `bins`."""
    p = [float(probs.get(str(i), probs.get(i, 0.0))) for i in range(len(bins))]
    tot = sum(p)
    p = [x / tot for x in p]
    ev = sum(a * m for a, m in zip(p, mids))
    order = sorted(range(len(bins)), key=lambda i: bins[i][0])
    cum = 0.0
    for i in order:
        lo, hi = bins[i]
        if p[i] > 0 and cum + p[i] >= 0.5:
            return round(lo + (0.5 - cum) / p[i] * (hi - lo), 3), round(ev, 3)
        cum += p[i]
    return float(bins[order[-1]][1]), round(ev, 3)


def kalshi_name(n: str) -> str:
    n = ALIASES.get(n, n)
    return re.sub(r" St\.$", " State", n)


def assign(names: tuple[str, str], away: str, home: str) -> dict[str, str] | None:
    """Map two short names onto (away, home) full names; the closest fit (fewest leftover words) wins."""
    fits = lambda n, t: t == n or t.startswith(n + " ")
    best = None
    for a, h in (names, names[::-1]):
        if fits(kalshi_name(a), away) and fits(kalshi_name(h), home):
            rest = len(away.split()) - len(kalshi_name(a).split()) + len(home.split()) - len(kalshi_name(h).split())
            if best is None or rest < best[0]:
                best = (rest, {a: "away", h: "home"})
    return best[1] if best else None


def kalshi(series: str) -> list[dict[str, Any]]:
    out, cur = [], ""
    while True:
        d = get(KALSHI.format(series=series) + (f"&cursor={cur}" if cur else ""))
        out += d["markets"]
        cur = d.get("cursor")
        if not cur or not d["markets"]:
            return out


def kalshi_ladders(games: list[dict[str, Any]], day: dt.date) -> dict[str, dict[str, Any]]:
    """{odds id: {"spread": line(...) + rungs, "total": ..., "event": ticker}} for the games Kalshi lists."""
    found: dict[str, dict[str, Any]] = {}
    for kind, series in (("spread", "KXNCAAFSPREAD"), ("total", "KXNCAAFTOTAL")):
        events: dict[str, list[dict[str, Any]]] = {}
        for m in kalshi(series):
            events.setdefault(m["event_ticker"], []).append(m)
        for ticker, ms in events.items():
            r = re.search(r"in the (.+?) vs (.+?) college football game originally scheduled for (\w+ \d+, \d{4})", ms[0]["rules_primary"])
            if not r or dt.datetime.strptime(r[3], "%b %d, %Y").date() != day:
                continue
            hits = [(g, side) for g in games if (side := assign((r[1], r[2]), g["away_team"], g["home_team"]))]
            if len(hits) != 1:
                continue
            g, side = hits[0]
            rungs = []
            for m in ms:
                bid, ask = float(m["yes_bid_dollars"]), float(m["yes_ask_dollars"])
                last = float(m["last_price_dollars"]) if m.get("last_price_dollars") else None
                k = float(m["floor_strike"])
                if kind == "total":
                    rungs.append(rung(k, last, bid, ask, False, m["yes_sub_title"]))
                else:
                    team = re.match(r"(.+?) wins by over", m["yes_sub_title"])[1]
                    if team not in side:
                        continue
                    away = side[team] == "away"                                # away by > k: margin > k
                    rungs.append(rung(k if away else -k, last, bid, ask, not away, m["yes_sub_title"]))   # home by > k: margin < -k
                rungs[-1].update(volume=float(m.get("volume_fp") or 0), oi=float(m.get("open_interest_fp") or 0))
            found.setdefault(g["id"], {"event": ticker.split("-", 1)[1]})[kind] = {**line(rungs), "ladder": rungs}
    return found


def poly_ladders(games: list[dict[str, Any]], day: dt.date, team_in) -> dict[str, dict[str, Any]]:
    """{odds id: {"spread": ..., "total": ..., "event": slug}} from Polymarket's cfb events around `day`."""
    a = dt.datetime.combine(day, dt.time(0), dt.timezone.utc)
    evs = []
    for off in range(0, 2000, 100):
        d = get(POLY.format(off=off, a=f"{a:%Y-%m-%dT%H:%M:%SZ}", b=f"{a + dt.timedelta(hours=36):%Y-%m-%dT%H:%M:%SZ}"))
        evs += d
        if len(d) < 100:
            break
    found: dict[str, dict[str, Any]] = {}
    for e in evs:
        ml = next((m for m in e.get("markets", []) if m.get("sportsMarketType") == "moneyline" and m.get("gameStartTime")), None)
        if not ml:
            continue
        names = json.loads(ml["outcomes"])
        start = dt.datetime.fromisoformat(ml["gameStartTime"].replace(" ", "T").replace("+00", "+00:00"))
        hits = [g for g in games if len(names) == 2 and team_in(names[0], g["away_team"]) and team_in(names[1], g["home_team"])
                and abs(dt.datetime.fromisoformat(g["commence_time"].replace("Z", "+00:00")) - start) < dt.timedelta(hours=3)]
        if len(hits) != 1:
            continue
        rec = {"event": e.get("slug")}
        for kind, smt in (("spread", "spreads"), ("total", "totals")):
            rungs = []
            for m in e["markets"]:
                if m.get("sportsMarketType") != smt or m.get("line") is None or m.get("closed"):
                    continue
                first = json.loads(m["outcomes"])[0]
                bid = float(m["bestBid"]) if m.get("bestBid") is not None else None
                ask = float(m["bestAsk"]) if m.get("bestAsk") is not None else None
                last = float(json.loads(m["outcomePrices"])[0]) if m.get("outcomePrices") else None
                k = float(m["line"])
                if kind == "total":
                    rungs.append(rung(k, last, bid, ask, first == "Under", m["question"]))
                elif first in names:                                           # "Spread: T (k)": T's margin > -k
                    away = first == names[0]
                    rungs.append(rung(-k if away else k, last, bid, ask, not away, m["question"]))
                else:
                    continue
                rungs[-1].update(volume=float(m.get("volume") or 0))
            rec[kind] = {**line(rungs), "ladder": rungs}
        found[hits[0]["id"]] = rec
    return found
