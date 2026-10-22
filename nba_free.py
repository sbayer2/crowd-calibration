"""Experiment 14 (docs/PREDICTIONS-NBA.md): NBA moneylines from free sources. No Odds API call is ever made.

A LaunchAgent runs `tick` every 2 minutes:
  - the schedule from ESPN's public scoreboard (Central today and tomorrow), refreshed hourly. A game's start is only
    updated by a refresh taken before that start, so the stored start is the last one listed before tip-off;
  - Jev, blind, once per game before it starts: the two configs of experiments 9-12 (noul_both, bins_plain), told only
    "NBA", "Away vs. Home" (ESPN's full names) and the date. From 14:00 UTC, for games starting within 20 hours and
    more than 5 minutes away. Each request is fresh and stateless;
  - `collect` once an hour, for games that started 3.5 hours to 3 days ago and are not settled yet:
      ESPN       final score and status
      Polymarket the `nba` moneyline matched by team names and start (within 3 h); 1-minute history of the away price
                 from 30 h before the start; the result
      Kalshi     series KXNBAGAME, the game matched by both team names and the date in the market rules (one day either
                 side); 1-minute candles (yes bid, yes ask, last price) of both teams' markets from 13:45 UTC on the
                 game's Central day to the start; each market's result
Records: runs/nba/state.json (schedule), jev.jsonl, data.json (everything `collect` reads, by ESPN game id).

    .venv/bin/python nba_free.py tick         # what the LaunchAgent runs
    .venv/bin/python nba_free.py collect      # the hourly collect, on demand
    .venv/bin/python nba_free.py status
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).parent
OUT = ROOT / "runs" / "nba"
CT = ZoneInfo("America/Chicago")
DAYS = ("2026-10-22", "2026-12-05")                    # Central game days in the sample
SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={d}"
POLY = ("https://gamma-api.polymarket.com/events?tag_slug=nba&closed={closed}&limit=100&offset={off}"
        "&end_date_min={a}&end_date_max={b}")
POLY_HIST = "https://clob.polymarket.com/prices-history?market={token}&startTs={a}&endTs={b}&fidelity=1"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2/markets?series_ticker=KXNBAGAME&min_close_ts={a}&max_close_ts={b}&limit=1000"
CANDLES = ("https://api.elections.kalshi.com/trade-api/v2/series/KXNBAGAME/markets/{ticker}/candlesticks"
           "?start_ts={a}&end_ts={b}&period_interval=1")
KALSHI_NAMES = {"Los Angeles C": "LA Clippers", "Los Angeles L": "Los Angeles Lakers"}   # Kalshi uses cities
JEV_CONFIGS = ["noul_both", "bins_plain"]
EARLY_UTC_HOUR, HORIZON = 14, dt.timedelta(hours=20)
SETTLE, GIVE_UP = dt.timedelta(hours=3.5), dt.timedelta(days=3)


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(t: str) -> dt.datetime:
    return dt.datetime.fromisoformat(t.replace("Z", "+00:00"))


def get(url: str) -> Any:
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "crowd-calibration/0.1"}), timeout=60) as r:
        return json.load(r)


def load(name: str, default: Any) -> Any:
    p = OUT / name
    return json.loads(p.read_text()) if p.exists() else default


def save(name: str, obj: Any) -> None:
    tmp = OUT / f"{name}.{os.getpid()}.tmp"
    tmp.write_text(json.dumps(obj, indent=1))
    tmp.replace(OUT / name)


def append(name: str, rec: dict[str, Any]) -> None:
    with (OUT / name).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")


def in_sample(g: dict[str, Any]) -> bool:
    return DAYS[0] <= g["day"] <= DAYS[1]


# --- matching (pure functions, tested in tests/test_nba_free.py) -----------------------------------------------------

def espn_games(board: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for e in board.get("events", []):
        c = e["competitions"][0]
        side = {x["homeAway"]: x for x in c["competitors"]}
        start = iso(e["date"])
        st = c["status"]["type"]
        out.append({"id": str(e["id"]), "away": side["away"]["team"]["displayName"], "home": side["home"]["team"]["displayName"],
                    "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "day": start.astimezone(CT).date().isoformat(),
                    "status": st["name"], "completed": st.get("completed", False), "neutral": c.get("neutralSite"),
                    "away_score": side["away"].get("score"), "home_score": side["home"].get("score")})
    return out


def merge_schedule(games: dict[str, dict[str, Any]], fresh: list[dict[str, Any]], t: dt.datetime) -> None:
    """Add new games; move a start only when the listing was read before the stored start."""
    for g in fresh:
        old = games.get(g["id"])
        if old is None:
            games[g["id"]] = {**g, "listed_at": t.isoformat()}
        elif t < iso(old["start"]):
            if g["start"] != old["start"]:
                old.setdefault("moves", []).append([t.isoformat(), old["start"], g["start"]])
            old.update(start=g["start"], day=g["day"], status=g["status"], listed_at=t.isoformat())
        else:
            old["status"] = g["status"]


def team_in(name: str, team: str) -> bool:
    """A Polymarket outcome name ("76ers", "Trail Blazers") inside ESPN's full name."""
    return team == name or team.endswith(" " + name)


def kalshi_team(city: str, team: str) -> bool:
    """A Kalshi city name ("Golden State", "Los Angeles C") for ESPN's full name."""
    if city in KALSHI_NAMES:
        return KALSHI_NAMES[city] == team
    return team.startswith(city + " ")


def kalshi_game(rules: str) -> tuple[str, str, dt.date] | None:
    r = re.search(r"wins the (.+?) vs (.+?) Pro Basketball game originally scheduled for (\w+ \d+, \d{4})", rules)
    return (r[1], r[2], dt.datetime.strptime(r[3], "%b %d, %Y").date()) if r else None


def kalshi_match(g: dict[str, Any], events: dict[str, list[dict[str, Any]]]) -> list[str]:
    """Event tickers whose two cities are this game's teams, dated within a day of its Central date."""
    day = dt.date.fromisoformat(g["day"])
    hits = []
    for ticker, ms in events.items():
        k = kalshi_game(ms[0].get("rules_primary", ""))
        if not k or abs((k[2] - day).days) > 1:
            continue
        a, b, _ = k
        if (kalshi_team(a, g["away"]) and kalshi_team(b, g["home"])) or (kalshi_team(a, g["home"]) and kalshi_team(b, g["away"])):
            hits.append(ticker)
    return hits


def early_moment(g: dict[str, Any]) -> dt.datetime:
    return dt.datetime.combine(dt.date.fromisoformat(g["day"]), dt.time(EARLY_UTC_HOUR), dt.timezone.utc)


# --- commands ---------------------------------------------------------------------------------------------------------

def refresh(st: dict[str, Any], t: dt.datetime) -> None:
    today = t.astimezone(CT).date()
    fresh = []
    for d in (today, today + dt.timedelta(days=1)):
        fresh += espn_games(get(SCOREBOARD.format(d=d.strftime("%Y%m%d"))))
    merge_schedule(st["games"], fresh, t)
    st["games_at"] = t.isoformat()


def ask_jev(todo: list[dict[str, Any]], st: dict[str, Any], t: dt.datetime) -> None:
    import jev
    from sports_jev import request, value

    def one(g):
        out = {"id": g["id"], "away": g["away"], "home": g["home"], "commence": g["start"], "asked_at": t.isoformat(),
               "v_away": {}, "answers": {}}
        for cfg in JEV_CONFIGS:
            stt, qs = request(cfg, "NBA", {"a": g["away"], "b": g["home"], "start": g["start"]})
            ans = jev.ask(stt, qs)["answers"]
            out["v_away"][cfg], out["answers"][cfg] = value(cfg, ans), ans
        return out
    with ThreadPoolExecutor(4) as pool:
        for rec in pool.map(one, todo):
            append("jev.jsonl", rec)
            st["jev"].append(rec["id"])
    print(f"{t:%H:%M} Jev asked about {len(todo)} games")


def tick() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    t = now()
    with (OUT / "heartbeat.log").open("a") as fh:
        fh.write(t.isoformat(timespec="seconds") + "\n")
    st = load("state.json", {"games": {}, "games_at": None, "jev": [], "collected_at": None})
    if not st["games_at"] or t - iso(st["games_at"]) > dt.timedelta(minutes=60):
        try:
            refresh(st, t)
        except (OSError, ValueError, KeyError) as exc:                                 # network gap: keep the cache
            print(f"{t:%H:%M} schedule refresh failed ({exc}); using cache from {st['games_at']}")
    todo = [g for g in st["games"].values() if in_sample(g) and g["id"] not in st["jev"] and "POSTPONED" not in g["status"]
            and dt.timedelta(minutes=5) < iso(g["start"]) - t <= HORIZON]
    if todo and t.hour >= EARLY_UTC_HOUR:
        try:
            ask_jev(todo, st, t)
        except Exception as exc:                                                       # retried next tick
            print(f"{t:%H:%M} Jev error: {exc}")
    save("state.json", st)
    if not st.get("collected_at") or t - iso(st["collected_at"]) > dt.timedelta(minutes=60):
        st["collected_at"] = t.isoformat()                                             # failed or not: next try in an hour
        save("state.json", st)
        try:
            collect()
        except (OSError, ValueError, KeyError) as exc:
            print(f"{t:%H:%M} collect failed ({exc!r}); retried next hour")


def settled(r: dict[str, Any]) -> bool:
    k = r.get("kalshi", {})
    return (r.get("espn", {}).get("completed") and r.get("poly", {}).get("away_won") in (0, 1)
            and (k.get("match") is not None or k.get("away_result") in ("yes", "no")))


def collect() -> None:
    import braves
    OUT.mkdir(parents=True, exist_ok=True)
    st = load("state.json", {"games": {}})
    data = load("data.json", {})
    t = now()
    todo = [g for g in st["games"].values() if in_sample(g) and t - GIVE_UP < iso(g["start"]) < t - SETTLE
            and not settled(data.get(g["id"], {}))]
    if not todo:
        print(f"{t:%H:%M} collect: nothing new")
        return
    lo = min(iso(g["start"]) for g in todo) - dt.timedelta(days=1)
    # ESPN: finals by game id
    board = {}
    for d in sorted({g["day"] for g in todo} | {(dt.date.fromisoformat(g["day"]) + dt.timedelta(days=1)).isoformat() for g in todo}):
        for x in espn_games(get(SCOREBOARD.format(d=d.replace("-", "")))):
            board[x["id"]] = x
    # Polymarket: moneylines of nba events closing in the window, open or closed
    found: dict[str, dict] = {}
    for closed in ("true", "false"):
        d = lo
        while d < t:
            d2 = d + dt.timedelta(days=3)
            for off in range(0, 2000, 100):
                evs = get(POLY.format(closed=closed, off=off, a=f"{d:%Y-%m-%dT%H:%M:%SZ}", b=f"{d2:%Y-%m-%dT%H:%M:%SZ}"))
                for e in evs:
                    for m in e.get("markets", []):
                        if m.get("sportsMarketType") == "moneyline" and m.get("gameStartTime"):
                            found[str(m["id"])] = m
                if len(evs) < 100:
                    break
            d = d2
    # Kalshi: every KXNBAGAME market closing in the window, grouped by event
    kal: dict[str, list[dict]] = {}
    cur = ""
    while True:
        r = get(KALSHI.format(a=int(lo.timestamp()), b=int((t + dt.timedelta(days=2)).timestamp())) + (f"&cursor={cur}" if cur else ""))
        for m in r["markets"]:
            kal.setdefault(m["event_ticker"], []).append(m)
        cur = r.get("cursor")
        if not cur or not r["markets"]:
            break
    for g in todo:
        rec = data.setdefault(g["id"], {"away": g["away"], "home": g["home"], "start": g["start"], "day": g["day"]})
        rec.update(start=g["start"], day=g["day"])
        start = iso(g["start"])
        if g["id"] in board:
            rec["espn"] = {k: board[g["id"]][k] for k in ("status", "completed", "neutral", "away_score", "home_score")}
        if rec.get("poly", {}).get("away_won") not in (0, 1):
            cands = [m for m in found.values() if abs(braves.ts(m["gameStartTime"]) - start) < dt.timedelta(hours=3)
                     and len(names := json.loads(m["outcomes"])) == 2 and team_in(names[0], g["away"]) and team_in(names[1], g["home"])]
            if len(cands) != 1:
                rec["poly"] = {"match": f"{len(cands)} candidates"}
            else:
                m = cands[0]
                prices = [float(p) for p in json.loads(m["outcomePrices"])]
                token = json.loads(m["clobTokenIds"])[0]
                hist = (get(POLY_HIST.format(token=token, a=int((start - dt.timedelta(hours=30)).timestamp()),
                                             b=int(start.timestamp()))) or {}).get("history", [])
                rec["poly"] = {"market_id": str(m["id"]), "slug": m.get("slug"), "closed": m.get("closed"),
                               "away_won": int(prices[0] == 1.0) if sorted(prices) == [0.0, 1.0] else None,
                               "volume": float(m.get("volume") or 0), "history_away": hist}
        if rec.get("kalshi", {}).get("away_result") not in ("yes", "no"):
            hits = kalshi_match(g, kal)
            if len(hits) != 1:
                rec["kalshi"] = {"match": f"{len(hits)} candidates"}
            else:
                ms = kal[hits[0]]
                side = {}
                for m in ms:
                    for who in ("away", "home"):
                        if kalshi_team(m.get("yes_sub_title", ""), g[who]):
                            side[who] = m
                if set(side) != {"away", "home"}:
                    rec["kalshi"] = {"match": f"event {hits[0]}: sides {sorted(side)}"}
                else:
                    a, b = int((early_moment(g) - dt.timedelta(minutes=15)).timestamp()), int(start.timestamp())
                    k = {"event": hits[0]}
                    for who, m in side.items():
                        cs = get(CANDLES.format(ticker=m["ticker"], a=a, b=b)).get("candlesticks", [])
                        k[f"{who}_ticker"], k[f"{who}_result"] = m["ticker"], m.get("result") or None
                        k[f"{who}_candles"] = [[c["end_period_ts"], c["yes_bid"].get("close_dollars"), c["yes_ask"].get("close_dollars"),
                                               c["price"].get("close_dollars")] for c in cs]
                    rec["kalshi"] = k
    save("data.json", data)
    n = sum(1 for g in st["games"].values() if g["id"] in data)
    print(f"{t:%H:%M} collect: {len(todo)} games checked; {sum(settled(r) for r in data.values())} settled of {n}")


def status() -> None:
    st, data = load("state.json", {"games": {}}), load("data.json", {})
    t = now()
    games = [g for g in st["games"].values() if in_sample(g)]
    past = [g for g in games if iso(g["start"]) < t]
    jev = {json.loads(l)["id"]: json.loads(l) for l in (OUT / "jev.jsonl").open()} if (OUT / "jev.jsonl").exists() else {}
    on_time = sum(1 for g in past if g["id"] in jev and iso(jev[g["id"]]["asked_at"]) < iso(g["start"]))
    print(f"NBA: {len(games)} games listed in the sample, {len(past)} started; Jev before start {on_time}/{len(past)}; "
          f"collected {len(data)}, settled {sum(settled(r) for r in data.values())}; schedule read {st.get('games_at')}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("tick", "collect", "status"))
    {"tick": tick, "collect": collect, "status": status}[ap.parse_args().cmd]()
