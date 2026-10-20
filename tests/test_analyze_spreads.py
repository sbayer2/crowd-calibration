"""analyze_spreads.py on synthetic data in live_odds.py's t72 formats, with known answers:
python -m unittest tests.test_analyze_spreads

The synthetic world: Pinnacle's line L; the result is L plus noise (SD 15); Kalshi sits within half a point of L,
Polymarket within about 1.5. Jev's margin is a compressed L plus noise and a missing home edge of 3 points; its total
is unrelated to Pinnacle's. So S1, S2, J5, J6 and J7 hold, J8's cover rate is near 50%, and the home term helps.
"""
import json
import random
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import analyze_spreads as A  # noqa: E402


def world(root: Path, n: int, rng: random.Random) -> None:
    d = root / "runs" / "ncaaf"
    d.mkdir(parents=True)
    t72, scores = [], {}
    for i in range(n):
        gid, key = f"g{i:04d}", f"t72:2026-1{0 + (i // 100)}-{24 - (i // 100) * 10:02d}"
        line, total = round(rng.gauss(-3, 14) * 2) / 2, round(rng.gauss(52, 7) * 2) / 2
        margin, pts = round(line + rng.gauss(0, 15)), round(total + rng.gauss(0, 13))
        away = max(0, round((pts + margin) / 2))
        home = max(0, pts - away)
        lad = lambda v: {"line": v, "usable": 10, "rungs": 20, "ladder": []}
        kal = {"spread": lad(line + rng.uniform(-0.5, 0.5)), "total": lad(total + rng.uniform(-0.7, 0.7))} if i % 10 else None
        pol = {"spread": lad(line + rng.gauss(0, 1.2)), "total": lad(None if i % 4 == 0 else total + rng.gauss(0, 1.5))}
        t72.append({"kind": "market", "key": key, "id": gid, "away": f"A{i}", "home": f"H{i}",
                    "commence": f"2026-10-24T{16 + i % 8:02d}:{i % 60:02d}:00Z", "late": i == 0, "lead_h": 72.0,
                    "pinnacle": {"spread": line, "total": total}, "kalshi": kal, "polymarket": pol})
        jm = 0.6 * line + 3 + rng.gauss(0, 5)                                       # +3: no home edge
        t72.append({"kind": "jev", "id": gid, "margin_median": jm, "margin_ev": jm * 0.9, "total_median": rng.gauss(51, 4),
                    "total_ev": rng.gauss(51, 4)})
        scores[gid] = {"completed": i != 1, "away_score": away if i != 1 else None, "home_score": home if i != 1 else None,
                       "neutral": i % 25 == 0}
    (d / "t72.jsonl").write_text("".join(json.dumps(r) + "\n" for r in t72))
    (d / "scores.json").write_text(json.dumps(scores))


class Units(unittest.TestCase):
    def test_wilson_interval(self):
        lo, hi = A.wilson(50, 100)
        self.assertAlmostEqual(lo, 0.404, places=3)
        self.assertAlmostEqual(hi, 0.596, places=3)

    def test_cover_skips_pushes_and_small_gaps(self):
        rows = [{"j": 5, "l": 3, "y": 7}, {"j": 5, "l": 3, "y": 3}, {"j": 1, "l": 3, "y": 0}, {"j": 3.5, "l": 3, "y": 0}]
        c = A.cover(rows, "j", "l", "y")
        self.assertEqual((c["n"], c["rate"]), (3, 2 / 3))                             # the push (y == l) is left out
        self.assertEqual(A.cover(rows, "j", "l", "y", gap=1.0)["n"], 2)

    def test_home_term_removes_a_constant_bias(self):
        rows = [{"neutral": False, "jev_margin": m + 3, "margin": m} for m in range(-20, 20)]
        adj = A.home_term(rows)
        self.assertTrue(all(abs(a - r["margin"]) < 1e-9 for a, r in zip(adj, rows)))


class Synthetic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        world(Path(cls.tmp.name), 300, random.Random(5))
        cls.res = A.report(Path(cls.tmp.name), b=200)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_counts_and_market_fallback(self):
        self.assertEqual(self.res["games"], 300)
        self.assertEqual(self.res["notes"], {"final": 299, "not final": 1})
        self.assertEqual(self.res["usable_ladders"]["k_spread"], 270)                # every 10th game has no Kalshi
        self.assertEqual(self.res["S3"]["n"], 299)                                  # Polymarket fills in

    def test_known_answers(self):
        r = self.res
        self.assertTrue(r["S1"]["holds"])
        self.assertTrue(r["S2"]["holds"])
        j = r["J5-J7 jev_margin"]
        self.assertTrue(j["J5_holds"] and j["J6_holds"] and j["J7_holds"])
        self.assertTrue(r["J8 jev_margin"]["spread"]["holds"])
        self.assertLess(r["S4 jev_margin with home term (secondary)"]["mae_a"], r["S4 jev_margin"]["mae_a"])


if __name__ == "__main__":
    unittest.main()
