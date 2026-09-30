"""Record who won each game in a frozen games snapshot, from the same public API (read-only).

A game counts as resolved only when its market is closed and one outcome's price is exactly 1. Anything else
(still open, voided, split) is listed and skipped, never guessed. Output: runs/games-<stamp>-resolved.json.

    .venv/bin/python resolve.py                  # every games snapshot that has no complete resolution yet
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
API = "https://gamma-api.polymarket.com/markets/{id}"


def fetch(market_id: str) -> dict:
    req = urllib.request.Request(API.format(id=market_id), headers={"User-Agent": "crowd-calibration/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def resolve(snapshot: Path) -> None:
    snap = json.loads(snapshot.read_text())
    out_path = snapshot.with_name(snapshot.stem + "-resolved.json")
    done = json.loads(out_path.read_text())["results"] if out_path.exists() else {}
    for g in snap["games"]:
        if g["id"] in done:
            continue
        m = fetch(g["id"])
        prices = [float(x) for x in json.loads(m.get("outcomePrices") or "[]")]
        teams = json.loads(m.get("outcomes") or "[]")
        if m.get("closed") and prices.count(1.0) == 1 and teams == [g["team_a"], g["team_b"]]:
            done[g["id"]] = {"a_won": prices[0] == 1.0, "winner": teams[prices.index(1.0)]}
    out_path.write_text(json.dumps({"snapshot": snapshot.name, "results": done}, indent=1))
    pending = [g for g in snap["games"] if g["id"] not in done]
    print(f"{snapshot.name}: {len(done)} resolved, {len(pending)} pending"
          + (f" ({', '.join(g['team_a'] + '-' + g['team_b'] for g in pending[:6])}{'...' if len(pending) > 6 else ''})" if pending else ""))


if __name__ == "__main__":
    for snap in sorted(p for p in (ROOT / "runs").glob("games-2*.json") if not p.stem.endswith("resolved")):
        resolve(snap)
