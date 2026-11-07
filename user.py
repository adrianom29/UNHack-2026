
import argparse
import json
import sqlite3
from datetime import date

import numpy as np
from scipy.special import logsumexp
from scipy.stats import gamma, poisson


# ==========================================
# 1. SETTINGS
# ==========================================

DATABASE = "smartprep.db"

# Initial model assumptions.
# These should be calibrated with real data.
PRIOR_MEAN = 30.0
PRIOR_SHAPE = 2.0
GRID_POINTS = 4001


# ==========================================
# 2. DATABASE
# ==========================================

def connect():

    db = sqlite3.connect(DATABASE)

    db.execute("""
        CREATE TABLE IF NOT EXISTS daily_records (
            day TEXT PRIMARY KEY,
            prepared INTEGER NOT NULL
                CHECK(prepared >= 1),
            sold INTEGER NOT NULL
                CHECK(sold >= 0 AND sold <= prepared)
        )
    """)

    db.commit()
    return db


def save_day(db, prepared, sold, day=None):

    if prepared < 1 or sold < 0 or sold > prepared:
        raise ValueError(
            "Require prepared >= 1 and "
            "0 <= sold <= prepared."
        )

    if day is None:
        day = date.today().isoformat()
    else:
        day = date.fromisoformat(day).isoformat()

    db.execute("""
        INSERT INTO daily_records(day, prepared, sold)
        VALUES (?, ?, ?)
        ON CONFLICT(day) DO UPDATE SET
            prepared = excluded.prepared,
            sold = excluded.sold
    """, (day, prepared, sold))

    db.commit()

    return {
        "date": day,
        "prepared": prepared,
        "sold": sold,
        "unsold": prepared - sold
    }


def get_history(db):

    rows = db.execute("""
        SELECT day, prepared, sold
        FROM daily_records
        ORDER BY day
    """).fetchall()

    return [
        {
            "date": day,
            "prepared": prepared,
            "sold": sold,
            "unsold": prepared - sold
        }
        for day, prepared, sold in rows
    ]


# ==========================================
# 3. STATISTICAL DEMAND MODEL
# ==========================================

def fit_demand(history):

    if not history:
        raise ValueError(
            "At least one trading day is required."
        )

    # Demand D follows a Poisson distribution.
    #
    # If sold < prepared:
    #   observed demand = sold
    #
    # If sold == prepared:
    #   demand >= prepared
    #   (censored observation)

    maximum = max(
        record["prepared"] for record in history
    )

    upper = max(
        120.0,
        4.0 * maximum,
        6.0 * PRIOR_MEAN
    )

    # Numerical Bayesian posterior calculation
    for _ in range(6):

        lam = np.linspace(
            0.001,
            upper,
            GRID_POINTS
        )

        # Gamma prior
        log_posterior = gamma.logpdf(
            lam,
            a=PRIOR_SHAPE,
            scale=PRIOR_MEAN / PRIOR_SHAPE
        )

        for record in history:

            sold = record["sold"]
            prepared = record["prepared"]

            if sold < prepared:

                # Exact demand observation
                log_posterior += poisson.logpmf(
                    sold,
                    lam
                )

            else:

                # Censored demand:
                # P(D >= prepared)
                log_posterior += poisson.logsf(
                    prepared - 1,
                    lam
                )

        # Normalize posterior probabilities
        weights = np.exp(
            log_posterior
            - logsumexp(log_posterior)
        )

        # Check that the posterior tail
        # has not been truncated.
        if weights[-10:].sum() < 1e-6:
            return lam, weights

        upper *= 2

    raise RuntimeError(
        "Could not safely bound demand distribution."
    )


# ==========================================
# 4. DEMAND FORECASTING
# ==========================================

def forecast(history):

    lam, weights = fit_demand(history)

    # Predictive cumulative distribution
    def cdf(k):

        if k < 0:
            return 0.0

        return float(
            np.dot(
                weights,
                poisson.cdf(k, lam)
            )
        )

    # Find predictive percentile
    def quantile(probability):

        predicted_mean = np.dot(weights, lam)

        high = max(
            10,
            int(np.ceil(predicted_mean * 2))
        )

        while cdf(high) < probability:
            high *= 2

        low = 0

        while low < high:

            mid = (low + high) // 2

            if cdf(mid) >= probability:
                high = mid
            else:
                low = mid + 1

        return low

    # Calculate expected leftover portions
    def expected_unsold(quantity):

        result = (
            quantity * cdf(quantity)
            - np.dot(
                weights,
                lam * poisson.cdf(
                    quantity - 1,
                    lam
                )
            )
        )

        return max(0.0, float(result))

    # Expected future demand
    predicted_demand = float(
        np.dot(weights, lam)
    )

    # 80% prediction interval
    lower = quantile(0.10)
    upper = quantile(0.90)

    # ======================================
    # 5. THREE PREPARATION STRATEGIES
    # ======================================

    strategies = {
        "Conservative": 0.25,
        "Balanced": 0.50,
        "Aggressive": 0.75
    }

    recommendations = {}

    for name, percentile in strategies.items():

        quantity = quantile(percentile)

        # Probability demand exceeds stock
        stockout_risk = 1 - cdf(quantity)

        recommendations[name] = {
            "prepare": quantity,

            "stockout_risk_percent": round(
                100 * stockout_risk,
                1
            ),

            "expected_unsold": round(
                expected_unsold(quantity),
                1
            )
        }

    # Historical statistics
    total_prepared = sum(
        r["prepared"] for r in history
    )

    total_sold = sum(
        r["sold"] for r in history
    )

    total_unsold = total_prepared - total_sold

    return {
        "historical_statistics": {
            "trading_days": len(history),
            "total_prepared": total_prepared,
            "total_sold": total_sold,
            "total_unsold": total_unsold
        },

        "predicted_demand": round(
            predicted_demand, 1
        ),

        "prediction_interval_80": [
            lower,
            upper
        ],

        "recommendations": recommendations
    }


# ==========================================
# 6. COMMAND LINE PROGRAM
# ==========================================

def main():

    parser = argparse.ArgumentParser(
        description="SmartPrep Statistical Model"
    )

    commands = parser.add_subparsers(
        dest="command",
        required=True
    )

    # Add daily record
    add = commands.add_parser("add")

    add.add_argument(
        "--prepared",
        type=int,
        required=True
    )

    add.add_argument(
        "--sold",
        type=int,
        required=True
    )

    add.add_argument(
        "--date",
        type=str
    )

    # Forecast
    commands.add_parser("forecast")

    # View historical records
    commands.add_parser("history")

    args = parser.parse_args()

    db = connect()

    try:

        if args.command == "add":

            result = save_day(
                db,
                args.prepared,
                args.sold,
                args.date
            )

        elif args.command == "history":

            result = get_history(db)

        elif args.command == "forecast":

            result = forecast(
                get_history(db)
            )

        print(
            json.dumps(
                result,
                indent=2,
                ensure_ascii=False
            )
        )

    finally:
        db.close()


if __name__ == "__main__":
    main()
