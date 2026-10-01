"""Experiment 3: Jev vs the crowd on pop-culture markets, given only the question and its choices.

Freeze: Polymarket culture events (creators, music, film, reality TV, podcasts, gaming) that close 20 minutes to 8 days
after now. The crowd's probability per option is the bid-ask midpoint, or the last trade when the quote is missing or
wider than 0.10. Two shapes, as Polymarket builds them:
  exclusive    one winner among brackets (negRisk, 3+ options): Jev answers one choice question over the options
  independent  separate yes/no items (each word that may be said, each threshold rung): Jev answers one noul per item
Jev's state is the event's title only. No description, dates, rules or prices.

    .venv/bin/python culture.py freeze [--dry-run]     # runs/culture-<stamp>.json
    .venv/bin/python culture.py ask                    # Jev x3 on the latest freeze -> runs/jev-culture-<stamp>-run<k>.json
    .venv/bin/python culture.py resolve                # outcomes for every freeze -> runs/culture-<stamp>-resolved.json
    .venv/bin/python culture.py compare                # head-to-head table, plus scores once resolved
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import re
import statistics
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
EVENTS = "https://gamma-api.polymarket.com/events?tag_slug={tag}&active=true&closed=false&limit=100"
MARKET = "https://gamma-api.polymarket.com/markets/{id}"
TAGS = ("celebrities", "celebrity", "music", "spotify", "youtube", "mrbeast", "movies", "box-office", "rotten-tomatoes",
        "reality-tv", "tv", "podcast", "netflix", "gaming", "twitch", "taylor-swift", "album")
MIN_LEAD, MAX_DAYS, MAX_WIDE = dt.timedelta(minutes=20), 8, 0.10
RUNS = 3
PLACEHOLDER = re.compile(r"^(Song|Album|Artist|Movie|Option) ([A-Z]|\d{1,2})$")   # unfilled slots Polymarket pads lists with


def scorable(option: str) -> bool:
    return not PLACEHOLDER.match(option)


def get(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "crowd-calibration/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def crowd_p(m: dict[str, Any]) -> float | None:
    b, a = m.get("bestBid"), m.get("bestAsk")
    if b is not None and a is not None and float(a) - float(b) <= MAX_WIDE:
        return (float(a) + float(b)) / 2
    lt = m.get("lastTradePrice")
    return float(lt) if lt not in (None, "") else None


def frozen_before() -> set[str]:
    ids: set[str] = set()
    for p in (ROOT / "runs").glob("culture-2*.json"):
        if not p.stem.endswith("resolved"):
            ids |= {e["id"] for e in json.loads(p.read_text())["events"]}
    return ids


def freeze(dry_run: bool) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    earlier, seen, events = frozen_before(), set(), []
    for tag in TAGS:
        for e in get(EVENTS.format(tag=tag)):
            if e["id"] in seen:
                continue
            seen.add(e["id"])
            try:
                end = dt.datetime.fromisoformat(e["endDate"].replace("Z", "+00:00"))
            except (KeyError, ValueError):
                continue
            if not now + MIN_LEAD <= end <= now + dt.timedelta(days=MAX_DAYS) or e["id"] in earlier:
                continue
            opts = []
            for m in e.get("markets", []):
                if m.get("closed"):
                    continue
                p = crowd_p(m)
                if p is not None:
                    opts.append({"market_id": str(m["id"]), "option": (m.get("groupItemTitle") or m["question"]).strip(),
                                 "crowd": round(p, 4)})
            if not opts:
                continue
            shape = "exclusive" if e.get("negRisk") and len(opts) > 2 else "independent"
            events.append({"id": str(e["id"]), "title": e["title"].strip(), "tag": tag, "closes": e["endDate"],
                           "shape": shape, "options": opts})
    print(f"{len(events)} culture events closing 20 min to {MAX_DAYS} days out "
          f"({sum(e['shape'] == 'exclusive' for e in events)} exclusive, {sum(e['shape'] == 'independent' for e in events)} independent, "
          f"{sum(len(e['options']) for e in events)} options)")
    for e in events:
        print(f"  {e['closes'][:10]} {e['shape']:11} {len(e['options']):2} options  {e['title'][:80]}")
    if dry_run:
        return
    stamp = now.strftime("%Y%m%d-%H%M%S")
    out = ROOT / "runs" / f"culture-{stamp}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"stamp": stamp, "fetched_at": now.isoformat(), "events": events}, indent=1))
    print(f"wrote {out}")


def jev_request(e: dict[str, Any]) -> tuple[dict[str, str], dict[str, Any]]:
    state = {"question": e["title"]}
    if e["shape"] == "exclusive":
        qs = {"pick": {"type": "choice", "instructions": e["title"],
                       "criteria": {f"o{i}": {"what": o["option"]} for i, o in enumerate(e["options"])}}}
    else:
        qs = {f"o{i}": {"type": "noul", "instructions": f"{e['title']} — {o['option']}",
                        "criteria": {"true": f"Yes: {o['option']}", "false": f"No: not {o['option']}"}}
              for i, o in enumerate(e["options"])}
    return state, qs


def ask_one(e: dict[str, Any]) -> dict[str, float]:
    import jev
    state, qs = jev_request(e)
    a = jev.ask(state, qs)["answers"]
    if e["shape"] == "exclusive":
        probs = a["pick"]["probabilities"]
        return {o["market_id"]: float(probs.get(f"o{i}", 0.0)) for i, o in enumerate(e["options"])}
    return {o["market_id"]: float(a[f"o{i}"]["noul"]) for i, o in enumerate(e["options"])}


def latest() -> Path:
    return sorted(p for p in (ROOT / "runs").glob("culture-2*.json") if not p.stem.endswith("resolved"))[-1]


def ask() -> None:
    snap = json.loads(latest().read_text())
    for k in range(1, RUNS + 1):
        t0 = time.time()
        with ThreadPoolExecutor(2) as pool:
            answers = list(pool.map(ask_one, snap["events"]))
        out = ROOT / "runs" / f"jev-culture-{snap['stamp']}-run{k}.json"
        out.write_text(json.dumps({"run": k, "answers": {e["id"]: a for e, a in zip(snap["events"], answers)}}, indent=1))
        print(f"jev run{k}: {len(answers)} events in {time.time() - t0:.0f}s -> {out.name}", flush=True)


def resolve() -> None:
    for snap_path in sorted(p for p in (ROOT / "runs").glob("culture-2*.json") if not p.stem.endswith("resolved")):
        snap = json.loads(snap_path.read_text())
        out = snap_path.with_name(snap_path.stem + "-resolved.json")
        done = json.loads(out.read_text())["results"] if out.exists() else {}
        for e in snap["events"]:
            for o in e["options"]:
                if o["market_id"] in done:
                    continue
                m = get(MARKET.format(id=o["market_id"]))
                prices = [float(x) for x in json.loads(m.get("outcomePrices") or "[]")]
                if m.get("closed") and len(prices) == 2 and sorted(prices) == [0.0, 1.0]:
                    done[o["market_id"]] = int(prices[0] == 1.0)       # 1 = this option resolved Yes
        out.write_text(json.dumps({"snapshot": snap_path.name, "results": done}, indent=1))
        n = sum(len(e["options"]) for e in snap["events"])
        print(f"{snap_path.name}: {len(done)} of {n} options resolved")


def compare() -> None:
    rows = []
    for snap_path in sorted(p for p in (ROOT / "runs").glob("culture-2*.json") if not p.stem.endswith("resolved")):
        snap = json.loads(snap_path.read_text())
        runs = [json.loads(Path(f).read_text())["answers"] for f in sorted(glob.glob(str(ROOT / "runs" / f"jev-culture-{snap['stamp']}-run*.json")))]
        if not runs:
            continue
        res_path = snap_path.with_name(snap_path.stem + "-resolved.json")
        res = json.loads(res_path.read_text())["results"] if res_path.exists() else {}
        for e in snap["events"]:
            jev = {o["market_id"]: statistics.mean(r[e["id"]][o["market_id"]] for r in runs) for o in e["options"]}
            print(f"\n[{e['closes'][:10]}] {e['title'][:85]}  ({e['shape']})")
            if e["shape"] == "exclusive":
                s = sum(o["crowd"] for o in e["options"]) or 1.0
                crowd = {o["market_id"]: o["crowd"] / s for o in e["options"]}
                cp = max(e["options"], key=lambda o: crowd[o["market_id"]])
                jp = max(e["options"], key=lambda o: jev[o["market_id"]])
                win = next((o["option"] for o in e["options"] if res.get(o["market_id"]) == 1), None)
                print(f"   crowd pick: {cp['option'][:30]} ({crowd[cp['market_id']]:.0%})   Jev pick: {jp['option'][:30]} "
                      f"({jev[jp['market_id']]:.0%})   {'agree' if cp is jp else 'DISAGREE'}" + (f"   -> {win}" if win else ""))
            else:
                crowd = {o["market_id"]: o["crowd"] for o in e["options"]}
            for o in sorted((o for o in e["options"] if scorable(o["option"])), key=lambda o: -crowd[o["market_id"]])[:12]:
                mid = o["market_id"]
                out = res.get(mid)
                flag = "" if (crowd[mid] >= 0.5) == (jev[mid] >= 0.5) else "  <- split"
                print(f"     {o['option'][:34]:34} crowd {crowd[mid]:4.0%}  Jev {jev[mid]:4.0%}"
                      + (f"  outcome {'YES' if out else 'no'}" if out is not None else "") + flag)
                if scorable(o["option"]):
                    rows.append((crowd[mid], jev[mid], out))
    scored = [(c, j, y) for c, j, y in rows if y is not None]
    agree = sum((c >= 0.5) == (j >= 0.5) for c, j, _ in rows)
    print(f"\n{len(rows)} options: Jev and the crowd on the same side of 50% on {agree}; {len(scored)} resolved")
    if scored:
        bc = statistics.mean((c - y) ** 2 for c, _, y in scored)
        bj = statistics.mean((j - y) ** 2 for _, j, y in scored)
        print(f"Brier per option (lower is better): crowd {bc:.3f}  Jev {bj:.3f}  coin flip 0.250")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("freeze", "ask", "resolve", "compare"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    {"freeze": lambda: freeze(a.dry_run), "ask": ask, "resolve": resolve, "compare": compare}[a.cmd]()
