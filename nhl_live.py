"""Experiment 9: NHL, live — crowd or book? And what is Jev agreeing with?

Collected going forward (The Odds API free tier has no history). A LaunchAgent runs `tick` every 5 minutes:
  - the schedule (free) from The Odds API, refreshed hourly;
  - Pinnacle + Matchbook moneylines (1 credit per call, all games at once) at three moments:
      early  once a day, first tick after 14:00 UTC (covers games in the next 20 h)
      t60    45-70 min before each start-time slot
      t5     1-12 min before each start-time slot
  - Jev, blind, once per game before it starts: two configs from experiment 8 (noul_both, bins_plain),
    told only "NHL", "Away vs. Home" and the date. Each request is fresh and stateless.
Polymarket prices (1-minute history at the snapshot times) and results are fetched afterwards (`collect-poly`).
Credit guard: at most DAILY_CAP odds calls per UTC day; none below MIN_REMAINING credits.

    .venv/bin/python nhl_live.py tick            # what the LaunchAgent runs
    .venv/bin/python nhl_live.py status
    .venv/bin/python nhl_live.py collect-poly    # after games: Polymarket prices + results
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
OUT = ROOT / "runs" / "nhl"
API = "https://api.the-odds-api.com/v4/sports/icehockey_nhl/"
EARLY_UTC_HOUR, EARLY_HORIZON_H, DAILY_CAP, MIN_REMAINING = 14, 20, 16, 25
WINDOWS = {"t60": (45, 70), "t5": (1, 12)}               # minutes before the slot's start
JEV_CONFIGS = ["noul_both", "bins_plain"]


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(t: str) -> dt.datetime:
    return dt.datetime.fromisoformat(t.replace("Z", "+00:00"))


def odds_api(path: str, **q: str) -> tuple[Any, dict[str, str | None]]:
    q["apiKey"] = os.environ["ODDS_API_KEY"]
    url = API + path + "?" + "&".join(f"{k}={v}" for k, v in q.items())
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "crowd-calibration/0.1"}), timeout=30) as r:
        return json.load(r), {k: r.headers.get(k) for k in ("x-requests-used", "x-requests-remaining", "x-requests-last")}


def load(name: str, default: Any) -> Any:
    p = OUT / name
    return json.loads(p.read_text()) if p.exists() else default


def save(name: str, obj: Any) -> None:
    tmp = OUT / (name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1))
    tmp.replace(OUT / name)


def append(name: str, rec: dict[str, Any]) -> None:
    with (OUT / name).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")


def snapshot(keys: list[str], st: dict[str, Any], t: dt.datetime) -> None:
    day = t.date().isoformat()
    if st["calls"].get(day, 0) >= DAILY_CAP or int(st.get("remaining") or 500) < MIN_REMAINING:
        print(f"{t:%H:%M} SKIP {keys}: credit guard (today {st['calls'].get(day, 0)}, remaining {st.get('remaining')})")
        return
    data, h = odds_api("odds", regions="eu", markets="h2h", oddsFormat="decimal", bookmakers="pinnacle,matchbook")
    st["calls"][day] = st["calls"].get(day, 0) + 1
    st["remaining"] = h["x-requests-remaining"]
    append("snapshots.jsonl", {"keys": keys, "fetched_at": t.isoformat(), "credits": h, "events": data})
    for k in keys:
        st["done"][k] = t.isoformat()
    n_pin = sum(any(b["key"] == "pinnacle" for b in e["bookmakers"]) for e in data)
    print(f"{t:%H:%M} snapshot {keys}: {len(data)} games, {n_pin} with Pinnacle; credits left {h['x-requests-remaining']}")


def ask_jev(events: list[dict[str, Any]], st: dict[str, Any], t: dt.datetime) -> None:
    import jev
    from sports_jev import request, value
    todo = [e for e in events if e["id"] not in st["jev"]]

    def one(e):
        g = {"a": e["away_team"], "b": e["home_team"], "start": e["commence_time"]}       # Polymarket order: away vs. home
        out = {"id": e["id"], "away": e["away_team"], "home": e["home_team"], "commence": e["commence_time"],
               "asked_at": t.isoformat(), "v_away": {}, "answers": {}}
        for cfg in JEV_CONFIGS:
            stt, qs = request(cfg, "NHL", g)
            ans = jev.ask(stt, qs)["answers"]
            out["v_away"][cfg], out["answers"][cfg] = value(cfg, ans), ans
        return out
    with ThreadPoolExecutor(4) as pool:
        for rec in pool.map(one, todo):
            append("jev.jsonl", rec)
            st["jev"].append(rec["id"])
    if todo:
        print(f"{t:%H:%M} Jev asked about {len(todo)} games")


def tick() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    t = now()
    st = load("state.json", {"events": [], "events_at": None, "done": {}, "calls": {}, "remaining": None, "jev": []})
    if not st["events_at"] or t - iso(st["events_at"]) > dt.timedelta(minutes=60):
        try:
            st["events"], _ = odds_api("events")                                      # free
            st["events_at"] = t.isoformat()
        except OSError as exc:                                                         # network gap: keep the cached schedule
            print(f"{t:%H:%M} schedule refresh failed ({exc}); using cache from {st['events_at']}")
    ahead = [e for e in st["events"] if dt.timedelta(0) < iso(e["commence_time"]) - t <= dt.timedelta(hours=EARLY_HORIZON_H)]
    due = []
    early_key = f"early:{t.date().isoformat()}"
    if t.hour >= EARLY_UTC_HOUR and early_key not in st["done"] and ahead:
        due.append(early_key)
    for slot in sorted({e["commence_time"] for e in ahead}):
        mins = (iso(slot) - t).total_seconds() / 60
        for kind, (lo, hi) in WINDOWS.items():
            k = f"{kind}:{slot}"
            if lo <= mins <= hi and k not in st["done"]:
                due.append(k)
    if due:
        try:
            snapshot(due, st, t)
        except OSError as exc:                                                         # not marked done: the next tick retries
            print(f"{t:%H:%M} snapshot {due} failed ({exc}); will retry while the window is open")
    soon = [e for e in ahead if iso(e["commence_time"]) - t > dt.timedelta(minutes=5)]
    if soon and (early_key in st["done"] or t.hour >= EARLY_UTC_HOUR):
        try:
            ask_jev(soon, st, t)
        except Exception as exc:                                                       # Jev trouble must not stop odds
            print(f"{t:%H:%M} Jev error: {exc}")
    save("state.json", st)


def status() -> None:
    st = load("state.json", {})
    snaps = [json.loads(l) for l in (OUT / "snapshots.jsonl").open()] if (OUT / "snapshots.jsonl").exists() else []
    kinds = {}
    for s in snaps:
        for k in s["keys"]:
            kinds[k.split(":")[0]] = kinds.get(k.split(":")[0], 0) + 1
    games = {e["id"] for s in snaps for e in s["events"]}
    print(f"snapshots {len(snaps)} ({kinds}); games seen {len(games)}; Jev-asked {len(st.get('jev', []))}; "
          f"credits left {st.get('remaining')}; calls by day {st.get('calls')}")


def collect_poly() -> None:
    """After games: match each game to its Polymarket moneyline, store the 1-minute price history and the result."""
    import braves
    snaps = [json.loads(l) for l in (OUT / "snapshots.jsonl").open()]
    games = {e["id"]: e for s in snaps for e in s["events"]}
    poly = load("poly.json", {})
    t = now()
    todo = [g for g in games.values() if g["id"] not in poly and iso(g["commence_time"]) < t - dt.timedelta(hours=5)]
    if not todo:
        print("nothing new to collect")
        return
    lo = min(iso(g["commence_time"]) for g in todo) - dt.timedelta(days=1)
    markets = []
    d = lo
    while d < t:
        d2 = d + dt.timedelta(days=3)
        for off in range(0, 2000, 100):
            evs = braves.get(braves.EVENTS.format(tag="nhl", off=off, a=d.strftime("%Y-%m-%dT%H:%M:%SZ"), b=d2.strftime("%Y-%m-%dT%H:%M:%SZ")))
            if not evs:
                break
            markets += [m for e in evs for m in e.get("markets", []) if m.get("sportsMarketType") == "moneyline" and m.get("gameStartTime")]
            if len(evs) < 100:
                break
        d = d2
    for g in todo:
        cands = [m for m in markets if abs(braves.ts(m["gameStartTime"]) - iso(g["commence_time"])) < dt.timedelta(hours=3)
                 and (names := json.loads(m["outcomes"])) and len(names) == 2
                 and names[0] in g["away_team"] and names[1] in g["home_team"]]
        if len(cands) != 1:
            poly[g["id"]] = {"match": f"{len(cands)} candidates"}
            continue
        m = cands[0]
        prices = [float(p) for p in json.loads(m["outcomePrices"])]
        start = iso(g["commence_time"])
        token_away = json.loads(m["clobTokenIds"])[0]
        hist = (braves.get(f"https://clob.polymarket.com/prices-history?market={token_away}&startTs={int((start - dt.timedelta(hours=30)).timestamp())}"
                           f"&endTs={int(start.timestamp())}&fidelity=1") or {}).get("history", [])
        poly[g["id"]] = {"market_id": str(m["id"]), "title": m["question"], "closed": m.get("closed"),
                         "away_won": int(prices[0] == 1.0) if sorted(prices) == [0.0, 1.0] else None,
                         "volume": float(m.get("volume") or 0), "history_away": hist}
    save("poly.json", poly)
    ok = sum(1 for v in poly.values() if "market_id" in v)
    print(f"Polymarket: {len(todo)} new games; matched {ok} of {len(poly)} total")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("tick", "status", "collect-poly"))
    {"tick": tick, "status": status, "collect-poly": collect_poly}[ap.parse_args().cmd]()
