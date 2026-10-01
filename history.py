"""Experiment 4 (the seams study): resolved Polymarket markets, with the crowd's price before resolution.

Sample: binary Yes/No markets that resolved cleanly (one outcome priced 1), grouped by the quarter in which they closed,
from 2023 Q1 to Jev's release (2026-09-15), plus every quarter after it ("post-release", outcomes Jev cannot have seen).
Per window, the highest-volume markets with volume >= MIN_VOLUME, a description, a life of at least LIFE_DAYS, and a
traded price HORIZON_DAYS before closing; at most 3 per event and 3 per question template (markets.template).
Crowd price = the Yes token's last daily price at or before closedTime - HORIZON_DAYS (public CLOB price history).
Frozen to runs/history-<stamp>.json. Jev later sees only the question, rules, close date and the horizon date.

    .venv/bin/python history.py --dry-run
    .venv/bin/python history.py
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from markets import template

ROOT = Path(__file__).parent
GAMMA = "https://gamma-api.polymarket.com/markets"
CLOB = "https://clob.polymarket.com/prices-history?market={token}&interval=max&fidelity=1440"
RELEASE = dt.datetime(2026, 9, 15, tzinfo=dt.timezone.utc)
PER_WINDOW, MIN_VOLUME, LIFE_DAYS, HORIZON_DAYS = 100, 50_000, 14, 7
MAX_PER_EVENT = MAX_PER_TEMPLATE = 3
PAGES = 10
FETCH = 160


def get(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "crowd-calibration/0.1"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as exc:
            if exc.code == 422:
                return []
            if attempt == 3:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == 3:
                raise
        time.sleep(2 ** attempt)


def windows(now: dt.datetime) -> list[tuple[str, dt.datetime, dt.datetime]]:
    out, y, q = [], 2023, 1
    while True:
        start = dt.datetime(y, 3 * q - 2, 1, tzinfo=dt.timezone.utc)
        end = dt.datetime(y + (q == 4), (3 * q) % 12 + 1, 1, tzinfo=dt.timezone.utc)
        if start >= now:
            break
        label = f"{y}Q{q}"
        if start < RELEASE < end:          # split the release quarter at the release date
            out.append((label + "-pre", start, RELEASE))
            out.append(("post-release", RELEASE, min(end, now)))
        elif start >= RELEASE:
            out.append(("post-release", start, min(end, now)))
        else:
            out.append((label, start, end))
        y, q = (y + 1, 1) if q == 4 else (y, q + 1)
    return out


def parse(ts: str | None) -> dt.datetime | None:
    if not ts:
        return None
    try:
        return dt.datetime.fromisoformat(ts.replace("Z", "+00:00").replace(" ", "T").replace("+00", "+00:00")
                                         if "+00:00" not in ts else ts.replace(" ", "T"))
    except ValueError:
        return None


def horizon_price(token: str, at: dt.datetime) -> float | None:
    hist = (get(CLOB.format(token=token)) or {}).get("history", [])
    before = [h for h in hist if h["t"] <= at.timestamp()]
    return float(before[-1]["p"]) if before else None


def candidates(start: dt.datetime, end: dt.datetime) -> list[dict[str, Any]]:
    out = []
    for page in range(PAGES):
        batch = get(f"{GAMMA}?closed=true&limit=100&offset={page * 100}&order=volumeNum&ascending=false"
                    f"&end_date_min={(start - dt.timedelta(days=60)).strftime('%Y-%m-%dT%H:%M:%SZ')}"
                    f"&end_date_max={(end + dt.timedelta(days=60)).strftime('%Y-%m-%dT%H:%M:%SZ')}")
        if not batch:
            break
        for m in batch:
            closed = parse(m.get("closedTime")) or parse(m.get("endDate"))
            created = parse(m.get("startDate") or m.get("createdAt"))
            try:
                prices = [float(x) for x in json.loads(m.get("outcomePrices") or "[]")]
                outcomes = json.loads(m.get("outcomes") or "[]")
                tokens = json.loads(m.get("clobTokenIds") or "[]")
            except (TypeError, ValueError):
                continue
            if (outcomes != ["Yes", "No"] or sorted(prices) != [0.0, 1.0] or len(tokens) != 2 or closed is None
                    or created is None or not start <= closed < end or (closed - created).days < LIFE_DAYS
                    or float(m.get("volumeNum") or 0) < MIN_VOLUME or not (m.get("description") or "").strip()):
                continue
            events = m.get("events") or [{}]
            out.append({"id": str(m["id"]), "question": m["question"].strip(),
                        "description": m["description"].strip()[:1500], "closes": m.get("endDate") or closed.isoformat(),
                        "closed_at": closed.isoformat(), "horizon_at": (closed - dt.timedelta(days=HORIZON_DAYS)).isoformat(),
                        "yes_won": prices[0] == 1.0, "volume": float(m.get("volumeNum") or 0), "token_yes": tokens[0],
                        "event": str(events[0].get("id", m["id"])), "template": template(m["question"])})
        if len(batch) < 100:
            break
    return sorted(out, key=lambda c: -c["volume"])


def pick_window(label: str, start: dt.datetime, end: dt.datetime) -> list[dict[str, Any]]:
    """Caps first (per event, per template), then price histories in parallel for the first FETCH eligible markets;
    keep the first PER_WINDOW, in volume order, that have a price HORIZON_DAYS before closing. Cached per window."""
    cache = ROOT / "runs" / "history-cache" / f"{label}-{start.date()}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    per_event, per_tmpl, eligible = Counter(), Counter(), []
    for c in candidates(start, end):
        if per_event[c["event"]] >= MAX_PER_EVENT or per_tmpl[c["template"]] >= MAX_PER_TEMPLATE:
            continue
        per_event[c["event"]] += 1
        per_tmpl[c["template"]] += 1
        eligible.append(c)
        if len(eligible) == FETCH:
            break
    with ThreadPoolExecutor(8) as pool:
        prices = list(pool.map(lambda c: horizon_price(c["token_yes"], dt.datetime.fromisoformat(c["horizon_at"])), eligible))
    picked = [{**c, "window": label, "price": round(p, 4)} for c, p in zip(eligible, prices) if p is not None][:PER_WINDOW]
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(picked))
    return picked


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-windows", type=int, help="stop after this many uncached windows (to fit a time limit)")
    args = ap.parse_args()
    now = dt.datetime.now(dt.timezone.utc)
    chosen: list[dict[str, Any]] = []
    fresh = 0
    for label, start, end in windows(now):
        if (end - start).days < 1:
            continue
        cached = (ROOT / "runs" / "history-cache" / f"{label}-{start.date()}.json").exists()
        if not cached and args.max_windows is not None and fresh >= args.max_windows:
            print(f"{label:16} not yet sampled (--max-windows)")
            continue
        t0 = time.time()
        picked = pick_window(label, start, end)
        fresh += not cached
        chosen += picked
        yes = sum(c["yes_won"] for c in picked)
        mean = sum(c["price"] for c in picked) / len(picked) if picked else float("nan")
        print(f"{label:16} {len(picked):3} markets, {yes:3} resolved Yes, mean price 7d out {mean:.2f}"
              f"{'' if cached else f'  ({time.time() - t0:.0f}s)'}", flush=True)
    print(f"total {len(chosen)}")
    if args.dry_run:
        for c in chosen[:: max(1, len(chosen) // 12)]:
            print(f"  {c['window']:14} price {c['price']:.2f} -> {'YES' if c['yes_won'] else 'no '}  {c['question'][:80]}")
        return
    stamp = now.strftime("%Y%m%d-%H%M%S")
    out = ROOT / "runs" / f"history-{stamp}.json"
    out.write_text(json.dumps({"stamp": stamp, "fetched_at": now.isoformat(), "release": RELEASE.isoformat(),
                               "params": {"per_window": PER_WINDOW, "min_volume": MIN_VOLUME, "life_days": LIFE_DAYS,
                                          "horizon_days": HORIZON_DAYS}, "markets": chosen}, indent=1))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
