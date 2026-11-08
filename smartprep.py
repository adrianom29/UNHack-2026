"""SmartPrep: standard-library-only newsvendor model and local interactive demo."""

import argparse
import json
import math
from datetime import date, timedelta
from statistics import NormalDist
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import demand
import records

NORMAL = NormalDist()
LIMIT = 1_000_000


def validate(p, c, mu, sigma, baseline):
    for name, value in zip(
        ("price", "cost", "mean", "std", "baseline"), (p, c, mu, sigma, baseline)
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not 0 <= value <= LIMIT
        ):
            raise ValueError(f"{name} must be a finite number between 0 and {LIMIT}")
    if int(baseline) != baseline:
        raise ValueError("Current preparation quantity must be an integer")


def tail(z):
    return 0.5 * math.erfc(z / math.sqrt(2))


def loss(q, mu, sigma):
    """E[(X-q)+], X~Normal(mu,sigma); q>=0 also equals E[(D-q)+]."""
    if sigma == 0:
        return max(mu - q, 0.0)
    z = (q - mu) / sigma
    return max(
        0.0, sigma * math.exp(-z * z / 2) / math.sqrt(2 * math.pi) + (mu - q) * tail(z)
    )


def metrics(q, p, c, mu, sigma):
    mean = loss(0, mu, sigma)
    shortage = loss(q, mu, sigma)
    sales = min(float(q), max(0.0, mean - shortage))
    return dict(
        quantity=q,
        profit=p * sales - c * q,
        waste=max(0.0, q - sales),
        stockout_probability=float(mu > q) if sigma == 0 else tail((q - mu) / sigma),
        sales=sales,
        unmet_demand=shortage,
    )


def validate_service_level(service_level):
    if (
        isinstance(service_level, bool)
        or not isinstance(service_level, (int, float))
        or not math.isfinite(service_level)
        or not 0 <= service_level < 1
    ):
        raise ValueError(
            "Service level must be between 0 (profit priority) and less than 1."
        )


def best_quantity(p, c, mu, sigma, service_level=0):
    """Returns (quantity, profit-only quantity, service-level minimum)."""
    if p > 0 and c == 0 and sigma > 0:
        raise ValueError(
            "Zero cost with an unbounded normal demand tail: no finite profit-maximizing quantity exists. Enter a positive cost."
        )
    if p <= c:
        q = 0
    else:
        continuous = mu if sigma == 0 else max(0.0, mu - sigma * NORMAL.inv_cdf(c / p))
        if not math.isfinite(continuous):
            raise ValueError(
                "The parameter ratio is too extreme. Use a reasonable price and cost."
            )
        candidates = sorted(
            {0, max(0, math.floor(continuous)), max(0, math.ceil(continuous))}
        )
        # Sorted order makes exact profit ties choose the smaller quantity.
        q = max(candidates, key=lambda n: metrics(n, p, c, mu, sigma)["profit"])
    minimum = 0
    if service_level > 0:
        minimum = max(
            0,
            math.ceil(mu if sigma == 0 else mu + sigma * NORMAL.inv_cdf(service_level)),
        )
    return max(q, minimum), q, minimum


def solve(p=12, c=5, mu=80, sigma=15, baseline=100, service_level=0):
    validate(p, c, mu, sigma, baseline)
    validate_service_level(service_level)
    q, profit_q, minimum = best_quantity(p, c, mu, sigma, service_level)
    profit_only = metrics(profit_q, p, c, mu, sigma)
    current = metrics(int(baseline), p, c, mu, sigma)
    optimal = metrics(q, p, c, mu, sigma)
    upper = max(1, baseline, q, mu + 4 * sigma) * 1.15
    quantities = sorted(
        {round(upper * i / 100) for i in range(101)} | {q, int(baseline)}
    )
    return dict(
        inputs=dict(
            price=p,
            cost=c,
            mean=mu,
            std=sigma,
            baseline=baseline,
            service_level=service_level,
        ),
        profit_only=profit_only,
        service_minimum=minimum,
        effective_mean=loss(0, mu, sigma),
        baseline=current,
        optimal=optimal,
        delta={
            k: optimal[k] - current[k]
            for k in ("profit", "waste", "stockout_probability")
        },
        curve=[metrics(n, p, c, mu, sigma) for n in quantities],
    )


BACKTEST_DAYS = 28


def backtest(rows, p, c, service_level=0, window=BACKTEST_DAYS):
    """Replay the last `window` days: plan each one from earlier days only.

    rows are an item's usable records, oldest first. A day is checked only if
    at least demand.MIN_DAYS earlier days exist. On days that sold out, true
    demand is unknown; if the plan would have made more, demand is taken as
    the expected amount above the sell-out point under that day's forecast.
    (Treating it as exactly what sold made the check far too pessimistic in
    simulate.py; this version reads slightly optimistic on waste.)
    """
    result = dict(
        days=[],
        actual_waste=0,
        plan_waste=0,
        actual_profit=0.0,
        plan_profit=0.0,
        error_sum=0.0,
        error_sold=0,
        error_days=0,
    )
    if not rows:
        return result
    last = date.fromisoformat(rows[-1]["day"])
    for i, r in enumerate(rows):
        day = date.fromisoformat(r["day"])
        if i < demand.MIN_DAYS or (last - day).days >= window:
            continue
        est = demand.estimate(rows[:i], day)
        if est is None:
            continue
        q = best_quantity(p, c, est["mu"], est["sigma"], service_level)[0]
        made, sold = r["prepared"], r["sold"]
        likely = sold
        if sold >= made and q > made:
            # Sold out, so demand was at least `made`; use the expected demand
            # above that point under the forecast made from earlier days.
            likely = demand.expected_above(est["mu"], est["sigma"], made)
        plan_sold = min(q, likely)
        result["days"].append(r["day"])
        result["actual_waste"] += made - sold
        result["plan_waste"] += q - plan_sold
        result["actual_profit"] += p * sold - c * made
        result["plan_profit"] += p * plan_sold - c * q
        if sold < made:  # demand known exactly: score the forecast
            result["error_sum"] += abs(est["mu"] - sold)
            result["error_sold"] += sold
            result["error_days"] += 1
    return result


def forecast(item, service_level=0, target=None):
    """Plan `target` (default tomorrow) for one item from its saved records."""
    target = target or date.today() + timedelta(days=1)
    history = records.summary(item)
    if history["count"] < 2:
        raise ValueError(
            f"Save at least two days with prepared and sold for {item} to get a forecast."
        )
    if history["price"] is None:
        raise ValueError(f"Set a price and cost for {item} under Manage menu.")
    rows = records.item_history(item)
    est = demand.estimate(rows, target)
    if est is None:
        raise ValueError(
            f"Save at least two days for {item} within the last {demand.MAX_HISTORY_DAYS} days."
        )
    p, c = history["price"], history["cost"]
    model = solve(p, c, est["mu"], est["sigma"], history["baseline"], service_level)
    best = model["optimal"]
    return dict(
        item=item,
        target_day=target.isoformat(),
        predicted_demand=est["mu"],
        recommended_quantity=best["quantity"],
        last_quantity=history["baseline"],
        predicted_waste=best["waste"],
        predicted_profit=best["profit"],
        previous_waste=history["previous_waste"],
        previous_profit=history["previous_profit"],
        provisional=est["days"] < demand.MIN_DAYS,
        days_used=est["days"],
        sellouts_adjusted=est["sellouts"],
        all_sold_out=est["all_sold_out"],
        history=history,
        backtest=backtest(rows, p, c, service_level),
    )


def percent_change(before, after):
    """Change from before to after as a percentage of before (None if before <= 0)."""
    return 100 * (after - before) / before if before > 0 else None


def plan(service_level=0, target=None):
    """Tomorrow's plan for every item on the menu, with combined totals."""
    # Check up front: per-item errors below are reported as "not planned yet".
    validate_service_level(service_level)
    ready, waiting = [], []
    for entry in records.list_items():
        if not entry["active"]:
            continue
        try:
            ready.append(forecast(entry["item"], service_level, target))
        except ValueError as exc:
            waiting.append(dict(item=entry["item"], reason=str(exc)))
    return dict(
        items=ready,
        waiting=waiting,
        totals=combine(ready),
        min_days=demand.MIN_DAYS,
        backtest_days=BACKTEST_DAYS,
        service_level=service_level,
    )


def combine(ready):
    """Combined waste and profit change for all planned items.

    Uses the backtest (plans checked against days they did not see) when any
    item has checked days; otherwise falls back to the model's own estimate.
    """
    checked = [r["backtest"] for r in ready if r["backtest"]["days"]]
    if checked:
        before_waste = sum(b["actual_waste"] for b in checked)
        after_waste = sum(b["plan_waste"] for b in checked)
        before_profit = sum(b["actual_profit"] for b in checked)
        after_profit = sum(b["plan_profit"] for b in checked)
        error_sold = sum(b["error_sold"] for b in checked)
        totals = dict(
            source="backtest",
            checked_items=len(checked),
            checked_days=len({d for b in checked for d in b["days"]}),
            forecast_error_pct=(
                100 * sum(b["error_sum"] for b in checked) / error_sold
                if error_sold > 0
                else None
            ),
        )
    else:
        before_waste = sum(r["previous_waste"] for r in ready)
        after_waste = sum(r["predicted_waste"] for r in ready)
        before_profit = sum(r["previous_profit"] for r in ready)
        after_profit = sum(r["predicted_profit"] for r in ready)
        totals = dict(source="estimate", checked_items=0, checked_days=0,
                      forecast_error_pct=None)
    totals.update(
        previous_waste=before_waste,
        predicted_waste=after_waste,
        previous_profit=before_profit,
        predicted_profit=after_profit,
        waste_reduction_pct=(
            -percent_change(before_waste, after_waste) if before_waste > 0 else None
        ),
        profit_increase_pct=percent_change(before_profit, after_profit),
    )
    return totals


class Handler(BaseHTTPRequestHandler):
    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, allow_nan=False).encode())

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/items":
            self.send_json({"items": records.list_items()})
            return
        if parsed.path == "/records":
            self.send_json({"records": records.list_records()})
            return
        if parsed.path == "/history-summary":
            self.send_json(records.summary(parse_qs(parsed.query).get("item", [""])[0]))
            return
        if parsed.path == "/plan":
            query = parse_qs(parsed.query)
            try:
                level = float(query.get("service_level", ["0"])[0])
                self.send_json(plan(level))
            except (ValueError, TypeError, OverflowError) as exc:
                self.send_json({"error": str(exc)}, 400)
            return
        static_files = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/index.html": ("index.html", "text/html; charset=utf-8"),
            "/styles.css": ("styles.css", "text/css; charset=utf-8"),
            "/app.js": ("app.js", "text/javascript; charset=utf-8"),
            "/records.js": ("records.js", "text/javascript; charset=utf-8"),
        }
        if parsed.path not in static_files:
            self.send_error(404)
            return
        filename, content_type = static_files[parsed.path]
        data = Path(__file__).with_name(filename).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path not in (
            "/calculate",
            "/records",
            "/records/batch",
            "/records/import",
            "/records/delete-day",
            "/records/delete-all",
            "/items",
            "/items/delete",
        ):
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            # Imported CSV files can hold years of records.
            limit = 4_194_304 if self.path == "/records/import" else 131072
            if not 0 < length < limit:
                raise ValueError("Request is too large or empty")
            args = json.loads(self.rfile.read(length))
            if self.path == "/calculate":
                result = solve(**args)
            elif self.path == "/items":
                result = records.save_item(**args)
            elif self.path == "/items/delete":
                result = records.delete_item(**args)
            elif self.path == "/records/delete-day":
                result = records.delete_day(**args)
            elif self.path == "/records/delete-all":
                result = records.delete_all_records(**args)
            elif self.path == "/records/batch":
                result = records.save_batch(**args)
            elif self.path == "/records/import":
                result = records.import_records(**args)
            else:
                result = records.save_record(**args)
            status = 200
        except (ValueError, TypeError, OverflowError) as exc:
            result = {"error": str(exc)}
            status = 400
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            json.dumps(result, ensure_ascii=False, allow_nan=False).encode()
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--service-level", type=float, default=0)
    for flag, default in [
        ("price", 12),
        ("cost", 5),
        ("mean", 80),
        ("std", 15),
        ("baseline", 100),
    ]:
        parser.add_argument("--" + flag, type=float, default=default)
    args = parser.parse_args()
    if args.serve:
        print(f"SmartPrep: http://127.0.0.1:{args.port} (Ctrl+C to stop)", flush=True)
        try:
            ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
        except KeyboardInterrupt:
            pass
    else:
        try:
            print(
                json.dumps(
                    solve(
                        args.price,
                        args.cost,
                        args.mean,
                        args.std,
                        args.baseline,
                        args.service_level,
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        except ValueError as exc:
            parser.error(str(exc))
