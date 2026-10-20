"""analyze_live.py on synthetic data in the collectors' file formats, with known answers. Standard library + numpy:
python -m unittest tests.test_analyze_live

The synthetic world: a team-strength gap s per game; Pinnacle's early line sees s, T-60 adds news1, T-5 adds news2.
Polymarket lags at T-60 (an offset) and sits on Pinnacle at T-5. The result is drawn from Pinnacle's T-5 price. Jev
sees s plus noise and no news. So C1 holds, C2 is null, C3 holds (Polymarket closes the gap), J2 favours the early
line, and J3 holds.
"""
import datetime as dt
import json
import math
import random
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import analyze_live as A  # noqa: E402

NOW = dt.datetime(2026, 12, 10, tzinfo=dt.timezone.utc)
sig = lambda x: 1 / (1 + math.exp(-x))


def odds(p: float, away: str, home: str, vig: float = 0.025) -> dict:
    return {"key": "pinnacle", "markets": [{"key": "h2h", "outcomes": [
        {"name": away, "price": round(1 / (p * (1 + vig)), 3)}, {"name": home, "price": round(1 / ((1 - p) * (1 + vig)), 3)}]}]}


def world(root: Path, sport: str, n: int, start: dt.datetime, rng: random.Random, plant: bool) -> dict[str, str]:
    """Write one sport's files; return {planted id: expected drop reason}."""
    d = root / "runs" / sport
    d.mkdir(parents=True)
    snaps, poly, jev, scope, planted = [], {}, [], [], {}
    for i in range(n):
        gid = f"{sport}{i:04d}"
        t0 = start + dt.timedelta(days=i // 8, hours=(i % 8))
        if sport == "ncaaf":
            t0 = dt.datetime(2026, 10, 10, 18, tzinfo=dt.timezone.utc) + dt.timedelta(days=7 * (i // 40), minutes=i % 40)
        away, home = f"A{i}", f"H{i}"
        s, n1, n2 = rng.gauss(0, 1), rng.gauss(0, 0.3), rng.gauss(0, 0.2)
        pe, p60, p5 = sig(s), sig(s + n1), sig(s + n1 + n2)
        q60, q5 = sig(s + n1 + 0.4 * (1 if rng.random() < 0.5 else -1)), min(max(p5 + rng.gauss(0, 0.01), 0.01), 0.99)
        ev = lambda p: {"id": gid, "commence_time": t0.strftime("%Y-%m-%dT%H:%M:%SZ"), "away_team": away, "home_team": home,
                        "bookmakers": [odds(p, away, home)] if p is not None else []}
        kind = None
        if plant and i < 6:
            kind = ["postponed", "no Pinnacle T-5", "no unique Polymarket match", "no Polymarket price at T-5",
                    "no clean result", "out"][i]
            if kind == "postponed":
                gid = next(iter(A.POSTPONED))
        t_early, t_60, t_5 = t0 - dt.timedelta(hours=8), t0 - dt.timedelta(minutes=58), t0 - dt.timedelta(minutes=6)
        snaps.append({"keys": [f"early:{t_early.date()}"], "fetched_at": t_early.isoformat(), "events": [ev(pe)]})
        snaps.append({"keys": [f"t60:{t0}"], "fetched_at": t_60.isoformat(), "events": [ev(p60)]})
        snaps.append({"keys": [f"t5:{t0}"], "fetched_at": t_5.isoformat(), "events": [ev(None if kind == "no Pinnacle T-5" else p5)]})
        hist = [{"t": int(t_60.timestamp()) - 30, "p": q60}, {"t": int(t_5.timestamp()) - 30, "p": q5}]
        if kind == "no Polymarket price at T-5":
            hist = [{"t": int(t_5.timestamp()) - 1200, "p": q5}]
        y = int(rng.random() < p5)
        if kind != "no unique Polymarket match":
            poly[gid] = {"market_id": str(i), "away_won": None if kind == "no clean result" else y, "history_away": hist}
        else:
            poly[gid] = {"match": "0 candidates"}
        jev.append({"id": gid, "v_away": {"noul_both": sig(s + rng.gauss(0, 1.0)), "bins_plain": s + rng.gauss(0, 1.5)}})
        if kind != "out":
            scope.append(gid)
        if kind:
            planted[gid] = kind
    (d / "state.json").write_text(json.dumps({"events": [], "scope": scope}))
    (d / "snapshots.jsonl").write_text("".join(json.dumps(s) + "\n" for s in snaps))
    (d / "poly.json").write_text(json.dumps(poly))
    (d / "jev.jsonl").write_text("".join(json.dumps(j) + "\n" for j in jev))
    return planted


class Units(unittest.TestCase):
    def test_novig_removes_the_margin(self):
        self.assertAlmostEqual(A.novig({"away_team": "a", "home_team": "h", "bookmakers": [odds(0.6, "a", "h")]}), 0.6, places=3)

    def test_polymarket_price_must_be_recent(self):
        t = dt.datetime(2026, 10, 20, tzinfo=dt.timezone.utc)
        h = [{"t": int(t.timestamp()) - 700, "p": 0.4}, {"t": int(t.timestamp()) - 500, "p": 0.5}, {"t": int(t.timestamp()) + 30, "p": 0.6}]
        self.assertEqual(A.poly_at(h, t), 0.5)
        self.assertIsNone(A.poly_at(h[:1], t))

    def test_partial_correlation_removes_the_shared_part(self):
        rng = random.Random(3)
        z = [rng.gauss(0, 1) for _ in range(3000)]
        x = [a + rng.gauss(0, 0.5) for a in z]
        y = [a + rng.gauss(0, 0.5) for a in z]
        self.assertGreater(A.spearman(x, y), 0.6)
        self.assertLess(abs(A.partial(x, y, z)), 0.06)

    def test_logistic_fit_recovers_the_slope(self):
        import numpy as np
        rng = random.Random(4)
        x = [rng.gauss(0, 1) for _ in range(5000)]
        y = [int(rng.random() < sig(0.3 + 1.5 * v)) for v in x]
        w = A.fit(np.array([[1.0, v] for v in x]), np.array(y, float))
        self.assertAlmostEqual(w[0], 0.3, delta=0.1)
        self.assertAlmostEqual(w[1], 1.5, delta=0.15)


class Synthetic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        rng = random.Random(11)
        cls.planted = {}
        for sport, n in (("nhl", 400), ("mlb", 60), ("ncaaf", 160)):
            cls.planted.update(world(root, sport, n, dt.datetime(2026, 10, 7, 23, tzinfo=dt.timezone.utc), rng, plant=sport in ("mlb", "ncaaf")))
        cls.data = A.load(root, NOW)
        cls.res = A.report(root, b=200, now=NOW)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_planted_drops_are_counted_by_reason(self):
        rows, drops = self.data["mlb"]
        want = {k for k in self.planted.values() if k != "out"}
        self.assertEqual(set(drops), want)
        self.assertTrue(all(v == 1 for v in drops.values()))
        self.assertEqual(len(rows), 60 - 5)                                     # MLB has no scope list: "out" is kept
        rows, drops = self.data["ncaaf"]
        self.assertEqual(set(drops), want)
        self.assertEqual(len(rows), 160 - 6)                                    # NCAA football: "out" is not in scope

    def test_nhl_window_and_ncaaf_scope(self):
        self.assertTrue(all(A.NHL_DAYS[0] <= r["day"] <= A.NHL_DAYS[1] for r in self.data["nhl"][0]))
        self.assertLess(len(self.data["nhl"][0]), 400)                         # games after 11-05 are excluded

    def test_known_answers(self):
        r = self.res["nhl"]
        self.assertTrue(r["C1"]["holds"])
        self.assertTrue(r["C3"]["holds"])
        self.assertGreater(r["C3"]["poly_closes"], 0.8)
        self.assertLess(abs(r["C3"]["pin_closes"]), 0.2)
        for cfg in A.CONFIGS:
            self.assertTrue(r[f"J3 {cfg}"]["holds"])
            self.assertGreater(r[f"J2 {cfg}"]["rho_early"], r[f"J2 {cfg}"]["rho_pin5"])
        lo, hi = r["C2"]["ci"]
        self.assertLess(lo, hi)

    def test_verdict_rules_and_pilot_subset(self):
        self.assertTrue(self.res["ncaaf"]["verdicts"])                          # 154 usable synthetic games
        self.assertIn("ncaaf-pilot", self.res)
        self.assertFalse(self.res["mlb"]["verdicts"])

    def test_pooled_and_j4_present(self):
        self.assertEqual(self.res["pooled"]["n"], sum(len(rows) for rows, _ in self.data.values()))
        self.assertEqual(set(self.res["J4"]), set(A.CONFIGS))


if __name__ == "__main__":
    unittest.main()
