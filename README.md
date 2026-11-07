# SmartPrep — runnable merchant demo

A local, English-language meal-preparation decision tool for UNHack. Vendors maintain a regular menu, enter daily preparation and sales on one page, and compare their current plan with a newsvendor recommendation. This repository contains the runnable merchant demo.

## Run

Requires **Python 3.10+**. No third-party Python packages are required.

From the repository root:

```sh
python smartprep.py --serve
```

Open **http://127.0.0.1:8765/**. Keep the terminal running. Press Ctrl+C to stop. On Windows, use `py` instead of `python` if needed. To use another port, add `--port 8766` and open that port. Do not open `demo.html` directly: it needs the Python service.

The server listens on the local computer only. A GitHub repository or GitHub Pages URL does not run this Python application. Every teammate runs their own local copy and database.

## Merchant workflow

1. **Manage regular items:** add products once. Hide and restore products without deleting history.
2. **Daily entry:** the date defaults to today; regular products appear automatically. Fill Prepared and Sold, then click Save day once. Leave both fields blank to skip a product. Existing records for that date can be updated; notes are preserved.
3. **History:** select a product. At least two days with positive preparation are needed to estimate average sales and sample variation. Click Use these records in the model. Price and unit cost remain manual estimates.
4. **Plan:** choose profit first or at least 80%, 90%, or 95% modeled daily demand coverage, then calculate. Compare profit, waste, and stockout probability; export results as JSON or daily records as CSV.

No business records are shipped with the source. Default calculator inputs are illustrative. The app creates `smartprep.sqlite3` beside the program and retains it across restarts. This is one local business workspace, not a multi-user or synchronized service. Stop the server before copying the database for backup. Do not commit business databases or exported records to GitHub.

## Model and limitations

Demand is approximated by `D=max(0,X)` with `X~Normal(mu,sigma²)`; preparation `Q` is a nonnegative integer. Profit is `p*min(Q,D)-c*Q`. With `p>c>0`, the continuous optimum is `max(0,mu+sigma*Phi_inverse(1-c/p))`. The solver compares neighboring integers by expected profit instead of simply rounding.

For coverage target `alpha`, require `P(D<=Q)>=alpha`. The minimum feasible integer is `max(0,ceil(mu+sigma*Phi_inverse(alpha)))`; choose the larger of this minimum and the unconstrained integer optimum. Zero standard deviation is handled directly. Price at or below cost gives zero preparation without a service constraint, but meeting a service target may incur a loss. Positive price with zero cost and unbounded stochastic demand has no finite profit-maximizing quantity and produces an explanatory error.

The inputs mu and sigma describe the normal distribution before clipping, not the exact moments afterward. History supplies sales moments as approximate parameters, without distribution fitting. Sales can underestimate demand when a product sells out. Possible stockout days are flagged but lost sales are not inferred. Zero-preparation days are excluded; missing dates are not interpreted as zero sales. More data does not guarantee accuracy.

Stockout probability is the chance that a day's demand exceeds supply, not the share of customers unserved. Coverage targets are model estimates, not service guarantees. Profit maximization may increase waste or stockout risk relative to the baseline.

The model assumes one item, one day, one preparation decision, zero leftover salvage value, and no capacity or substitution constraints. Reported profit excludes fixed expenses. Historical prepared-minus-sold is labeled unsold; it is not measured food waste. Default results are not evidence of real savings.

### Default example

Price CAD 12, cost CAD 5, demand parameters 80/15, baseline 100 portions:

| Preference | Recommended portions |
|---|---:|
| Profit first | 83 |
| At least 80% daily demand coverage | 93 |
| At least 90% daily demand coverage | 100 |
| At least 95% daily demand coverage | 105 |

## Tests

Run from the repository folder:

```sh
python -m unittest -v test_smartprep.py test_records.py
```

Tests cover global integer optima, service constraints, boundary inputs, independent simulation checks, persistent records, atomic daily saves, fixed-menu hide/restore, and the calculation HTTP interface. Optional frontend logic checks require Node.js and a running service: `node test_demo.js`.

## Files and development scope

- `smartprep.py`: optimizer, CLI, and local HTTP server.
- `records.py`: SQLite records, regular menu, and sales statistics.
- `demo.html`, `records.js`: interactive merchant interface.
- `test_*.py`, `test_demo.js`: validation.

This upload is the currently runnable demo. Weather/calendar integrations, recipes, shopping lists, expiry-aware inventory, and adaptive forecasting are not included in this version.

## 中文快速启动

下载并解压仓库，在 `smartprep-demo` 文件夹打开终端，执行 `python smartprep.py --serve`，然后用浏览器访问 `http://127.0.0.1:8765/`。不要直接双击 HTML。保持终端运行；每台电脑的数据独立保存，不会同步到同学的电脑。
