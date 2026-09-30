"""Sanity checks on the permutation test and Spearman. Standard library only: python -m unittest discover tests"""
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from analyze import perm_p, spearman  # noqa: E402


class Stats(unittest.TestCase):
    def test_perfect_correlation_rejects_the_null(self):
        a = [i / 30 for i in range(30)]
        self.assertAlmostEqual(spearman(a, a), 1.0)
        self.assertLess(perm_p(a, a, n=2000), 0.001)

    def test_null_p_values_are_roughly_uniform(self):
        rng = random.Random(1)
        ps = []
        for k in range(200):
            a = [rng.random() for _ in range(30)]
            b = [rng.random() for _ in range(30)]
            ps.append(perm_p(a, b, n=199, seed=k))
        below = sum(p <= 0.05 for p in ps) / len(ps)
        self.assertLess(abs(below - 0.05), 0.04)   # false-positive rate near 5%

    def test_ties_are_ranked_by_average(self):
        self.assertAlmostEqual(spearman([1, 1, 2, 3], [1, 2, 3, 4]), 0.9486832980505138)



class Scores(unittest.TestCase):
    def test_coin_flip_brier_is_a_quarter(self):
        from analyze_games import brier
        self.assertAlmostEqual(brier([0.5] * 4, [1, 0, 1, 0]), 0.25)

    def test_brier_and_log_loss_known_values(self):
        import math
        from analyze_games import brier, log_loss
        self.assertAlmostEqual(brier([0.8, 0.3], [1, 0]), (0.04 + 0.09) / 2)
        self.assertAlmostEqual(log_loss([0.8, 0.3], [1, 0]), (-math.log(0.8) - math.log(0.7)) / 2)


if __name__ == "__main__":
    unittest.main()
