import numpy as np
from scipy.stats import gamma, poisson
from scipy.special import logsumexp

from entry import Entry


# =====================================
# 1. Estimate Demand Rate (Bayesian)
# =====================================

def estimate_demand(history: list[Entry]):

    # Gamma prior parameters
    alpha = 2.0
    beta = 0.08

    # Possible daily demand rates
    max_produced = max(entry.produced for entry in history)

    upper = max(120, max_produced * 4)

    for _ in range(6):

        lambdas = np.linspace(0.001, upper, 4001)

        log_posterior = gamma.logpdf(lambdas, a=alpha, scale=1 / beta)

        for entry in history:

            if entry.sold < entry.produced:
                # Demand is observed exactly
                log_posterior += poisson.logpmf(entry.sold, lambdas)
            else:
                # Sold out: actual demand >= produced
                log_posterior += poisson.logsf(entry.produced - 1, lambdas)

        # Normalize posterior distribution
        weights = np.exp(log_posterior - logsumexp(log_posterior))

        if weights[-10:].sum() < 1e-6:
            break

        upper *= 2

    else:
        raise RuntimeError("Posterior range is insufficient")

    return lambdas, weights


# =====================================
# 2. Predict Tomorrow's Demand
# =====================================

def predict_demand(history: list[Entry]):

    if not history:
        raise ValueError("Historical data required")

    lambdas, weights = estimate_demand(history)

    # Expected demand
    predicted_mean = np.dot(lambdas, weights)

    # Predictive cumulative distribution
    def predictive_cdf(k):
        return np.dot(weights, poisson.cdf(k, lambdas))

    # Smallest k with P(demand <= k) >= probability
    def quantile(probability):

        low = 0
        high = max(10, int(predicted_mean * 2))

        while predictive_cdf(high) < probability:
            high *= 2

        while low < high:
            mid = (low + high) // 2
            if predictive_cdf(mid) >= probability:
                high = mid
            else:
                low = mid + 1

        return low

    # 80% prediction interval
    lower = quantile(0.10)
    upper = quantile(0.90)

    # Profit-maximizing quantity (newsvendor model), using the latest
    # cost and price. Making one more unit earns (price - cost) if it sells
    # and loses cost if it's wasted, so the optimal quantity is the
    # demand quantile at (price - cost) / price.
    latest = history[-1]
    if latest.price > latest.cost and latest.price > 0:
        critical_ratio = (latest.price - latest.cost) / latest.price
        recommended = quantile(critical_ratio)
    else:
        critical_ratio = 0.0
        recommended = 0  # selling at a loss: don't produce

    return {
        "predicted_demand": round(float(predicted_mean), 1),
        "prediction_interval_80": [lower, upper],
        "recommended_production": recommended,
        "critical_ratio": round(critical_ratio, 3),
    }
