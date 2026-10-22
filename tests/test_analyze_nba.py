"""analyze_nba.py on synthetic data in nba_free.py's file formats, with known answers. Standard library + numpy:
python -m unittest tests.test_analyze_nba

The synthetic world: a strength gap s per game; the early price sees s, the close adds news. Kalshi sits on Polymarket
with tiny noise, and the result is drawn from Polymarket's close. Jev sees s plus heavy noise, and no news. So E1
holds, E2 is null both ways, N1 holds, N2 favours the early price, and X6 holds against an NCAA football world whose
Jev is less noisy (tests/test_analyze_live.py).
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
sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_nba as A  # noqa: E402
from test_analyze_live import world as live_world  # noqa: E402

NOW = dt.datetime(2026, 12, 10, tzinfo=dt.timezone.utc)
sig = lambda x: 1 / (1 + math.exp(-x))
KINDS = ["postponed", "no Jev answer before the start", "no unique Polymarket match", "no Polymarket price at T-5",
         "no clean result", "Kalshi result disagrees (kept, no Kalshi)", "out of window"]


def nba_world(root: Path, n: int, rng: random.Random) -> dict[str, str]:
    d = root / "runs" / "nba"
    d.mkdir(parents=True)
    games, data, jev, planted = {}, {}, [], {}
    for i in range(n):
        gid = str(400000 + i)
        start = dt.datetime(2026, 10, 23, 23, tzinfo=dt.timezone.utc) + dt.timedelta(days=i // 7, minutes=30 * (i % 7))
        kind = KINDS[i] if i < len(KINDS) else None
        if kind == "out of window":
            start = dt.datetime(2026, 10, 21, 23, tzinfo=dt.timezone.utc)
        day = start.astimezone(A.L.CT).date().isoformat()
        s, news = rng.gauss(0, 1.2), rng.gauss(0, 0.5)
        pe, p60, p5 = sig(s), sig(s + 0.6 * news), sig(s + news)
        y = int(rng.random() < p5)
        games[gid] = {"id": gid, "away": f"A{i}", "home": f"H{i}", "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "day": day,
                      "status": "STATUS_POSTPONED" if kind == "postponed" else "STATUS_FINAL"}
        ts = lambda m: int((start - dt.timedelta(minutes=m)).timestamp())
        early_ts = int(dt.datetime.combine(dt.date.fromisoformat(day), dt.time(14), dt.timezone.utc).timestamp())
        hist = [{"t": early_ts - 60, "p": pe}, {"t": ts(61), "p": p60}, {"t": ts(6), "p": p5}]
        if kind == "no Polymarket price at T-5":
            hist = [{"t": early_ts - 60, "p": pe}]
        k = lambda p: [round(max(p - 0.005 + rng.gauss(0, 0.004), 0.01), 3), round(min(p + 0.005 + rng.gauss(0, 0.004), 0.99), 3)]
        candles = [[ts(62), *k(p60), None], [ts(7), *k(p5), None]]
        kres = "yes" if y else "no"
        if kind == "Kalshi result disagrees (kept, no Kalshi)":
            kres = "no" if y else "yes"
        winner_scores = (110, 100) if y else (100, 110)
        data[gid] = {"espn": {"status": games[gid]["status"], "completed": kind != "no clean result", "neutral": False,
                              "away_score": str(winner_scores[0]), "home_score": str(winner_scores[1])},
                     "poly": {"match": "0 candidates"} if kind == "no unique Polymarket match" else
                             {"market_id": gid, "away_won": y, "history_away": hist},
                     "kalshi": {"away_result": kres, "away_candles": candles}}
        asked = start - dt.timedelta(hours=8) if kind != "no Jev answer before the start" else start + dt.timedelta(minutes=2)
        jev.append({"id": gid, "asked_at": asked.isoformat(),
                    "v_away": {"noul_both": sig(s + rng.gauss(0, 3.0)), "bins_plain": s + rng.gauss(0, 4.0)}})
        if kind:
            planted[gid] = kind
    (d / "state.json").write_text(json.dumps({"games": games}))
    (d / "data.json").write_text(json.dumps(data))
    (d / "jev.jsonl").write_text("".join(json.dumps(j) + "\n" for j in jev))
    return planted


class Units(unittest.TestCase):
    def test_kalshi_price_rules(self):
        t = dt.datetime(2026, 11, 1, tzinfo=dt.timezone.utc)
        ts = int(t.timestamp())
        self.assertAlmostEqual(A.kalshi_at([[ts - 120, "0.40", "0.42", None]], t), 0.41)
        self.assertIsNone(A.kalshi_at([[ts - 700, "0.40", "0.42", None]], t))           # older than 10 minutes
        self.assertIsNone(A.kalshi_at([[ts - 60, "0.30", "0.45", None]], t))            # spread over 0.10
        self.assertIsNone(A.kalshi_at([[ts + 60, "0.40", "0.42", None]], t))            # after the moment
        self.assertIsNone(A.kalshi_at([[ts - 60, "0.00", "0.02", None]], t))            # no bid


class Synthetic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        rng = random.Random(5)
        cls.planted = nba_world(root, 300, rng)
        live_world(root, "ncaaf", 160, dt.datetime(2026, 10, 7, 23, tzinfo=dt.timezone.utc), rng, plant=False)
        cls.rows, cls.drops = A.games(root, NOW)
        cls.res = A.report(root, b=200, now=NOW)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_planted_drops(self):
        want = {k for k in self.planted.values() if k != "out of window"}
        self.assertEqual(set(self.drops), want)
        self.assertTrue(all(v == 1 for v in self.drops.values()))
        self.assertEqual(len(self.rows), 300 - 6)                                   # the Kalshi disagreement stays
        bad = next(g for g, k in self.planted.items() if k.startswith("Kalshi"))
        self.assertIsNone(next(r for r in self.rows if r["id"] == bad)["kal5"])

    def test_known_answers(self):
        r = self.res
        self.assertTrue(r["verdicts"])
        self.assertTrue(r["E1"]["holds"])
        self.assertTrue(r["E2"]["holds"])
        for cfg in A.CONFIGS:
            self.assertTrue(r[f"N1 {cfg}"]["holds"])
            self.assertGreater(r[f"N2 {cfg}"]["rho_early"], r[f"N2 {cfg}"]["rho_poly5"])
            self.assertTrue(r["X6"][cfg]["holds"])
            self.assertGreater(r["X6"][cfg]["rho_ncaaf"], r["X6"][cfg]["rho_nba"])

    def test_home_and_e3_present(self):
        self.assertAlmostEqual(self.res["home"]["away_win_share"], sum(r["y"] for r in self.rows) / len(self.rows))
        self.assertIn("n", self.res["E3"])


if __name__ == "__main__":
    unittest.main()
