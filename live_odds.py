"""Experiments 9 (NHL), 10 (MLB postseason) and 12 (NCAA football, AP Top 25 games on Saturdays), live — crowd or book? And what is Jev agreeing with?

Collected going forward (The Odds API free tier has no history). A LaunchAgent runs `tick` every 5 minutes:
  - the schedule (free) from The Odds API, refreshed hourly;
  - Pinnacle + Matchbook moneylines (1 credit per call, all games at once) at three moments:
      early  once a day, first tick after 14:00 UTC (covers games in the next 20 h)
      t60    45-70 min before each start-time slot
      t5     1-12 min before each start-time slot
  - Jev, blind, once per game before it starts: two configs from experiment 8 (noul_both, bins_plain),
    told only the league, "Away vs. Home" and the date. Each request is fresh and stateless.
Polymarket prices (1-minute history at the snapshot times) and results are fetched afterwards (`collect-poly`).
Credit guard: at most DAILY_CAP odds calls per sport per UTC day; none below MIN_REMAINING credits (shared key, read
from the newest snapshot of any sport). Until NCAAF_RESERVE_UNTIL, NCAA football also leaves RESERVE_PER_DAY credits a
day for the NHL and MLB arms.
One LaunchAgent per sport; each sport keeps its own state in runs/<sport>/.
NCAA football is limited to games on the listed Saturdays (US Central date) with an AP Top 25 team. The poll is read
from ESPN's public rankings feed and frozen the first time a tick runs on each of those days.
Experiment 13 (NCAA football only, docs/PREDICTIONS-SPREADS.md): the first tick at or after Wednesday 11:00 Central before
each listed Saturday (late up to Thursday 11:00) reads Kalshi and Polymarket spread/total ladders (`ladders.py`), then
Pinnacle + Matchbook spreads and totals (2 credits, same guard), for that Saturday's games with a team in the current AP
poll; then asks Jev, blind, for the margin and the total. Records: runs/ncaaf/t72.jsonl (raw odds: t72_odds.jsonl).
`collect-scores` stores ESPN final scores (runs/ncaaf/scores.json).

    .venv/bin/python live_odds.py --sport nhl tick            # what the LaunchAgents run (--sport nhl | mlb | ncaaf)
    .venv/bin/python live_odds.py --sport mlb status
    .venv/bin/python live_odds.py --sport mlb collect-poly    # after games: Polymarket prices + results
    .venv/bin/python live_odds.py --sport ncaaf collect-scores  # after games: ESPN final scores
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

from dotenv import load_dotenv

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")                                # ODDS_API_KEY; the LaunchAgents also export it
SPORTS = {   # odds-api key, league name told to Jev, Polymarket tags (windowed scan), tags read whole (few, long-dated events)
    "nhl": {"key": "icehockey_nhl", "league": "NHL", "tags": ["nhl"], "whole": []},
    "mlb": {"key": "baseball_mlb", "league": "MLB", "tags": ["mlb"], "whole": ["mlb-playoffs"]},
    "ncaaf": {"key": "americanfootball_ncaaf", "league": "NCAA football", "tags": ["cfb"], "whole": [],
              "top25_days": ["2026-10-10", "2026-10-17", "2026-10-24", "2026-10-31", "2026-11-07", "2026-11-14",
                             "2026-11-21", "2026-11-28", "2026-12-05"], "open_events": True},   # cfb events stay open after the moneyline resolves
}
CT = ZoneInfo("America/Chicago")
RANKINGS = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/rankings"
SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard?dates={d}&groups=80&limit=500"
SPORT = "nhl"
OUT = ROOT / "runs" / SPORT
API = f"https://api.the-odds-api.com/v4/sports/{SPORTS[SPORT]['key']}/"
EARLY_UTC_HOUR, EARLY_HORIZON_H, DAILY_CAP, MIN_REMAINING = 14, 20, 24, 25
NCAAF_RESERVE_UNTIL, RESERVE_PER_DAY = dt.date(2026, 11, 6), 12          # protect experiment 9 through its stop date
WINDOWS = {"t60": (45, 70), "t5": (1, 12)}               # minutes before the slot's start
JEV_CONFIGS = ["noul_both", "bins_plain"]
T72_AT, T72_LATE = dt.time(11, 0), dt.timedelta(minutes=15)     # Wednesday 11:00 Central; flagged late after 15 minutes


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
    tmp = OUT / f"{name}.{os.getpid()}.tmp"                                           # concurrent runs must not share it
    tmp.write_text(json.dumps(obj, indent=1))
    tmp.replace(OUT / name)


def append(name: str, rec: dict[str, Any]) -> None:
    with (OUT / name).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")


def local_day(e: dict[str, Any]) -> str:
    return iso(e["commence_time"]).astimezone(CT).date().isoformat()


def get(url: str) -> Any:
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "crowd-calibration/0.1"}), timeout=30) as r:
        return json.load(r)


def ap_poll() -> tuple[str | None, dict[str, int]]:
    """The current AP poll from ESPN: (headline, {Odds API-style team name: rank})."""
    ap = next(x for x in get(RANKINGS)["rankings"] if x.get("shortName", "").startswith("AP"))
    return ap.get("headline"), {x["team"]["location"] + " " + x["team"]["name"]: x["current"] for x in ap["ranks"]}


def in_scope(st: dict[str, Any], t: dt.datetime) -> list[dict[str, Any]]:
    """The games this sport collects. All of them, except NCAA football: Top 25 games on the listed Saturdays."""
    days = SPORTS[SPORT].get("top25_days")
    if not days:
        return st["events"]
    top = st.setdefault("top25", {})
    day = t.astimezone(CT).date().isoformat()
    if day in days and day not in top:
        try:
            headline, ranks = ap_poll()
            top[day] = {"poll": headline, "fetched_at": t.isoformat(), "ranks": ranks}
            playing = {n for e in st["events"] if local_day(e) == day for n in (e["away_team"], e["home_team"])}
            print(f"{t:%H:%M} froze {headline} for {day}; ranked teams without a game listed: "
                  f"{sorted(n for n in ranks if n not in playing)}")
        except (OSError, KeyError, StopIteration) as exc:                              # retried next tick
            print(f"{t:%H:%M} rankings fetch failed ({exc!r})")
    keep = [e for e in st["events"] if (rk := top.get(local_day(e), {}).get("ranks"))
            and (e["away_team"] in rk or e["home_team"] in rk)]
    st["scope"] = sorted(set(st.get("scope", [])) | {e["id"] for e in keep})
    return keep


def shared_remaining(own: str | None) -> int:
    """Credits left on the shared key: the newest snapshot of any sport (each state file sees only its own calls)."""
    newest = (None, int(own or 500))
    for p in (ROOT / "runs" / sp / f for sp in SPORTS for f in ("snapshots.jsonl", "t72_odds.jsonl")):
        if not p.exists():
            continue
        with p.open("rb") as fh:
            fh.seek(0, 2)
            fh.seek(max(0, fh.tell() - 2_000_000))
            lines = fh.read().splitlines()
        if not lines:
            continue
        rec = json.loads(lines[-1])
        if (left := rec["credits"].get("x-requests-remaining")) and (newest[0] is None or rec["fetched_at"] > newest[0]):
            newest = (rec["fetched_at"], int(float(left)))
    return newest[1]


def credit_ok(keys: list[str], st: dict[str, Any], t: dt.datetime, cost: int = 1) -> bool:
    day = t.date().isoformat()
    left = shared_remaining(st.get("remaining"))
    floor = MIN_REMAINING
    if SPORT == "ncaaf" and t.date() < NCAAF_RESERVE_UNTIL:
        floor += RESERVE_PER_DAY * (NCAAF_RESERVE_UNTIL - t.date()).days
    if st["calls"].get(day, 0) >= DAILY_CAP or left - cost < floor - 1:
        print(f"{t:%H:%M} SKIP {keys}: credit guard (today {st['calls'].get(day, 0)}, remaining {left}, floor {floor})")
        return False
    return True


def snapshot(keys: list[str], st: dict[str, Any], t: dt.datetime) -> None:
    day = t.date().isoformat()
    if not credit_ok(keys, st, t):
        return
    data, h = odds_api("odds", regions="eu", markets="h2h", oddsFormat="decimal", bookmakers="pinnacle,matchbook")
    st["calls"][day] = st["calls"].get(day, 0) + 1
    st["remaining"] = h["x-requests-remaining"]
    append("snapshots.jsonl", {"keys": keys, "fetched_at": t.isoformat(), "credits": h, "events": data})
    for k in keys:
        st["done"][k] = t.isoformat()
    moved = {e["id"]: e["commence_time"] for e in data}                              # kickoffs move: follow each snapshot,
    for e in st["events"]:                                                             # not only the hourly schedule refresh
        if e["id"] in moved and moved[e["id"]] != e["commence_time"] and iso(moved[e["id"]]) > t:
            e["commence_time"] = moved[e["id"]]
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
        if (rk := st.get("top25", {}).get(local_day(e), {}).get("ranks")) is not None:
            out["ranks"] = {"away": rk.get(e["away_team"]), "home": rk.get(e["home_team"])}
        for cfg in JEV_CONFIGS:
            stt, qs = request(cfg, SPORTS[SPORT]["league"], g)
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
    with (OUT / "heartbeat.log").open("a") as fh:                                     # one line per run, to diagnose gaps
        fh.write(t.isoformat(timespec="seconds") + "\n")
    st = load("state.json", {"events": [], "events_at": None, "done": {}, "calls": {}, "remaining": None, "jev": []})
    if not st["events_at"] or t - iso(st["events_at"]) > dt.timedelta(minutes=60):
        try:
            st["events"], _ = odds_api("events")                                      # free
            st["events_at"] = t.isoformat()
        except OSError as exc:                                                         # network gap: keep the cached schedule
            print(f"{t:%H:%M} schedule refresh failed ({exc}); using cache from {st['events_at']}")
    ahead = [e for e in in_scope(st, t) if dt.timedelta(0) < iso(e["commence_time"]) - t <= dt.timedelta(hours=EARLY_HORIZON_H)]
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
    if SPORT == "ncaaf":
        try:
            t72(st, t)
        except Exception as exc:                                                       # not marked done: the next tick retries
            print(f"{t:%H:%M} t72 failed ({exc!r}); will retry while the window is open")
    save("state.json", st)


def t72_window(st: dict[str, Any], t: dt.datetime) -> tuple[str, dt.date, dt.datetime] | None:
    """The experiment 13 snapshot whose window (Wednesday 11:00 Central to Thursday 11:00) holds `t`, if any."""
    for d in SPORTS[SPORT].get("top25_days", []):
        sat = dt.date.fromisoformat(d)
        opens = dt.datetime.combine(sat - dt.timedelta(days=3), T72_AT, CT)
        if opens <= t < opens + dt.timedelta(days=1):
            return f"t72:{d}", sat, opens
    return None


def pinnacle_lines(e: dict[str, Any] | None) -> dict[str, Any] | None:
    """Pinnacle's margin line (away - home) and total, with each side's no-vig probability."""
    b = next((b for b in (e or {}).get("bookmakers", []) if b["key"] == "pinnacle"), None)
    if not b:
        return None
    out = {"last_update": b.get("last_update")}
    for m in b["markets"]:
        o = {x["name"]: x for x in m["outcomes"]}
        if m["key"] == "spreads" and e["away_team"] in o and e["home_team"] in o:
            a, h = o[e["away_team"]], o[e["home_team"]]
            out["spread"] = -a["point"]                                                # away +7.5 -> margin line -7.5
            out["p_away_covers"] = (1 / a["price"]) / (1 / a["price"] + 1 / h["price"])
        if m["key"] == "totals" and "Over" in o and "Under" in o:
            out["total"] = o["Over"]["point"]
            out["p_over"] = (1 / o["Over"]["price"]) / (1 / o["Over"]["price"] + 1 / o["Under"]["price"])
    return out


def t72(st: dict[str, Any], t: dt.datetime) -> None:
    """Experiment 13: every source read at one moment, about three days before the Saturday; then Jev."""
    import ladders
    w = t72_window(st, t)
    if not w:
        return
    key, sat, opens = w
    wk = st.setdefault("t72", {}).setdefault(key, {"games": [], "jev": []})
    if key not in st["done"]:
        headline, ranks = ap_poll()
        games = [e for e in st["events"] if local_day(e) == sat.isoformat() and (e["away_team"] in ranks or e["home_team"] in ranks)]
        if not games:
            print(f"{t:%H:%M} {key}: no ranked games listed yet; will retry")
            return
        kal = ladders.kalshi_ladders(games, sat)                                      # free sources first: if one fails,
        pol = ladders.poly_ladders(games, sat, team_in)                                # no credits are spent
        if not credit_ok([key], st, t, cost=2):
            return
        lo = dt.datetime.combine(sat, dt.time(0), CT).astimezone(dt.timezone.utc)
        data, h = odds_api("odds", regions="eu", markets="spreads,totals", oddsFormat="decimal", bookmakers="pinnacle,matchbook",
                           commenceTimeFrom=f"{lo:%Y-%m-%dT%H:%M:%SZ}", commenceTimeTo=f"{lo + dt.timedelta(days=1):%Y-%m-%dT%H:%M:%SZ}")
        day = t.date().isoformat()
        st["calls"][day] = st["calls"].get(day, 0) + 1
        st["remaining"] = h["x-requests-remaining"]
        append("t72_odds.jsonl", {"keys": [key], "fetched_at": t.isoformat(), "credits": h, "events": data})
        odds = {e["id"]: e for e in data}
        late = t - opens > T72_LATE
        append("t72.jsonl", {"kind": "poll", "key": key, "taken_at": t.isoformat(), "poll": headline, "ranks": ranks})
        for g in games:
            append("t72.jsonl", {"kind": "market", "key": key, "id": g["id"], "away": g["away_team"], "home": g["home_team"],
                                 "commence": g["commence_time"], "taken_at": t.isoformat(), "late": late,
                                 "lead_h": round((iso(g["commence_time"]) - t).total_seconds() / 3600, 2),
                                 "ranks": {"away": ranks.get(g["away_team"]), "home": ranks.get(g["home_team"])},
                                 "pinnacle": pinnacle_lines(odds.get(g["id"])), "kalshi": kal.get(g["id"]), "polymarket": pol.get(g["id"])})
        wk["games"] = [{k: g[k] for k in ("id", "away_team", "home_team", "commence_time")} for g in games]
        st["done"][key] = t.isoformat()
        save("state.json", st)                                                         # the snapshot stands even if Jev fails
        line = lambda src, k: sum(1 for x in src.values() if (x.get(k) or {}).get("line") is not None)
        print(f"{t:%H:%M} {key}{' (late)' if late else ''}: {len(games)} games; Pinnacle {sum(bool(pinnacle_lines(odds.get(g['id']))) for g in games)}, "
              f"Kalshi spread/total lines {line(kal, 'spread')}/{line(kal, 'total')}, Polymarket {line(pol, 'spread')}/{line(pol, 'total')}; "
              f"credits left {h['x-requests-remaining']}")
    todo = [g for g in wk["games"] if g["id"] not in wk["jev"]]
    if todo:
        with ThreadPoolExecutor(4) as pool:
            for g, rec in zip(todo, pool.map(lambda g: t72_jev(g, sat, t), todo)):
                if rec:
                    append("t72.jsonl", rec)
                    wk["jev"].append(g["id"])
        print(f"{t:%H:%M} {key}: Jev answered {len(wk['jev'])}/{len(wk['games'])}")


def t72_jev(g: dict[str, Any], sat: dt.date, t: dt.datetime) -> dict[str, Any] | None:
    """Blind Jev: one fresh request per game with the margin and total questions. None on failure (retried next tick)."""
    import jev
    import ladders
    from braves_opt import instr
    a, h = g["away_team"], g["home_team"]
    qs = {"margin": {"type": "score", "instructions": instr("Which team wins this game, and by how many points?", "plain"),
                     "criteria": [l.format(a=a, h=h) for l in ladders.MARGIN_LEVELS]},
          "total": {"type": "score", "instructions": instr("How many points will the two teams score in total?", "plain"),
                    "criteria": ladders.TOTAL_LEVELS}}
    try:
        ans = jev.ask(f"NCAA football game: {a} vs. {h}, {sat}.", qs)["answers"]
        m_med, m_ev = ladders.dist_line(ans["margin"]["probabilities"], ladders.MARGIN_BINS, ladders.MARGIN_MIDS)
        t_med, t_ev = ladders.dist_line(ans["total"]["probabilities"], ladders.TOTAL_BINS, ladders.TOTAL_MIDS)
    except Exception as exc:                                                           # Jev trouble must not stop the arm
        print(f"{t:%H:%M} t72 Jev error for {a} @ {h}: {exc}")
        return None
    return {"kind": "jev", "id": g["id"], "away": a, "home": h, "asked_at": now().isoformat(), "answers": ans,
            "margin_median": m_med, "margin_ev": m_ev, "total_median": t_med, "total_ev": t_ev}


def status() -> None:
    st = load("state.json", {})
    snaps = [json.loads(l) for l in (OUT / "snapshots.jsonl").open()] if (OUT / "snapshots.jsonl").exists() else []
    kinds = {}
    for s in snaps:
        for k in s["keys"]:
            kinds[k.split(":")[0]] = kinds.get(k.split(":")[0], 0) + 1
    games = {e["id"] for s in snaps for e in s["events"]}
    if "scope" in st:
        games &= set(st["scope"])
    print(f"snapshots {len(snaps)} ({kinds}); games seen {len(games)}; Jev-asked {len(st.get('jev', []))}; "
          f"credits left {st.get('remaining')}; calls by day {st.get('calls')}")


def team_in(name: str, team: str) -> bool:
    """A Polymarket outcome name inside an Odds API team name; a trailing state tag ("Miami (FL)") may be dropped."""
    return name in team or re.sub(r" \([A-Z]{2}\)$", "", name) in team


def collect_poly() -> None:
    """After games: match each game to its Polymarket moneyline, store the 1-minute price history and the result."""
    import braves
    snaps = [json.loads(l) for l in (OUT / "snapshots.jsonl").open()]
    games = {e["id"]: e for s in snaps for e in s["events"]}
    if "scope" in (st := load("state.json", {})):
        games = {k: g for k, g in games.items() if k in st["scope"]}
    poly = load("poly.json", {})
    t = now()
    retry = lambda g: g["id"] not in poly or (poly[g["id"]].get("away_won") is None and iso(g["commence_time"]) > t - dt.timedelta(days=3))
    todo = [g for g in games.values() if retry(g) and iso(g["commence_time"]) < t - dt.timedelta(hours=5)]
    if not todo:
        print("nothing new to collect")
        return
    lo = min(iso(g["commence_time"]) for g in todo) - dt.timedelta(days=1)
    found: dict[str, dict] = {}

    def take(evs):
        for e in evs:
            for m in e.get("markets", []):
                if m.get("sportsMarketType") == "moneyline" and m.get("gameStartTime"):
                    found[str(m["id"])] = m
    urls = [braves.EVENTS] + ([braves.EVENTS.replace("closed=true", "closed=false")] if SPORTS[SPORT].get("open_events") else [])
    for tag in SPORTS[SPORT]["tags"]:
        for url in urls:
            d = lo
            while d < t:
                d2 = d + dt.timedelta(days=3)
                for off in range(0, 2000, 100):
                    evs = braves.get(url.format(tag=tag, off=off, a=d.strftime("%Y-%m-%dT%H:%M:%SZ"), b=d2.strftime("%Y-%m-%dT%H:%M:%SZ")))
                    if not evs:
                        break
                    take(evs)
                    if len(evs) < 100:
                        break
                d = d2
    for tag in SPORTS[SPORT]["whole"]:
        for off in range(0, 1000, 100):
            evs = braves.get(f"https://gamma-api.polymarket.com/events?tag_slug={tag}&closed=true&limit=100&offset={off}")
            if not evs:
                break
            take(evs)
            if len(evs) < 100:
                break
    markets = list(found.values())
    for g in todo:
        cands = [m for m in markets if abs(braves.ts(m["gameStartTime"]) - iso(g["commence_time"])) < dt.timedelta(hours=3)
                 and (names := json.loads(m["outcomes"])) and len(names) == 2
                 and team_in(names[0], g["away_team"]) and team_in(names[1], g["home_team"])]
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


def collect_scores() -> None:
    """After games: ESPN final scores for experiment 13's games and the experiment 12 scope (runs/<sport>/scores.json)."""
    import unicodedata
    norm = lambda n: unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode().replace("'", "").lower()
    games = {}
    if (OUT / "t72.jsonl").exists():
        for l in (OUT / "t72.jsonl").open():
            if (r := json.loads(l))["kind"] == "market":
                games[r["id"]] = {"id": r["id"], "away_team": r["away"], "home_team": r["home"], "commence_time": r["commence"]}
    st = load("state.json", {})
    if (OUT / "snapshots.jsonl").exists():
        for l in (OUT / "snapshots.jsonl").open():
            for e in json.loads(l)["events"]:
                if e["id"] in st.get("scope", []):
                    games.setdefault(e["id"], e)
    scores = load("scores.json", {})
    t = now()
    todo = [g for g in games.values() if not scores.get(g["id"], {}).get("completed")
            and iso(g["commence_time"]) < t - dt.timedelta(hours=5) and iso(g["commence_time"]) > t - dt.timedelta(days=10)]
    if not todo:
        print("nothing new to collect")
        return
    days = sorted({local_day(g) for g in todo})
    board = {}
    for d in days + [(dt.date.fromisoformat(d) + dt.timedelta(days=1)).isoformat() for d in days]:
        for e in get(SCOREBOARD.format(d=d.replace("-", "")))["events"]:
            c = e["competitions"][0]
            teams = {norm(x["team"]["displayName"]): x for x in c["competitors"]}
            board[frozenset(teams)] = {"espn_id": e["id"], "date": e["date"], "status": c["status"]["type"]["name"],
                                       "completed": c["status"]["type"]["completed"], "neutral": c.get("neutralSite"), "teams": teams}
    for g in todo:
        a, h = norm(g["away_team"]), norm(g["home_team"])
        b = board.get(frozenset((a, h)))
        if not b:
            scores[g["id"]] = {"match": "none", "away": g["away_team"], "home": g["home_team"]}
            continue
        sa, sh = b["teams"][a].get("score"), b["teams"][h].get("score")
        scores[g["id"]] = {"away": g["away_team"], "home": g["home_team"], "espn_id": b["espn_id"], "status": b["status"],
                           "completed": b["completed"], "neutral": b["neutral"], "espn_home": b["teams"][h]["homeAway"] == "home",
                           "away_score": int(sa) if sa not in (None, "") else None, "home_score": int(sh) if sh not in (None, "") else None}
    save("scores.json", scores)
    done = sum(1 for v in scores.values() if v.get("completed"))
    print(f"ESPN: {len(todo)} games checked; {done} final of {len(scores)}; unmatched {sum(1 for v in scores.values() if v.get('match') == 'none')}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sport", choices=tuple(SPORTS), default="nhl")
    ap.add_argument("cmd", choices=("tick", "status", "collect-poly", "collect-scores"))
    a = ap.parse_args()
    SPORT, OUT = a.sport, ROOT / "runs" / a.sport
    API = f"https://api.the-odds-api.com/v4/sports/{SPORTS[a.sport]['key']}/"
    {"tick": tick, "status": status, "collect-poly": collect_poly, "collect-scores": collect_scores}[a.cmd]()
