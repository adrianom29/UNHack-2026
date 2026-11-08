import random
import statistics
import unittest
from datetime import date, timedelta

import demand
from smartprep import backtest, combine

START = date(2026, 3, 2)  # a Monday


def rows_from(sales, made, start=START):
    return [
        dict(day=(start + timedelta(days=i)).isoformat(), prepared=m, sold=min(s, m))
        for i, (s, m) in enumerate(zip(sales, made))
    ]


class CensoredFitTests(unittest.TestCase):
    def test_recovers_true_demand_when_sales_are_capped(self):
        rng = random.Random(7)
        true = [rng.gauss(80, 15) for _ in range(3000)]
        for cap in (70, 85):
            sold = [min(x, cap) for x in true]
            mu, sigma, _ = demand.censored_fit(
                sold, [x >= cap for x in true], [1] * len(true)
            )
            self.assertLess(statistics.mean(sold), 77)  # plain average is biased low
            self.assertAlmostEqual(mu, 80, delta=1.5)
            self.assertAlmostEqual(sigma, 15, delta=1.5)

    def test_without_sellouts_matches_plain_statistics(self):
        values = [70, 90, 85, 60]
        mu, sigma, filled = demand.censored_fit(values, [False] * 4, [1] * 4)
        self.assertAlmostEqual(mu, statistics.mean(values))
        self.assertAlmostEqual(sigma, statistics.stdev(values))
        self.assertEqual(filled, values)

    def test_minimum_spread_and_expected_above(self):
        _, sigma, _ = demand.censored_fit([5, 5, 5], [False] * 3, [1] * 3)
        self.assertGreaterEqual(sigma, demand.MIN_SIGMA)
        self.assertGreater(demand.expected_above(80, 15, 90), 90)
        # Far in the tail the shortcut formula is used without overflow.
        self.assertAlmostEqual(demand.expected_above(0, 1, 50), 50, delta=0.1)


class EstimateTests(unittest.TestCase):
    def test_needs_two_days_before_target(self):
        rows = rows_from([10, 12], [20, 20])
        self.assertIsNone(demand.estimate(rows[:1], START + timedelta(days=5)))
        self.assertIsNone(demand.estimate(rows, START))  # nothing before target
        self.assertIsNone(
            demand.estimate(rows, START + timedelta(days=demand.MAX_HISTORY_DAYS + 5))
        )
        self.assertEqual(demand.estimate(rows, START + timedelta(days=2))["days"], 2)

    def test_weekday_levels(self):
        # Fridays sell about double the other days, over eight weeks.
        rng = random.Random(3)
        sales = [
            round(rng.gauss(100 if (START + timedelta(days=i)).weekday() == 4 else 50, 5))
            for i in range(56)
        ]
        rows = rows_from(sales, [200] * 56)
        friday = START + timedelta(days=60)  # 2026-05-01 is a Friday
        monday = START + timedelta(days=63)
        self.assertEqual(friday.weekday(), 4)
        # Without weekdays both would be about 57. The Friday level is still
        # blended toward the overall level (WEEKDAY_SHRINK, tuned in simulate.py).
        self.assertGreater(demand.estimate(rows, friday)["mu"], 75)
        self.assertLess(demand.estimate(rows, monday)["mu"], 55)

    def test_recent_days_count_more(self):
        sales = [40] * 30 + [80] * 14  # demand stepped up two weeks ago
        rows = rows_from(sales, [200] * 44)
        mu = demand.estimate(rows, START + timedelta(days=44))["mu"]
        self.assertGreater(mu, statistics.mean(sales) + 5)

    def test_sellouts_raise_the_estimate(self):
        sales = [60, 95, 70, 100, 90, 100, 80]
        rows = rows_from(sales, [90] * 7)
        est = demand.estimate(rows, START + timedelta(days=7))
        self.assertEqual(est["sellouts"], 4)
        # Compare before the weekday adjustment, which this test is not about.
        level = est["mu"] / est["weekday_factor"]
        self.assertGreater(level, statistics.mean(min(s, 90) for s in sales) + 3)

    def test_all_sold_out_is_flagged(self):
        rows = rows_from([50, 60, 70], [40, 40, 40])
        est = demand.estimate(rows, START + timedelta(days=3))
        self.assertTrue(est["all_sold_out"])
        self.assertAlmostEqual(est["mu"], 40)


class BacktestTests(unittest.TestCase):
    def test_checks_only_unseen_days_in_window(self):
        rng = random.Random(11)
        sales = [round(rng.gauss(60, 8)) for _ in range(40)]
        rows = rows_from(sales, [90] * 40)  # habitually makes far too many
        result = backtest(rows, 10, 4, window=28)
        self.assertEqual(len(result["days"]), 28)
        self.assertEqual(result["days"][0], rows[12]["day"])
        self.assertEqual(result["actual_waste"], sum(90 - s for s in sales[12:]))
        self.assertLess(result["plan_waste"], result["actual_waste"] / 2)
        self.assertGreater(result["plan_profit"], result["actual_profit"])
        self.assertEqual(result["error_days"], 28)
        totals = combine([dict(backtest=result)])
        self.assertEqual(totals["source"], "backtest")
        self.assertEqual(totals["checked_days"], 28)
        self.assertGreater(totals["waste_reduction_pct"], 50)
        self.assertLess(totals["forecast_error_pct"], 20)

    def test_too_short_history_is_not_checked(self):
        rows = rows_from([50] * demand.MIN_DAYS, [60] * demand.MIN_DAYS)
        self.assertEqual(backtest(rows, 10, 4)["days"], [])
        self.assertEqual(backtest([], 10, 4)["days"], [])


if __name__ == "__main__":
    unittest.main()
