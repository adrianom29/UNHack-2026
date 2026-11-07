# =====================================
import numpy as np
from scipy.stats import gamma, poisson
from scipy.special import logsumexp



def estimate_demand(history):

    # Gamma prior parameters
    alpha = 2.0
    beta = 0.08

    # Possible daily demand rates
    max_prepared = max(
        day["prepared"] for day in history
    )

    upper = max(120, max_prepared * 4)

    for _ in range(6):

        lambdas = np.linspace(
            0.001, upper, 4001
        )

        log_posterior = gamma.logpdf(
            lambdas,
            a=alpha,
            scale=1 / beta
        )

        for day in history:

            prepared = day["prepared"]
            sold = day["sold"]

            if prepared < 1 or sold < 0 or sold > prepared:
                raise ValueError("Invalid daily record")

            if sold < prepared:
                # Demand is observed
                log_posterior += poisson.logpmf(
                    sold, lambdas
                )

            else:
                # Sold out:
                # Actual demand >= prepared
                log_posterior += poisson.logsf(
                    prepared - 1,
                    lambdas
                )

        # Normalize posterior distribution
        weights = np.exp(
            log_posterior - logsumexp(log_posterior)
        )

        if weights[-10:].sum() < 1e-6:
            break

        upper *= 2

    else:
        raise RuntimeError(
            "Posterior range is insufficient"
        )

    return lambdas, weights


# =====================================
# 2. Predict Future Demand
# =====================================

def predict_demand(history):

    if not history:
        raise ValueError("Historical data required")

    lambdas, weights = estimate_demand(history)

    # Expected demand
    predicted_mean = np.dot(
        lambdas, weights
    )

    # Predictive cumulative distribution
    def predictive_cdf(k):

        return np.dot(
            weights,
            poisson.cdf(k, lambdas)
        )

    # Calculate prediction percentiles
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

    return {
        "predicted_demand": round(
            float(predicted_mean), 1
        ),
        "prediction_interval_80": [
            lower, upper
        ]
    }
