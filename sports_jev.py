"""Experiment 8: does the Braves-optimal request (experiment 6, config 182) carry over to other sports?

Config 182 was the best of 220 request configs on the Braves season: win-likelihood bins asked about each team, the
"venue" instruction ("Consider home-field advantage and travel for this matchup."), plain criteria, and the game as a
one-sentence string. Its edge was within luck (O-001). Here it runs blind on resolved moneyline games of four sports,
next to two controls that differ by one thing each:
  c182        bins | venue | plain | string           the Braves optimum
  bins_plain  bins | plain | plain | string           same, without the venue instruction (isolates the wording)
  noul_both   yes/no about each team | plain | object  the plain baseline
Polymarket lists games "away vs. home" (checked: "Cowboys vs. Eagles", 2025 opener in Philadelphia), so the "home"
baseline picks the second-listed team. Jev is never told which team is at home.

Games (runs/matches-<sport>.json, from `tennis.py collect`; price 5 min before start, volume >= $5k):
  mlb  2026-08-22 .. 10-04   nfl  2025-09-05 .. 2026-10-05   nba  2026-01-28 .. 04-12   nhl  2026-01-31 .. 04-15

    .venv/bin/python sports_jev.py run          # resumable; runs/sports-jev/<sport>-<config>.jsonl
    .venv/bin/python sports_jev.py report
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from analyze import spearman
from braves_opt import BINS, block_acc, cv_picks, instr, noul
from tennis_jev import auc

ROOT = Path(__file__).parent
OUT = ROOT / "runs" / "sports-jev"
SPORTS = {"mlb": "MLB", "nfl": "NFL", "nba": "NBA", "nhl": "NHL"}
CONFIGS = ["c182", "bins_plain", "noul_both"]
SEED, WORKERS, BOOT = 7, 8, 2000


def games(sport: str) -> list[dict[str, Any]]:
    return json.loads((ROOT / "runs" / f"matches-{sport}.json").read_text())["rows"]


def request(cfg: str, league: str, g: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    a, b = g["a"], g["b"]
    if cfg == "noul_both":
        st = {"league": league, "game": f"{a} vs. {b}", "starts": g["start"][:16].replace("T", " ") + " UTC",
              "today": g["start"][:10]}
        return st, {"a": noul(a, b, "plain", "plain"), "b": noul(b, a, "plain", "plain")}
    style = "venue" if cfg == "c182" else "plain"
    levels = [l for l, _ in BINS["plain"]]
    q = lambda t: {"type": "score", "instructions": instr(f"How likely is it that the {t} win this game?", style), "criteria": levels}
    return f"{league} game: {a} vs. {b}, {g['start'][:10]}.", {"a": q(a), "b": q(b)}


def value(cfg: str, ans: dict[str, Any]) -> float:
    """A number that favours the first-listed (away) team."""
    if cfg == "noul_both":
        return (float(ans["a"]["noul"]) + 1 - float(ans["b"]["noul"])) / 2
    mids = [m for _, m in BINS["plain"]]
    ev = lambda x: sum(float(x["probabilities"].get(str(i), x["probabilities"].get(i, 0.0))) * m for i, m in enumerate(mids))
    return ev(ans["a"]) - ev(ans["b"])


def run() -> None:
    import jev
    OUT.mkdir(parents=True, exist_ok=True)
    for sport, league in SPORTS.items():
        gs = games(sport)
        for cfg in CONFIGS:
            path = OUT / f"{sport}-{cfg}.jsonl"
            done = {json.loads(l)["id"] for l in path.open(encoding="utf-8")} if path.exists() else set()
            todo = [g for g in gs if g["id"] not in done]

            def one(g):                                   # one fresh, stateless request per game
                st, qs = request(cfg, league, g)
                ans = jev.ask(st, qs)["answers"]
                return {"id": g["id"], "v": value(cfg, ans), "answers": ans}
            with ThreadPoolExecutor(WORKERS) as pool, path.open("a", encoding="utf-8") as fh:
                for rec in pool.map(one, todo):
                    fh.write(json.dumps(rec) + "\n")
                    fh.flush()
            print(f"{sport} {cfg}: done ({len(todo)} new)", flush=True)


def report() -> None:
    rng = random.Random(SEED)
    pooled = []
    for sport in SPORTS:
        gs = games(sport)
        y, mk = [g["a_won"] for g in gs], [g["p_a"] for g in gs]
        home = statistics.mean(1 - t for t in y)
        print(f"\n{sport.upper()}: {len(gs)} games | market AUC {auc(mk, y):.3f}, picks {statistics.mean((p >= .5) == bool(t) for p, t in zip(mk, y)):.1%}"
              f" | always pick the home (second-listed) team {home:.1%}")
        print(f"  market per block (target): {' '.join(f'{a:.0%}' for a in block_acc([p >= .5 for p in mk], y))}")
        v = {}
        for cfg in CONFIGS:
            d = {(r := json.loads(l))["id"]: r["v"] for l in (OUT / f"{sport}-{cfg}.jsonl").open(encoding="utf-8")}
            if len(d) < len(gs):
                print(f"  {cfg:11} incomplete ({len(d)}/{len(gs)})")
                continue
            v[cfg] = [d[g["id"]] for g in gs]
            picks = cv_picks(v[cfg], y)
            blocks = block_acc(picks, y)
            mkb = block_acc([p >= .5 for p in mk], y)
            mid = 0.5 if cfg == "noul_both" else 0.0
            home_share = statistics.mean(x < mid for x in v[cfg])
            print(f"  {cfg:11} AUC {auc(v[cfg], y):.3f}  rho mkt {spearman(v[cfg], mk):+.2f}  picks (CV) {statistics.mean(p == bool(t) for p, t in zip(picks, y)):.1%}"
                  f"  blocks {' '.join(f'{a:.0%}' for a in blocks)}  margin {min(a - m for a, m in zip(blocks, mkb)):+.1%}"
                  f"  raw lean to home team {home_share:.0%}")
        if "c182" in v and "bins_plain" in v:
            boots = [[rng.randrange(len(gs)) for _ in gs] for _ in range(BOOT)]
            diffs = sorted(auc([v["c182"][i] for i in b], [y[i] for i in b]) - auc([v["bins_plain"][i] for i in b], [y[i] for i in b])
                           for b in boots if 0 < sum(y[i] for i in b) < len(b))
            dd = auc(v["c182"], y) - auc(v["bins_plain"], y)
            pooled.append(dd)
            print(f"  venue wording effect, AUC(c182) - AUC(bins_plain): {dd:+.3f} [{diffs[int(.025 * len(diffs))]:+.3f}, {diffs[int(.975 * len(diffs)) - 1]:+.3f}]")
    if pooled:
        print(f"\nmean venue-wording effect across sports: {statistics.mean(pooled):+.3f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("run", "report"))
    {"run": run, "report": report}[ap.parse_args().cmd]()
