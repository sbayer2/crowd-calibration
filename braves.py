"""Atlanta Braves, last 30 days: Polymarket's pre-game probability of a Braves win vs Jev's blind probability.

Games: every Braves moneyline market (regular season via tag "mlb", postseason via "mlb-playoffs") whose game started
in the last DAYS days and is closed. Market probability = the Braves token's last traded price at or before
PRE_GAME_MIN minutes before first pitch (public CLOB price history). Jev sees only the league, the matchup, the start
time and the date, and answers one yes/no: "Will the Atlanta Braves win this game?" (3 runs, mean). Both sides pick
"win" at P >= 0.5. Outcomes are deliberately not shown: this compares the two forecasters, not their accuracy.

    .venv/bin/python braves.py           # runs/braves-<stamp>.json and artifacts/braves-30d.html
"""

from __future__ import annotations

import datetime as dt
import json
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
TEAM, DAYS, PRE_GAME_MIN, RUNS = "Atlanta Braves", 30, 5, 3
JEV_T = 0.5     # Jev picks Win at >= JEV_T, Loss at <= 1 - JEV_T, otherwise makes no call (--jev-threshold)
EVENTS = "https://gamma-api.polymarket.com/events?tag_slug={tag}&closed=true&limit=100&offset={off}&end_date_min={a}&end_date_max={b}"
MARKET = "https://gamma-api.polymarket.com/markets/{id}"
HIST = "https://clob.polymarket.com/prices-history?market={token}&startTs={a}&endTs={b}&fidelity=5"


def get(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "crowd-calibration/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as exc:
        if exc.code == 422:
            return None
        raise


def ts(s: str) -> dt.datetime:
    s = s.replace(" ", "T")
    return dt.datetime.fromisoformat(s if "+00:00" in s else s.replace("Z", "+00:00").replace("+00", "+00:00"))


def find_games(now: dt.datetime) -> list[str]:
    ids: set[str] = set()
    start = now - dt.timedelta(days=DAYS + 1)
    for closed in ("true", "false"):            # postseason: few events, with later end dates, so read them all
        for off in range(0, 1000, 100):
            evs = get(f"https://gamma-api.polymarket.com/events?tag_slug=mlb-playoffs&closed={closed}&limit=100&offset={off}")
            if not evs:
                break
            for e in evs:
                for m in e.get("markets", []):
                    if m.get("sportsMarketType") == "moneyline" and TEAM in json.loads(m.get("outcomes") or "[]"):
                        ids.add(str(m["id"]))
            if len(evs) < 100:
                break
    for tag in ("mlb",):
        d = start
        while d < now + dt.timedelta(days=12):     # some games carry an end date days after first pitch
            d2 = d + dt.timedelta(days=3)
            for off in range(0, 3000, 100):
                evs = get(EVENTS.format(tag=tag, off=off, a=d.strftime("%Y-%m-%dT%H:%M:%SZ"), b=d2.strftime("%Y-%m-%dT%H:%M:%SZ")))
                if not evs:
                    break
                for e in evs:
                    for m in e.get("markets", []):
                        if m.get("sportsMarketType") == "moneyline" and TEAM in json.loads(m.get("outcomes") or "[]"):
                            ids.add(str(m["id"]))
                if len(evs) < 100:
                    break
            d = d2
    return sorted(ids)


def game(market_id: str, now: dt.datetime) -> dict[str, Any] | None:
    m = get(MARKET.format(id=market_id))
    teams, tokens = json.loads(m["outcomes"]), json.loads(m["clobTokenIds"])
    start = ts(m["gameStartTime"])
    if not (now - dt.timedelta(days=DAYS) <= start <= now) or not m.get("closed"):
        return None
    i = teams.index(TEAM)
    at = start - dt.timedelta(minutes=PRE_GAME_MIN)
    hist = (get(HIST.format(token=tokens[i], a=int((at - dt.timedelta(hours=12)).timestamp()), b=int(at.timestamp()))) or {}).get("history", [])
    if not hist:
        return None
    opp = teams[1 - i]
    return {"id": market_id, "start": start.isoformat(), "matchup": f"{teams[0]} vs. {teams[1]}", "opponent": opp,
            "market_p": float(hist[-1]["p"]), "price_at": dt.datetime.fromtimestamp(hist[-1]["t"], dt.timezone.utc).isoformat()}


def ask_jev(g: dict[str, Any]) -> float:
    import jev
    state = {"league": "MLB", "game": g["matchup"], "starts": g["start"][:16].replace("T", " ") + " UTC", "today": g["start"][:10]}
    q = {"win": {"type": "noul", "instructions": f"Will the {TEAM} win this game?",
                 "criteria": {"true": f"The {TEAM} win the game.", "false": f"The {TEAM} lose; the {g['opponent']} win."}}}
    return float(jev.ask(state, q)["answers"]["win"]["noul"])


def ask_jev_forced(g: dict[str, Any], team: str = TEAM) -> float:
    """Forced call: no neutral option, Jev must choose between two committed 60/40 statements about `team`.
    Returns Jev's probability for the '`team` at least 60% to win' option."""
    import jev
    state = {"league": "MLB", "game": g["matchup"], "starts": g["start"][:16].replace("T", " ") + " UTC", "today": g["start"][:10]}
    q = {"call": {"type": "choice", "instructions": f"Call this game for the {team}. You must pick one side.",
                  "criteria": {"win": {"what": f"The {team} are at least 60% likely to win this game (a clear favourite)."},
                               "lose": {"what": f"The {team} are at least 60% likely to lose this game (a clear underdog)."}}}}
    probs = jev.ask(state, q)["answers"]["call"]["probabilities"]
    return float(probs["win"]) / (float(probs["win"]) + float(probs["lose"]))


def forced(out_html: Path) -> None:
    """Reuse the latest run's games and market prices; ask only the forced 60/40 call."""
    src = sorted((ROOT / "runs").glob("braves-2*.json"))[-1]
    rows = json.loads(src.read_text())["rows"]
    for r in rows:
        r["forced_runs"] = []
    for _ in range(RUNS):
        with ThreadPoolExecutor(3) as pool:
            for r, p in zip(rows, pool.map(ask_jev_forced, rows)):
                r["forced_runs"].append(p)
    for r in rows:
        r["forced_p"] = statistics.mean(r["forced_runs"])
    (ROOT / "runs" / f"{src.stem}-forced.json").write_text(json.dumps({"source": src.name, "rows": rows}, indent=1))
    labels = [f"{r['start'][5:10]} {'vs' if r['matchup'].startswith(TEAM) else '@'} {r['opponent'].split()[-1]}" for r in rows]
    mk = [round(r["market_p"], 3) for r in rows]
    jv = [round(r["jev_p"], 3) for r in rows]
    fc = [round(r["forced_p"], 3) for r in rows]
    same_mk = sum((a >= 0.5) == (f >= 0.5) for a, f in zip(mk, fc))
    same_jv = sum((b >= 0.5) == (f >= 0.5) for b, f in zip(jv, fc))
    strong = [(a, f) for a, f in zip(mk, fc) if a >= 0.6 or a <= 0.4]
    same_strong = sum((a >= 0.5) == (f >= 0.5) for a, f in strong)
    trs = "".join(f"<tr><td>{lb}</td><td>{r['matchup']}</td><td class=n>{a:.0%}</td><td>{'Win' if a >= .5 else 'Loss'}{' *' if a >= .6 or a <= .4 else ''}</td>"
                  f"<td class=n>{b:.0%}</td><td class=n>{f:.0%}</td><td>{'Win' if f >= .5 else 'Loss'}</td>"
                  f"<td class='{'ok' if (a >= .5) == (f >= .5) else 'no'}'>{'agree' if (a >= .5) == (f >= .5) else 'differ'}</td></tr>"
                  for lb, r, a, b, f in zip(labels, rows, mk, jv, fc))
    out_html.write_text(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Braves: Jev Forced Call</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
<style>
:root{{--bg:#fbfaf8;--ink:#1d1c1a;--muted:#6b675f;--rule:#e2ded7;--card:#fff;--ok:#3c6e50;--no:#a8321a}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 -apple-system,"Segoe UI",system-ui,sans-serif}}
main{{max-width:980px;margin:0 auto;padding:40px 16px 64px}} h1{{font-size:1.5rem;margin:0 0 4px}} .sub{{color:var(--muted);margin:0 0 24px}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:0 0 24px}}
.stat{{background:var(--card);border:1px solid var(--rule);border-radius:10px;padding:12px 16px}} .stat b{{display:block;font-size:1.5rem}}
.card{{background:var(--card);border:1px solid var(--rule);border-radius:10px;padding:16px;margin:0 0 20px}}
.wrap{{overflow-x:auto}} table{{border-collapse:collapse;width:100%;font-size:.88rem}} th,td{{padding:6px 8px;border-bottom:1px solid var(--rule);text-align:left}}
th{{color:var(--muted);font-weight:600;font-size:.78rem;text-transform:uppercase}} td.n{{text-align:right;font-variant-numeric:tabular-nums}}
.ok{{color:var(--ok)}} .no{{color:var(--no);font-weight:600}} .note{{color:var(--muted);font-size:.88rem}}
@media print{{body{{background:#fff}} .card,.stat{{border-color:#bbb;break-inside:avoid}}}}
</style></head><body><main>
<h1>Braves: Jev forced to call each game at 60/40</h1>
<p class="sub">Same {len(rows)} games and market prices as the 50% run. Jev chooses between "Braves at least 60% to win" and
"Braves at least 60% to lose", with no neutral option ({RUNS} runs, mean). Its call is the side it prefers; the percentage is how
strongly it prefers the Win statement. Outcomes are not shown.</p>
<div class="stats">
<div class="stat"><b>{same_mk} / {len(rows)}</b>forced call = market pick</div>
<div class="stat"><b>{same_strong} / {len(strong)}</b>agree where the market itself is 60/40+</div>
<div class="stat"><b>{same_jv} / {len(rows)}</b>forced call = Jev's own 50% pick</div>
<div class="stat"><b>{min(fc):.0%} – {max(fc):.0%}</b>range of Jev's preference for Win</div>
</div>
<div class="card"><canvas id="c" height="140"></canvas></div>
<div class="card wrap"><table><tr><th>Game</th><th>Matchup</th><th>Market P(win)</th><th>Market pick</th><th>Jev P(win), plain</th><th>Jev forced: prefers Win</th><th>Jev forced call</th><th></th></tr>{trs}</table>
<p class="note">* the market itself is at 60% or more, or 40% or less.</p></div>
</main><script>
new Chart(document.getElementById('c'),{{type:'line',data:{{labels:{json.dumps(labels)},datasets:[
{{label:'Polymarket P(Braves win)',data:{json.dumps(mk)},borderColor:'#13274f',backgroundColor:'#13274f',tension:.2,pointRadius:4}},
{{label:'Jev forced: preference for "Braves 60%+ to win"',data:{json.dumps(fc)},borderColor:'#ce1141',backgroundColor:'#ce1141',tension:.2,pointRadius:4}},
{{label:'Jev plain P(win)',data:{json.dumps(jv)},borderColor:'#e8a0b0',backgroundColor:'#e8a0b0',borderDash:[4,3],tension:.2,pointRadius:2}},
{{label:'50%',data:{json.dumps([0.5] * len(rows))},borderColor:'#9a948a',borderDash:[6,4],pointRadius:0,borderWidth:1}}]}},
options:{{responsive:true,interaction:{{mode:'index',intersect:false}},scales:{{y:{{min:0,max:1,ticks:{{callback:v=>Math.round(v*100)+'%'}}}},x:{{ticks:{{maxRotation:60,minRotation:45}}}}}},
plugins:{{tooltip:{{callbacks:{{label:c=>c.dataset.label+': '+Math.round(c.parsed.y*100)+'%'}}}}}}}}}});
</script></body></html>""")
    print(f"forced call = market pick {same_mk}/{len(rows)}; where market is 60/40+: {same_strong}/{len(strong)}; = Jev's 50% pick {same_jv}/{len(rows)};"
          f" preference range {min(fc):.2f}-{max(fc):.2f}")
    for lb, r, a, f in zip(labels, rows, mk, fc):
        print(f"  {lb:14} market {a:.2f}  plain {r['jev_p']:.2f}  forced {f:.2f} -> {'Win' if f >= .5 else 'Loss'}")


def forced_opponent(out_html: Path) -> None:
    """The same forced call, phrased about the opponent. Reuses the latest Braves-framed forced run.
    P(Braves) from this framing = 1 - preference for '<opponent> at least 60% to win'."""
    src = sorted((ROOT / "runs").glob("braves-2*-forced.json"))[-1]
    rows = json.loads(src.read_text())["rows"]
    for r in rows:
        r["opp_runs"] = []
    for _ in range(RUNS):
        with ThreadPoolExecutor(3) as pool:
            for r, p in zip(rows, pool.map(lambda g: ask_jev_forced(g, g["opponent"]), rows)):
                r["opp_runs"].append(p)
    for r in rows:
        r["opp_pref"] = statistics.mean(r["opp_runs"])
        r["opp_braves_p"] = 1 - r["opp_pref"]
        r["both_p"] = (r["forced_p"] + r["opp_braves_p"]) / 2
    (ROOT / "runs" / f"{src.stem}-opponent.json").write_text(json.dumps({"source": src.name, "rows": rows}, indent=1))
    labels = [f"{r['start'][5:10]} {r['opponent'].split()[-1]}" for r in rows]
    mk = [round(r["market_p"], 3) for r in rows]
    bf = [round(r["forced_p"], 3) for r in rows]
    of = [round(r["opp_braves_p"], 3) for r in rows]
    av = [round(r["both_p"], 3) for r in rows]
    named = sum(r["opp_pref"] >= 0.5 for r in rows)
    flips = sum((b >= .5) != (o >= .5) for b, o in zip(bf, of))
    agree = lambda xs: sum((a >= .5) == (x >= .5) for a, x in zip(mk, xs))
    corr = lambda xs: statistics.correlation(mk, xs)
    trs = "".join(f"<tr><td>{lb}</td><td>{r['matchup']}</td><td class=n>{a:.0%}</td><td class=n>{b:.0%}</td>"
                  f"<td class=n>{r['opp_pref']:.0%}</td><td class=n>{o:.0%}</td><td class=n>{v:.0%}</td>"
                  f"<td class='{'no' if (b >= .5) != (o >= .5) else 'ok'}'>{'flips' if (b >= .5) != (o >= .5) else 'same'}</td></tr>"
                  for lb, r, a, b, o, v in zip(labels, rows, mk, bf, of, av))
    out_html.write_text(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Braves: Framing Test</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
<style>
:root{{--bg:#fbfaf8;--ink:#1d1c1a;--muted:#6b675f;--rule:#e2ded7;--card:#fff;--ok:#3c6e50;--no:#a8321a}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 -apple-system,"Segoe UI",system-ui,sans-serif}}
main{{max-width:980px;margin:0 auto;padding:40px 16px 64px}} h1{{font-size:1.5rem;margin:0 0 4px}} .sub{{color:var(--muted);margin:0 0 24px}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:0 0 24px}}
.stat{{background:var(--card);border:1px solid var(--rule);border-radius:10px;padding:12px 16px}} .stat b{{display:block;font-size:1.5rem}}
.card{{background:var(--card);border:1px solid var(--rule);border-radius:10px;padding:16px;margin:0 0 20px}}
.wrap{{overflow-x:auto}} table{{border-collapse:collapse;width:100%;font-size:.88rem}} th,td{{padding:6px 8px;border-bottom:1px solid var(--rule);text-align:left}}
th{{color:var(--muted);font-weight:600;font-size:.78rem;text-transform:uppercase}} td.n{{text-align:right;font-variant-numeric:tabular-nums}}
.ok{{color:var(--ok)}} .no{{color:var(--no);font-weight:600}}
@media print{{body{{background:#fff}} .card,.stat{{border-color:#bbb;break-inside:avoid}}}}
</style></head><body><main>
<h1>Braves forced call: does the wording decide the pick?</h1>
<p class="sub">Same {len(rows)} games. Jev must call each game at 60/40, once phrased about the Braves and once about the opponent
({RUNS} runs each). All values are expressed as P(Braves win); the opponent framing is converted as 1 &minus; Jev's preference for
"opponent 60%+ to win". Outcomes are not shown.</p>
<div class="stats">
<div class="stat"><b>{named} / {len(rows)}</b>opponent framing: Jev backs the named opponent</div>
<div class="stat"><b>{flips} / {len(rows)}</b>picks that flip with the wording</div>
<div class="stat"><b>{agree(bf)} / {agree(of)} / {agree(av)}</b>same pick as market: Braves-framed / opponent-framed / both averaged</div>
<div class="stat"><b>{corr(bf):+.2f} / {corr(of):+.2f} / {corr(av):+.2f}</b>correlation with market (same order)</div>
</div>
<div class="card"><canvas id="c" height="140"></canvas></div>
<div class="card wrap"><table><tr><th>Game</th><th>Matchup</th><th>Market P(win)</th><th>Braves-framed</th><th>Opp. framed: prefers opp.</th><th>Opp. framed as P(Braves)</th><th>Both averaged</th><th></th></tr>{trs}</table></div>
</main><script>
new Chart(document.getElementById('c'),{{type:'line',data:{{labels:{json.dumps(labels)},datasets:[
{{label:'Polymarket',data:{json.dumps(mk)},borderColor:'#13274f',backgroundColor:'#13274f',tension:.2,pointRadius:4}},
{{label:'Jev forced, Braves named',data:{json.dumps(bf)},borderColor:'#ce1141',backgroundColor:'#ce1141',tension:.2,pointRadius:3}},
{{label:'Jev forced, opponent named',data:{json.dumps(of)},borderColor:'#e07b00',backgroundColor:'#e07b00',tension:.2,pointRadius:3}},
{{label:'Jev, both framings averaged',data:{json.dumps(av)},borderColor:'#7a4fa0',backgroundColor:'#7a4fa0',borderDash:[4,3],tension:.2,pointRadius:2}},
{{label:'50%',data:{json.dumps([0.5] * len(rows))},borderColor:'#9a948a',borderDash:[6,4],pointRadius:0,borderWidth:1}}]}},
options:{{responsive:true,interaction:{{mode:'index',intersect:false}},scales:{{y:{{min:0,max:1,ticks:{{callback:v=>Math.round(v*100)+'%'}}}},x:{{ticks:{{maxRotation:60,minRotation:45}}}}}},
plugins:{{tooltip:{{callbacks:{{label:c=>c.dataset.label+': '+Math.round(c.parsed.y*100)+'%'}}}}}}}}}});
</script></body></html>""")
    print(f"opponent framing backs the named opponent in {named}/{len(rows)}; picks flip with wording {flips}/{len(rows)}")
    print(f"same pick as market: Braves-framed {agree(bf)}, opponent-framed {agree(of)}, averaged {agree(av)} (of {len(rows)})")
    print(f"correlation with market: Braves-framed {corr(bf):+.2f}, opponent-framed {corr(of):+.2f}, averaged {corr(av):+.2f}")
    for lb, r, a, b, o in zip(labels, rows, mk, bf, of):
        print(f"  {lb:14} market {a:.2f}  Braves-named {b:.2f}  opponent-named -> P(Braves) {o:.2f}  (prefers {r['opponent'].split()[-1]} {r['opp_pref']:.2f})")


def jev_pick(p: float) -> str:
    return "Win" if p >= JEV_T else "Loss" if p <= 1 - JEV_T else "No call"


def chart(rows: list[dict[str, Any]], out: Path) -> None:
    labels = [f"{r['start'][5:10]} {'vs' if r['matchup'].startswith(TEAM) else '@'} {r['opponent'].split()[-1]}" for r in rows]
    mk, jv = [round(r["market_p"], 3) for r in rows], [round(r["jev_p"], 3) for r in rows]
    calls = [(a, b) for a, b in zip(mk, jv) if jev_pick(b) != "No call"]
    agree = sum((a >= 0.5) == (jev_pick(b) == "Win") for a, b in calls)
    corr = statistics.correlation(mk, jv) if len(rows) > 2 else float("nan")
    def verdict(a: float, b: float) -> str:
        pick = jev_pick(b)
        if pick == "No call":
            return "<td class=nc>no call</td>"
        same = (a >= 0.5) == (pick == "Win")
        return f"<td class='{'ok' if same else 'no'}'>{'agree' if same else 'differ'}</td>"
    trs = "".join(f"<tr><td>{lb}</td><td>{r['matchup']}</td><td class=n>{a:.0%}</td><td>{'Win' if a >= 0.5 else 'Loss'}</td>"
                  f"<td class=n>{b:.0%}</td><td>{jev_pick(b)}</td>{verdict(a, b)}</tr>"
                  for lb, r, a, b in zip(labels, rows, mk, jv))
    out.write_text(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Braves: Market vs Jev</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
<style>
:root{{--bg:#fbfaf8;--ink:#1d1c1a;--muted:#6b675f;--rule:#e2ded7;--card:#fff;--mk:#13274f;--jv:#ce1141;--ok:#3c6e50;--no:#a8321a}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 -apple-system,"Segoe UI",system-ui,sans-serif}}
main{{max-width:980px;margin:0 auto;padding:40px 16px 64px}} h1{{font-size:1.5rem;margin:0 0 4px}} .sub{{color:var(--muted);margin:0 0 24px}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:0 0 24px}}
.stat{{background:var(--card);border:1px solid var(--rule);border-radius:10px;padding:12px 16px}} .stat b{{display:block;font-size:1.5rem}}
.card{{background:var(--card);border:1px solid var(--rule);border-radius:10px;padding:16px;margin:0 0 20px}}
.wrap{{overflow-x:auto}} table{{border-collapse:collapse;width:100%;font-size:.88rem}} th,td{{padding:6px 8px;border-bottom:1px solid var(--rule);text-align:left}}
th{{color:var(--muted);font-weight:600;font-size:.78rem;text-transform:uppercase}} td.n{{text-align:right;font-variant-numeric:tabular-nums}}
.ok{{color:var(--ok)}} .no{{color:var(--no);font-weight:600}} .nc{{color:var(--muted)}} .note{{color:var(--muted);font-size:.88rem}}
@media print{{body{{background:#fff}} .card,.stat{{border-color:#bbb;break-inside:avoid}}}}
</style></head><body><main>
<h1>Atlanta Braves: Polymarket vs Jev</h1>
<p class="sub">Probability the Braves win, last {DAYS} days ({rows[0]['start'][:10]} to {rows[-1]['start'][:10]}), {len(rows)} games incl. postseason.
Market = last traded price {PRE_GAME_MIN} min before first pitch; picks Win at &ge; 50%. Jev = blind yes/no, mean of {RUNS} runs; picks Win at &ge; {JEV_T:.0%}, Loss at &le; {1 - JEV_T:.0%}, otherwise no call.</p>
<div class="stats">
<div class="stat"><b>{len(calls)} / {len(rows)}</b>games Jev made a call</div>
<div class="stat"><b>{agree} / {len(calls)}</b>same pick, where Jev called</div>
<div class="stat"><b>{statistics.mean(mk):.0%}</b>market mean P(win)</div>
<div class="stat"><b>{statistics.mean(jv):.0%}</b>Jev mean P(win)</div>
<div class="stat"><b>{corr:+.2f}</b>correlation, game by game</div>
</div>
<div class="card"><canvas id="c" height="140"></canvas></div>
<div class="card wrap"><table><tr><th>Game</th><th>Matchup</th><th>Market P(win)</th><th>Market pick</th><th>Jev P(win)</th><th>Jev pick</th><th></th></tr>{trs}</table></div>
<p class="note">Outcomes are intentionally omitted: this compares what each forecaster predicted, not who was right.</p>
</main><script>
new Chart(document.getElementById('c'),{{type:'line',data:{{labels:{json.dumps(labels)},datasets:[
{{label:'Polymarket P(Braves win)',data:{json.dumps(mk)},borderColor:'#13274f',backgroundColor:'#13274f',tension:.2,pointRadius:4}},
{{label:'Jev P(Braves win)',data:{json.dumps(jv)},borderColor:'#ce1141',backgroundColor:'#ce1141',tension:.2,pointRadius:4}},
{{label:'50% (market pick line)',data:{json.dumps([0.5] * len(rows))},borderColor:'#9a948a',borderDash:[6,4],pointRadius:0,borderWidth:1}},
{{label:'Jev Win line ({JEV_T:.0%})',data:{json.dumps([JEV_T] * len(rows))},borderColor:'#ce1141',borderDash:[2,4],pointRadius:0,borderWidth:1}},
{{label:'Jev Loss line ({1 - JEV_T:.0%})',data:{json.dumps([round(1 - JEV_T, 3)] * len(rows))},borderColor:'#ce1141',borderDash:[2,4],pointRadius:0,borderWidth:1}}]}},
options:{{responsive:true,interaction:{{mode:'index',intersect:false}},scales:{{y:{{min:0,max:1,ticks:{{callback:v=>Math.round(v*100)+'%'}}}},x:{{ticks:{{maxRotation:60,minRotation:45}}}}}},
plugins:{{tooltip:{{callbacks:{{label:c=>c.dataset.label+': '+Math.round(c.parsed.y*100)+'%'}}}}}}}}}});
</script></body></html>""")


def main() -> None:
    global JEV_T
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--jev-threshold", type=float, default=0.5)
    ap.add_argument("--forced", action="store_true", help="reuse the latest games; Jev must call each at 60/40")
    ap.add_argument("--forced-opponent", action="store_true", help="the same forced call, phrased about the opponent")
    a = ap.parse_args()
    if a.forced_opponent:
        (ROOT / "artifacts").mkdir(exist_ok=True)
        forced_opponent(ROOT / "artifacts" / "braves-30d-forced60-opponent.html")
        return
    JEV_T = a.jev_threshold
    if a.forced:
        (ROOT / "artifacts").mkdir(exist_ok=True)
        forced(ROOT / "artifacts" / "braves-30d-forced60.html")
        return
    now = dt.datetime.now(dt.timezone.utc)
    ids = find_games(now)
    with ThreadPoolExecutor(6) as pool:
        rows = sorted((g for g in pool.map(lambda i: game(i, now), ids) if g), key=lambda g: g["start"])
    print(f"{len(ids)} Braves moneylines found; {len(rows)} played in the last {DAYS} days with a pre-game price")
    for r in rows:
        r["jev_runs"] = []
    for _ in range(RUNS):
        with ThreadPoolExecutor(3) as pool:
            for r, p in zip(rows, pool.map(ask_jev, rows)):
                r["jev_runs"].append(p)
    for r in rows:
        r["jev_p"] = statistics.mean(r["jev_runs"])
        print(f"  {r['start'][:16]}  {r['matchup']:45} market {r['market_p']:.2f}  Jev {r['jev_p']:.2f}")
    stamp = now.strftime("%Y%m%d-%H%M%S")
    (ROOT / "runs" / f"braves-{stamp}.json").write_text(json.dumps({"stamp": stamp, "rows": rows}, indent=1))
    (ROOT / "artifacts").mkdir(exist_ok=True)
    name = "braves-30d.html" if JEV_T == 0.5 else f"braves-30d-jev{round(JEV_T * 100)}.html"
    chart(rows, ROOT / "artifacts" / name)
    print(f"wrote artifacts/{name}")


if __name__ == "__main__":
    main()
