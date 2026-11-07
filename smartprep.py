"""SmartPrep: standard-library-only newsvendor model and local interactive demo."""

import argparse
import json
import math
from statistics import NormalDist
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
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


def solve(p=12, c=5, mu=80, sigma=15, baseline=100, service_level=0):
    validate(p, c, mu, sigma, baseline)
    if (
        isinstance(service_level, bool)
        or not isinstance(service_level, (int, float))
        or not math.isfinite(service_level)
        or not 0 <= service_level < 1
    ):
        raise ValueError(
            "Service level must be between 0 (profit priority) and less than 1."
        )
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
    profit_only = metrics(q, p, c, mu, sigma)
    minimum = 0
    if service_level > 0:
        minimum = max(
            0,
            math.ceil(mu if sigma == 0 else mu + sigma * NORMAL.inv_cdf(service_level)),
        )
        q = max(q, minimum)
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
        if self.path not in ("/calculate", "/records", "/records/batch", "/items"):
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length < 131072:
                raise ValueError("Request is too large or empty")
            args = json.loads(self.rfile.read(length))
            if self.path == "/calculate":
                result = solve(**args)
            elif self.path == "/items":
                result = records.save_item(**args)
            elif self.path == "/records/batch":
                result = records.save_batch(**args)
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
