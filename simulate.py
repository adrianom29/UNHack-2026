"""Simulate SmartPrep on synthetic businesses and report how accurate it is.

Each run invents one menu item with a known "true" demand: a base level, a
weekday pattern, a slow trend and day-to-day noise (skewed, whole items, so
not the bell curve the model assumes). The owner first runs it by habit for
a warm-up period, then four ways of choosing how many to make are compared
on the same days of demand:

  owner    - keeps making the habitual amount (the "before" picture)
  old      - previous SmartPrep: plain average and spread of units sold
  new      - current SmartPrep: demand.estimate() (sell-outs, weekdays, recency)
  oracle   - knows the true demand distribution each day (best possible)

Old and new each keep their own records, so their sell-outs affect what they
learn, exactly as in real use. The app's backtest is also run on the owner's
history and compared with what really happened, to check that the
percentages the app shows are honest.

Pass criteria (fixed before looking at results; the script exits with
status 1 if any fails):

  1. The new method's forecast error is lower than the old method's.
  2. The new method increases profit over the owner's habit (average).
  3. The new method makes more profit than the old method (average).
  4. The new method runs out on fewer days than the old method (average).
  5. The app's backtest profit figure is within 3 percentage points of the
     real result, on average.

Usage: py simulate.py [--runs 100] [--days 28] [--warmup 14] [--seed 2026]
                      [--service-level 0]
"""

PROFIT_GAP_LIMIT = 3.0

import argparse
import math
import random
import statistics
import sys
from datetime import date, timedelta

import demand
from smartprep import backtest, best_quantity


def make_business(rng, days):
    """True mean demand for each day, plus price, cost and noise level."""
    base = rng.uniform(20, 150)
    pattern = [rng.uniform(0.7, 1.3) for _ in range(7)]
    scale = statistics.mean(pattern)
    pattern = [m / scale for m in pattern]
    trend = rng.uniform(-0.004, 0.006)  # per day, multiplicative
    start = date(2026, 1, 5) + timedelta(days=rng.randrange(7))
    price = rng.uniform(4, 15)
    calendar = [start + timedelta(days=t) for t in range(days)]
    means = [
        base * pattern[d.weekday()] * (1 + trend) ** t for t, d in enumerate(calendar)
    ]
    return dict(
        base=base,
        calendar=calendar,
        means=means,
        cv=rng.uniform(0.15, 0.45),
        price=price,
        cost=price * rng.uniform(0.25, 0.6),
        habit=round(base * rng.uniform(0.9, 1.3)),
    )


def draw(rng, mean, cv):
    """Skewed whole-item demand with the given mean and coefficient of variation."""
    shape = 1 / cv**2
    return round(rng.gammavariate(shape, mean / shape))


def oracle_quantity(rng, mean, cv, p, c, service_level, samples=400):
    """Best quantity when the true distribution is known (by sampling it)."""
    draws = sorted(draw(rng, mean, cv) for _ in range(samples))
    ratio = max((p - c) / p, service_level)
    return draws[min(samples - 1, math.ceil(ratio * samples) - 1)]


def old_estimate(history):
    sold = [r["sold"] for r in history if r["prepared"] > 0]
    return statistics.mean(sold), max(statistics.stdev(sold), demand.MIN_SIGMA)


def run_once(seed, days, warmup, service_level):
    rng = random.Random(seed)
    b = make_business(rng, days)
    p, c = b["price"], b["cost"]
    actual = [draw(rng, m, b["cv"]) for m in b["means"]]
    oracle_rng = random.Random(seed + 1_000_003)

    def record(day, made, d):
        return dict(day=day.isoformat(), prepared=made, sold=min(made, d))

    warm = [record(b["calendar"][t], b["habit"], actual[t]) for t in range(warmup)]
    histories = {"old": list(warm), "new": list(warm)}
    owner_history = list(warm)
    totals = {
        name: dict(waste=0, profit=0.0, stockout_days=0, made=0)
        for name in ("owner", "old", "new", "oracle")
    }
    errors = {"old": [], "new": []}
    for t in range(warmup, days):
        day, d, true_mean = b["calendar"][t], actual[t], b["means"][t]
        quantities = {
            "owner": b["habit"],
            "oracle": oracle_quantity(
                oracle_rng, true_mean, b["cv"], p, c, service_level
            ),
        }
        mu, sigma = old_estimate(histories["old"])
        errors["old"].append(abs(mu - true_mean) / true_mean)
        quantities["old"] = best_quantity(p, c, mu, sigma, service_level)[0]
        est = demand.estimate(histories["new"], day)
        errors["new"].append(abs(est["mu"] - true_mean) / true_mean)
        quantities["new"] = best_quantity(p, c, est["mu"], est["sigma"], service_level)[0]
        for name, q in quantities.items():
            sold = min(q, d)
            totals[name]["waste"] += q - sold
            totals[name]["profit"] += p * sold - c * q
            totals[name]["stockout_days"] += d > q
            totals[name]["made"] += q
        for name in ("old", "new"):
            histories[name].append(record(day, quantities[name], d))
        owner_history.append(record(day, b["habit"], d))

    # What the app would have told this owner, from their own records only.
    check = backtest(owner_history, p, c, service_level, window=days - warmup)
    return b, totals, errors, check


def pct(before, after):
    return 100 * (after - before) / before if before else None


def summarize(values, center=statistics.mean):
    values = sorted(v for v in values if v is not None)
    if not values:
        return "n/a"
    lo = values[int(0.05 * (len(values) - 1))]
    hi = values[int(0.95 * (len(values) - 1))]
    return f"{center(values):7.1f}   ({lo:6.1f} to {hi:6.1f})"


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--runs", type=int, default=100)
    parser.add_argument("--days", type=int, default=28)
    parser.add_argument("--warmup", type=int, default=14)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--service-level", type=float, default=0)
    args = parser.parse_args()
    if not 2 <= args.warmup < args.days:
        parser.error("--warmup must be at least 2 and less than --days")

    rows = []
    for run in range(args.runs):
        rows.append(run_once(args.seed + run, args.days, args.warmup, args.service_level))

    evaluated = args.days - args.warmup
    print(
        f"SmartPrep simulation: {args.runs} businesses x {args.days} days "
        f"({args.warmup} warm-up days by habit, {evaluated} days compared), "
        f"service level {args.service_level:g}, seed {args.seed}"
    )
    print("Values are the average across runs, with the 5th to 95th percentile range.\n")

    averages = {}
    print("Forecast error (|forecast - true mean demand| / true mean, % per day)")
    for name in ("old", "new"):
        per_run = [100 * statistics.mean(e[name]) for _, _, e, _ in rows]
        averages[("error", name)] = statistics.mean(per_run)
        print(f"  {name:<8} {summarize(per_run)}")

    print("\nChange compared with the owner's habit (%)")
    for label, key, sign in (
        ("Waste reduction", "waste", -1),
        ("Profit increase", "profit", 1),
    ):
        print(f"  {label}")
        for name in ("old", "new", "oracle"):
            values = []
            for _, t, _, _ in rows:
                change = pct(t["owner"][key], t[name][key])
                values.append(None if change is None else sign * change)
            kept = [v for v in values if v is not None]
            averages[(key, name)] = statistics.mean(kept) if kept else None
            print(f"    {name:<8} {summarize(values)}")

    # A ratio with a small denominator in some runs: the median is the fair summary.
    print(
        "\nShare of the oracle's profit gain over the owner that was captured"
        " (%, median)"
    )
    for name in ("old", "new"):
        values = []
        for _, t, _, _ in rows:
            gain = t["oracle"]["profit"] - t["owner"]["profit"]
            if gain > 1e-9:
                values.append(100 * (t[name]["profit"] - t["owner"]["profit"]) / gain)
        print(f"  {name:<8} {summarize(values, statistics.median)}")

    print("\nDays that ran out (% of compared days)")
    for name in ("owner", "old", "new", "oracle"):
        values = [100 * t[name]["stockout_days"] / evaluated for _, t, _, _ in rows]
        averages[("stockouts", name)] = statistics.mean(values)
        print(f"  {name:<8} {summarize(values)}")

    print("\nHonesty check: the app's backtest vs what really happened (new method)")
    shown, real = [], []
    for _, t, _, check in rows:
        if check["days"] and check["actual_waste"] > 0 and check["actual_profit"] > 0:
            shown.append(
                (
                    -pct(check["actual_waste"], check["plan_waste"]),
                    pct(check["actual_profit"], check["plan_profit"]),
                )
            )
            real.append(
                (
                    -pct(t["owner"]["waste"], t["new"]["waste"]),
                    pct(t["owner"]["profit"], t["new"]["profit"]),
                )
            )
    profit_gap = None
    if shown:
        for i, label in enumerate(("Waste reduction", "Profit increase")):
            gap = [s[i] - r[i] for s, r in zip(shown, real)]
            if i == 1:
                profit_gap = statistics.mean(gap)
            print(
                f"  {label}: app shows {statistics.mean(s[i] for s in shown):.1f}%, "
                f"real {statistics.mean(r[i] for r in real):.1f}%, "
                f"gap {summarize(gap).strip()} points"
            )
        print(
            "  (A negative gap means the app understates the benefit, which is the"
            " safe direction.)"
        )
    else:
        print("  Not enough backtest days to compare.")

    a = averages
    checks = [
        (
            "New forecast error is lower than old",
            a[("error", "new")] < a[("error", "old")],
            f"{a[('error', 'new')]:.1f}% vs {a[('error', 'old')]:.1f}%",
        ),
        (
            "New method increases profit over the owner's habit",
            a[("profit", "new")] > 0,
            f"{a[('profit', 'new')]:+.1f}%",
        ),
        (
            "New method makes more profit than old",
            a[("profit", "new")] > a[("profit", "old")],
            f"{a[('profit', 'new')]:+.1f}% vs {a[('profit', 'old')]:+.1f}%",
        ),
        (
            "New method runs out on fewer days than old",
            a[("stockouts", "new")] < a[("stockouts", "old")],
            f"{a[('stockouts', 'new')]:.1f}% vs {a[('stockouts', 'old')]:.1f}% of days",
        ),
        (
            f"App's profit figure within {PROFIT_GAP_LIMIT:g} points of reality",
            profit_gap is not None and abs(profit_gap) <= PROFIT_GAP_LIMIT,
            "no data" if profit_gap is None else f"average gap {profit_gap:+.1f} points",
        ),
    ]
    print("\nPass criteria")
    for label, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}: {detail}")
    failed = sum(not ok for _, ok, _ in checks)
    print(f"\n{'ALL PASSED' if not failed else f'{failed} FAILED'} ({len(checks)} checks)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
