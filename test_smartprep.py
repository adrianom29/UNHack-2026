import math
import random
import unittest
from smartprep import solve, metrics


class ModelTests(unittest.TestCase):
    def test_service_targets(self):
        for level, q in [(0, 83), (0.8, 93), (0.9, 100), (0.95, 105)]:
            r = solve(service_level=level)
            self.assertEqual(r["optimal"]["quantity"], q)
            self.assertEqual(r["profit_only"]["quantity"], 83)
            if level:
                self.assertLessEqual(
                    r["optimal"]["stockout_probability"], 1 - level + 1e-12
                )
        self.assertEqual(solve(4, 5, 80, 0, 100, 0.95)["optimal"]["quantity"], 80)
        self.assertEqual(solve(12, 5, 0, 0, 0, 0.95)["optimal"]["quantity"], 0)
        for level in [-1, 1, float("nan"), True]:
            with self.assertRaises(ValueError):
                solve(service_level=level)

    def test_service_constrained_global_optimum(self):
        rng = random.Random(43)
        for _ in range(100):
            p = rng.uniform(0.1, 30)
            c = rng.uniform(0.1, 35)
            mu = rng.uniform(0, 40)
            sigma = rng.uniform(0.1, 20)
            level = rng.choice([0.8, 0.9, 0.95])
            r = solve(p, c, mu, sigma, 20, level)
            feasible = [
                metrics(q, p, c, mu, sigma)
                for q in range(250)
                if metrics(q, p, c, mu, sigma)["stockout_probability"] <= 1 - level
            ]
            self.assertAlmostEqual(
                r["optimal"]["profit"], max(m["profit"] for m in feasible), places=8
            )

    def test_default(self):
        r = solve()
        self.assertEqual(r["optimal"]["quantity"], 83)
        self.assertGreater(r["delta"]["profit"], 0)
        self.assertLess(r["delta"]["waste"], 0)

    def test_integer_global_optimum(self):
        rng = random.Random(42)
        for _ in range(200):
            p = rng.uniform(0.1, 30)
            c = rng.uniform(0.01, 35)
            mu = rng.uniform(0, 40)
            sigma = rng.uniform(0, 20)
            r = solve(p, c, mu, sigma, 20)
            brute = max(metrics(q, p, c, mu, sigma)["profit"] for q in range(250))
            self.assertAlmostEqual(r["optimal"]["profit"], brute, places=8)

    def test_edges(self):
        for p, c in [(0, 0), (0, 5), (5, 5), (4, 5)]:
            self.assertEqual(solve(p, c)["optimal"]["quantity"], 0)
        self.assertEqual(solve(12, 5, 80, 0)["optimal"]["quantity"], 80)
        self.assertEqual(solve(12, 0, 80, 0)["optimal"]["quantity"], 80)
        self.assertEqual(solve(12, 5, 0, 0, 0)["optimal"]["profit"], 0)
        self.assertEqual(solve(12, 5, 80, 0, 80)["baseline"]["stockout_probability"], 0)
        self.assertEqual(solve(12, 5, 80, 0, 0)["baseline"]["stockout_probability"], 1)
        self.assertGreater(solve(12, 5, 0, 15)["effective_mean"], 0)
        self.assertEqual(solve(12, 11, 0, 15)["optimal"]["quantity"], 0)

    def test_invalid(self):
        for kwargs in [
            dict(p=-1),
            dict(c=float("nan")),
            dict(mu=float("inf")),
            dict(sigma=-1),
            dict(baseline=1.5),
            dict(baseline=True),
            dict(p=12, c=0, sigma=15),
            dict(mu=1e7),
        ]:
            with self.assertRaises(ValueError):
                solve(**kwargs)

    def test_expected_values_independent_simulation(self):
        rng = random.Random(2026)
        n = 100000
        ds = [max(0, rng.gauss(5, 15)) for _ in range(n)]
        q = 12
        m = metrics(q, 12, 5, 5, 15)
        profits = [12 * min(q, d) - 5 * q for d in ds]
        self.assertLess(abs(sum(profits) / n - m["profit"]), 0.8)
        self.assertLess(abs(sum(max(0, q - d) for d in ds) / n - m["waste"]), 0.08)
        self.assertLess(
            abs(sum(d > q for d in ds) / n - m["stockout_probability"]), 0.006
        )

    def test_conservation(self):
        for mu, sigma in [(80, 15), (0, 50), (80, 0), (1000000, 0.001)]:
            r = solve(12, 5, mu, sigma, 100)
            for m in [r["baseline"], r["optimal"]]:
                self.assertAlmostEqual(m["sales"] + m["waste"], m["quantity"])
                self.assertAlmostEqual(
                    m["sales"] + m["unmet_demand"], r["effective_mean"]
                )
                self.assertTrue(0 <= m["stockout_probability"] <= 1)


if __name__ == "__main__":
    unittest.main()
