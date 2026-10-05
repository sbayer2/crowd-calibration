"""Collect every Atlanta Braves moneyline game Polymarket priced this season, with the pre-game market probability and
the result. Reuses braves.py's search and pricing. Output: runs/braves-season.json (gitignored).

    .venv/bin/python braves_season.py --days 200
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import braves

ROOT = Path(__file__).parent


def outcome(market_id: str) -> bool | None:
    req = urllib.request.Request(braves.MARKET.format(id=market_id), headers={"User-Agent": "crowd-calibration/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        m = json.load(r)
    teams, prices = json.loads(m["outcomes"]), [float(x) for x in json.loads(m["outcomePrices"])]
    return prices[teams.index(braves.TEAM)] == 1.0 if sorted(prices) == [0.0, 1.0] else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=200)
    braves.DAYS = ap.parse_args().days
    now = dt.datetime.now(dt.timezone.utc)
    ids = braves.find_games(now)
    with ThreadPoolExecutor(6) as pool:
        games = [g for g in pool.map(lambda i: braves.game(i, now), ids) if g]
        wins = list(pool.map(lambda g: outcome(g["id"]), games))
    rows = sorted(({**g, "braves_won": w} for g, w in zip(games, wins) if w is not None), key=lambda g: g["start"])
    out = ROOT / "runs" / "braves-season.json"
    out.write_text(json.dumps({"fetched_at": now.isoformat(), "rows": rows}, indent=1))
    print(f"{len(ids)} Braves moneylines; {len(rows)} played, priced and resolved; {rows[0]['start'][:10]} to {rows[-1]['start'][:10]}")


if __name__ == "__main__":
    main()
