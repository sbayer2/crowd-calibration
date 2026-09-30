"""Select and freeze upcoming game moneylines from Polymarket's public Gamma API (no account, read-only).

Games are found through /events by sport tag (the /markets date window misses most of them). Kept: moneyline markets
with a gameStartTime at least MIN_LEAD after now and within --hours, both quotes present, spread <= MAX_SPREAD,
liquidity >= MIN_LIQUIDITY. Price = the bid-ask midpoint for the first-listed team (outcome A).

    .venv/bin/python games.py --dry-run --hours 168      # this week's games and their prices
    .venv/bin/python games.py --hours 30                 # freeze the next 30 hours to runs/games-<stamp>.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
API = "https://gamma-api.polymarket.com/events"
SPORTS = ("mlb", "nhl", "nfl", "nba", "wnba")
MIN_LEAD = dt.timedelta(minutes=20)
MAX_SPREAD, MIN_LIQUIDITY = 0.03, 20_000
PAGE, MAX_PAGES = 100, 10


def fetch_events(tag: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for page in range(MAX_PAGES):
        url = f"{API}?tag_slug={tag}&active=true&closed=false&limit={PAGE}&offset={page * PAGE}"
        req = urllib.request.Request(url, headers={"User-Agent": "crowd-calibration/0.1"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                batch = json.load(r)
        except urllib.error.HTTPError as exc:
            if exc.code == 422:
                break
            raise
        out += batch
        if len(batch) < PAGE:
            break
    return out


def parse_time(s: str) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(s.replace(" ", "T").replace("Z", "+00:00").replace("+00", "+00:00")
                                         if "+00:00" not in s else s.replace(" ", "T"))
    except ValueError:
        return None


def games(hours: float, now: dt.datetime) -> tuple[list[dict[str, Any]], Counter]:
    seen, out, dropped = set(), [], Counter()
    for tag in SPORTS:
        for ev in fetch_events(tag):
            for m in ev.get("markets", []):
                if m.get("sportsMarketType") != "moneyline" or m["id"] in seen:
                    continue
                seen.add(m["id"])
                start = parse_time(m.get("gameStartTime") or "")
                teams = json.loads(m.get("outcomes") or "[]")
                if start is None or len(teams) != 2:
                    dropped["no start/teams"] += 1
                    continue
                if not now + MIN_LEAD <= start <= now + dt.timedelta(hours=hours):
                    continue
                try:
                    bid, ask = float(m["bestBid"]), float(m["bestAsk"])
                except (KeyError, TypeError, ValueError):
                    dropped["no quotes"] += 1
                    continue
                if ask - bid > MAX_SPREAD:
                    dropped["wide spread"] += 1
                    continue
                if float(m.get("liquidityNum") or 0) < MIN_LIQUIDITY:
                    dropped["thin"] += 1
                    continue
                out.append({"id": str(m["id"]), "league": tag.upper(), "team_a": teams[0], "team_b": teams[1],
                            "starts": start.isoformat(), "bid": bid, "ask": ask, "price": round((bid + ask) / 2, 4),
                            "liquidity": float(m.get("liquidityNum") or 0), "question": m["question"],
                            "description": (m.get("description") or "").strip()[:1500], "event": str(ev.get("id"))})
    return sorted(out, key=lambda g: g["starts"]), dropped


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=30)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    now = dt.datetime.now(dt.timezone.utc)
    gs, dropped = games(args.hours, now)
    print(f"{len(gs)} games starting in the next {args.hours:g} h (dropped: {dict(dropped)})")
    for g in gs:
        fav = g["team_a"] if g["price"] >= 0.5 else g["team_b"]
        print(f"  {g['starts'][:16]} {g['league']:4} {g['team_a']:>24} {g['price']:.3f} | {1 - g['price']:.3f} {g['team_b']:<24}"
              f" favourite: {fav} ({max(g['price'], 1 - g['price']):.0%})  liq ${g['liquidity']:,.0f}")
    if args.dry_run:
        return
    stamp = now.strftime("%Y%m%d-%H%M%S")
    out = ROOT / "runs" / f"games-{stamp}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"stamp": stamp, "fetched_at": now.isoformat(), "source": API, "hours": args.hours,
                               "filters": {"min_lead_min": 20, "max_spread": MAX_SPREAD, "min_liquidity": MIN_LIQUIDITY},
                               "games": gs}, indent=1))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
