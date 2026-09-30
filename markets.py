"""Select and freeze Polymarket markets from the public Gamma API (no account, read-only).

Filters: binary Yes/No, closes at least MIN_DAYS after the snapshot, liquidity >= MIN_LIQUIDITY, bid-ask spread
<= MAX_SPREAD, both quotes present. Price = bid-ask midpoint. Strata: 30 contested (0.15-0.85) plus 30 across the tails
(<0.05, 0.05-0.15, 0.85-0.95, >0.95), at most MAX_PER_EVENT markets from one event and MAX_PER_TEMPLATE
from one question template, highest liquidity first.
The snapshot is frozen to runs/snapshot-<stamp>.json; models only ever see its text, and prices come only from it.

    .venv/bin/python markets.py --dry-run     # print the selection
    .venv/bin/python markets.py               # write the snapshot
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
API = "https://gamma-api.polymarket.com/markets"
PAGE, MAX_PAGES = 100, 60
MIN_DAYS, MIN_LIQUIDITY, MAX_SPREAD, MAX_PER_EVENT, MAX_PER_TEMPLATE = 7, 10_000, 0.03, 3, 3
CONTESTED = (0.15, 0.85)
N_CONTESTED = 30
TAILS = {"<0.05": (0.0, 0.05), "0.05-0.15": (0.05, 0.15), "0.85-0.95": (0.85, 0.95), ">0.95": (0.95, 1.0)}
N_TAILS = 30
DESCRIPTION_CHARS = 1500


def fetch_all() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for page in range(MAX_PAGES):
        url = (f"{API}?active=true&closed=false&limit={PAGE}&offset={page * PAGE}"
               "&order=liquidityNum&ascending=false")
        req = urllib.request.Request(url, headers={"User-Agent": "crowd-calibration/0.1"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                batch = json.load(r)
        except urllib.error.HTTPError as exc:
            if exc.code == 422:          # the API refuses offsets past its paging cap (seen between 2,000 and 5,000)
                break
            raise
        out += batch
        if len(batch) < PAGE:
            break
        time.sleep(0.2)
    return out


def usable(m: dict[str, Any], now: dt.datetime) -> dict[str, Any] | None:
    try:
        if json.loads(m.get("outcomes") or "[]") != ["Yes", "No"]:
            return None
        end = dt.datetime.fromisoformat(m["endDate"].replace("Z", "+00:00"))
        bid, ask = float(m["bestBid"]), float(m["bestAsk"])
    except (KeyError, TypeError, ValueError):
        return None
    if end < now + dt.timedelta(days=MIN_DAYS) or float(m.get("liquidityNum") or 0) < MIN_LIQUIDITY:
        return None
    if not 0 <= ask - bid <= MAX_SPREAD:
        return None
    events = m.get("events") or [{}]
    return {"id": str(m["id"]), "question": m["question"].strip(),
            "description": (m.get("description") or "").strip()[:DESCRIPTION_CHARS],
            "closes": m["endDate"], "bid": bid, "ask": ask, "price": round((bid + ask) / 2, 4),
            "volume": float(m.get("volumeNum") or 0), "liquidity": float(m.get("liquidityNum") or 0),
            "event": str(events[0].get("id", m["id"])), "event_title": events[0].get("title", ""),
            "neg_risk": bool(m.get("negRisk"))}


def template(question: str) -> str:
    """The question with names and numbers removed, so near-identical markets ("Will <State> enact a data center
    moratorium by <date>?") share a key. Capping each template keeps one cluster from standing in for many questions."""
    words = [w for w in re.findall(r"[A-Za-z'’.-]+", question) if not w[0].isupper()]
    return " ".join(w.lower() for w in words)


def select(cands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cands = sorted(cands, key=lambda c: -c["liquidity"])
    per_event: Counter = Counter()
    per_template: Counter = Counter()
    chosen: list[dict[str, Any]] = []

    def take(pool: list[dict[str, Any]], n: int, stratum: str) -> None:
        for c in pool:
            if n == 0:
                return
            key = template(c["question"])
            if (per_event[c["event"]] >= MAX_PER_EVENT or per_template[key] >= MAX_PER_TEMPLATE
                    or any(c["id"] == x["id"] for x in chosen)):
                continue
            per_event[c["event"]] += 1
            per_template[key] += 1
            chosen.append({**c, "stratum": stratum, "template": key})
            n -= 1

    take([c for c in cands if CONTESTED[0] <= c["price"] <= CONTESTED[1]], N_CONTESTED, "contested")
    by_tail = defaultdict(list)
    for c in cands:
        for name, (lo, hi) in TAILS.items():
            if lo <= c["price"] < hi or (name == ">0.95" and c["price"] >= hi):
                by_tail[name].append(c)
    # spread the 30 across the tail bins; a short bin gives its places to the others
    quota = {name: N_TAILS // len(TAILS) + (i < N_TAILS % len(TAILS)) for i, name in enumerate(TAILS)}
    spare = 0
    for name in TAILS:
        before = len(chosen)
        take(by_tail[name], quota[name], name)
        spare += quota[name] - (len(chosen) - before)
    for name in TAILS:
        if spare:
            before = len(chosen)
            take(by_tail[name], spare, name)
            spare -= len(chosen) - before
    return chosen


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    now = dt.datetime.now(dt.timezone.utc)
    raw = fetch_all()
    cands = [c for c in (usable(m, now) for m in raw) if c]
    chosen = select(cands)
    print(f"fetched {len(raw)} active markets, {len(cands)} pass the filters, {len(chosen)} selected")
    print("strata:", dict(Counter(c["stratum"] for c in chosen)))
    for c in chosen:
        print(f"  {c['stratum']:10} {c['price']:.3f}  liq ${c['liquidity']:>10,.0f}  {c['question'][:90]}")
    if args.dry_run:
        return
    stamp = now.strftime("%Y%m%d-%H%M%S")
    out = ROOT / "runs" / f"snapshot-{stamp}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"stamp": stamp, "fetched_at": now.isoformat(), "source": API,
                               "filters": {"min_days": MIN_DAYS, "min_liquidity": MIN_LIQUIDITY, "max_spread": MAX_SPREAD,
                                           "max_per_event": MAX_PER_EVENT, "max_per_template": MAX_PER_TEMPLATE},
                               "n_fetched": len(raw), "n_candidates": len(cands), "markets": chosen}, indent=1))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
