"""Demand estimation from daily records (standard library only).

A plain average of units sold has three problems, and each is handled here:

1. Sell-outs. When everything made was sold, demand was *at least* that
   much, not exactly that much. Those days are treated as censored
   observations and a normal distribution is fitted by maximum likelihood
   (a Tobit model), using the EM algorithm.
2. Recency. Recent days count more: a day's weight halves every
   HALF_LIFE_DAYS days.
3. Weekdays. Each weekday gets its own demand level, pulled toward the
   overall level until that weekday has enough history of its own.
"""

import math
from datetime import date
from statistics import NormalDist

NORMAL = NormalDist()
HALF_LIFE_DAYS = 21
# Each weekday's level is blended with the overall level as if the overall
# level had been seen on this many extra days of that weekday.
WEEKDAY_SHRINK = 3
# Sales are whole items, so demand is never treated as perfectly certain.
MIN_SIGMA = 0.5
# Fewer usable days than this and a plan is marked provisional.
MIN_DAYS = 7
# Older days have negligible weight; ignoring them keeps the fit fast.
MAX_HISTORY_DAYS = 180


def _inverse_mills(z):
    """phi(z) / (1 - Phi(z)): expected overshoot above a sell-out point."""
    if z > 8:
        # 1 - Phi(z) underflows here; use the asymptotic expansion.
        return z + 1 / z - 2 / z**3
    return NORMAL.pdf(z) / (1 - NORMAL.cdf(z))


def expected_above(mu, sigma, floor):
    """Expected demand on a day that sold out at `floor`: E[D | D >= floor]."""
    return max(floor, mu + sigma * _inverse_mills((floor - mu) / sigma))


def censored_fit(values, censored, weights, iterations=200, tol=1e-7):
    """Weighted normal fit where censored[i] means demand was >= values[i].

    Returns (mu, sigma, filled): filled[i] is the expected demand on day i
    (the value itself on days that did not sell out).
    """
    total = sum(weights)
    mu = sum(w * x for w, x in zip(weights, values)) / total
    sigma = max(
        math.sqrt(sum(w * (x - mu) ** 2 for w, x in zip(weights, values)) / total),
        MIN_SIGMA,
    )
    filled = list(values)
    for _ in range(iterations):
        s1 = s2 = 0.0
        for i, (x, cut, w) in enumerate(zip(values, censored, weights)):
            if cut:
                lam = _inverse_mills((x - mu) / sigma)
                e1 = mu + sigma * lam
                e2 = mu * mu + sigma * sigma + sigma * (x + mu) * lam
            else:
                e1, e2 = x, x * x
            filled[i] = e1
            s1 += w * e1
            s2 += w * e2
        new_mu = s1 / total
        new_sigma = max(math.sqrt(max(s2 / total - new_mu**2, 0.0)), MIN_SIGMA)
        done = abs(new_mu - mu) <= tol * (1 + abs(mu)) and abs(
            new_sigma - sigma
        ) <= tol * (1 + sigma)
        mu, sigma = new_mu, new_sigma
        if done:
            break
    # Maximum likelihood divides by the total weight, which understates the
    # spread on short histories; correct with the effective sample size.
    n_eff = total**2 / sum(w * w for w in weights)
    if n_eff > 1:
        sigma = max(sigma * math.sqrt(n_eff / (n_eff - 1)), MIN_SIGMA)
    return mu, sigma, filled


def _as_date(day):
    return day if isinstance(day, date) else date.fromisoformat(day)


def estimate(rows, target):
    """Demand forecast for `target` from rows of {day, prepared, sold}.

    Only days with something made and dated before `target` (within
    MAX_HISTORY_DAYS) are used. Returns None with fewer than two such days.
    """
    target = _as_date(target)
    usable = []
    for r in rows:
        day = _as_date(r["day"])
        if r["prepared"] > 0 and 0 < (target - day).days <= MAX_HISTORY_DAYS:
            usable.append((day, r["prepared"], r["sold"]))
    if len(usable) < 2:
        return None
    weights = [0.5 ** ((target - d).days / HALF_LIFE_DAYS) for d, _, _ in usable]
    sold = [s for _, _, s in usable]
    censored = [s >= p for _, p, s in usable]
    sellouts = sum(censored)
    result = dict(days=len(usable), sellouts=sellouts, all_sold_out=False)

    if sellouts == len(usable):
        # Every day sold out: there is no upper reference, so the fit cannot
        # say how high demand goes. Fall back to sales, flagged as a floor.
        mu, sigma, _ = censored_fit(sold, [False] * len(sold), weights)
        return dict(result, mu=mu, sigma=sigma, weekday_factor=1.0, all_sold_out=True)

    # Pass 1: overall fit, which also fills in likely demand on sell-out days.
    _, _, filled = censored_fit(sold, censored, weights)
    overall = sum(w * f for w, f in zip(weights, filled)) / sum(weights)

    # Weekday levels from the filled-in demand, shrunk toward the overall level.
    factors = [1.0] * 7
    if overall > 0:
        for wd in range(7):
            idx = [i for i, (d, _, _) in enumerate(usable) if d.weekday() == wd]
            if idx:
                w = sum(weights[i] for i in idx)
                level = sum(weights[i] * filled[i] for i in idx) / w
                factors[wd] = (len(idx) * level + WEEKDAY_SHRINK * overall) / (
                    len(idx) + WEEKDAY_SHRINK
                ) / overall
                # Keep a weekday that has sold nothing from zeroing the scale.
                factors[wd] = max(factors[wd], 0.05)

    # Pass 2: refit on weekday-adjusted demand (sell-out points adjusted too),
    # then scale back to the target's weekday.
    adjusted = [s / factors[d.weekday()] for (d, _, _), s in zip(usable, sold)]
    mu, sigma, _ = censored_fit(adjusted, censored, weights)
    f = factors[target.weekday()]
    return dict(result, mu=mu * f, sigma=sigma * f, weekday_factor=f)
