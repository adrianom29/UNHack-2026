# SmartPrep — runnable merchant demo

A local, English-language meal-preparation decision tool for UNHack. Vendors maintain a regular menu, enter daily preparation and sales on one page, and compare their current plan with a newsvendor recommendation. This repository contains the runnable merchant demo.

## Run

Requires **Python 3.10+**. No third-party Python packages are required.

From the repository root:

```sh
python smartprep.py --serve
```

Open **http://127.0.0.1:8765/**. Keep the terminal running. Press Ctrl+C to stop. On Windows, use `py` instead of `python` if needed. To use another port, add `--port 8766` and open that port. Do not open `index.html` directly: it needs the Python service.

The server listens on the local computer only. A GitHub repository or GitHub Pages URL does not run this Python application. Every teammate runs their own local copy and database.

## Merchant workflow

1. **Manage menu:** add each product once with its selling price and cost to make one. Change a price or cost right in the menu table; it saves when you leave the box. Hide a product to take it off the daily sheet and the plan while keeping its history, or Delete it to remove the product and all of its past records.
2. **Daily entry:** the date defaults to today; regular products appear automatically. For each item fill Made and Sold, then click Save day once. Leave both blank to skip a product. Waste is calculated as made − sold.
3. **Tomorrow's plan:** lists how many of each menu item to make tomorrow (items need a price and at least two saved days), with the predicted waste reduction and profit increase for all planned items combined, as percentages of your actual averages so far. Choose how much you want to avoid running out; the plan updates immediately.
4. **Past records:** one row per day with that day's totals; click a day to see each item recorded on it, with an Edit button per item and a Delete day button that removes the whole day. A CSV export of all records is below the list.

No business records are shipped with the source. Default calculator inputs are illustrative. The app creates `smartprep.sqlite3` beside the program and retains it across restarts. This is one local business workspace, not a multi-user or synchronized service. Stop the server before copying the database for backup. Do not commit business databases or exported records to GitHub.

## Model and limitations

Demand is approximated by `D=max(0,X)` with `X~Normal(mu,sigma²)`; preparation `Q` is a nonnegative integer. Profit is `p*min(Q,D)-c*Q`. With `p>c>0`, the continuous optimum is `max(0,mu+sigma*Phi_inverse(1-c/p))`. The solver compares neighboring integers by expected profit instead of simply rounding.

For coverage target `alpha`, require `P(D<=Q)>=alpha`. The minimum feasible integer is `max(0,ceil(mu+sigma*Phi_inverse(alpha)))`; choose the larger of this minimum and the unconstrained integer optimum. Zero standard deviation is handled directly. Price at or below cost gives zero preparation without a service constraint, but meeting a service target may incur a loss. Positive price with zero cost and unbounded stochastic demand has no finite profit-maximizing quantity and produces an explanatory error.

The merchant never enters mu or sigma; `demand.py` estimates them per item for the target day (tomorrow) from the last 180 days of records:

- **Sell-outs.** A day where everything made was sold only shows that demand was at least that much. These days are treated as censored observations and the normal distribution is fitted by maximum likelihood (a Tobit model, solved with the EM algorithm), instead of averaging sales.
- **Recency.** Each day's weight halves every 21 days (`HALF_LIFE_DAYS`).
- **Weekdays.** Each weekday gets its own level, blended with the overall level as if that level had been seen on 3 extra days of the weekday (`WEEKDAY_SHRINK`, tuned with `simulate.py`).
- **Small samples.** The spread is corrected for short histories and never drops below 0.5 items. With fewer than 7 usable days a plan is marked provisional; if an item sold out every day the plan is flagged, because the data cannot show how high demand goes.

Price and cost come from the menu. Zero-preparation days are excluded; missing dates are not interpreted as zero sales.

**Checking accuracy (backtest).** Once an item has more than 7 days, each of its last 28 days is replayed: SmartPrep plans that day using only earlier days and the plan is compared with what was actually made and sold. Combined waste reduction, profit increase and the typical forecast miss shown in the app come from this check; before any item qualifies, the app shows the model's own estimate and labels it as such. On sold-out days true demand is unknown, so if the plan would have made more, demand is taken as the expected amount above the sell-out point under that day's forecast. Past profit is valued at current menu prices. The forecast miss compares with actual sales, so it includes ordinary day-to-day randomness that no forecast can remove.

Stockout probability is the chance that a day's demand exceeds supply, not the share of customers unserved. Coverage targets are model estimates, not service guarantees. Profit maximization may increase waste or stockout risk relative to the baseline.

The model assumes one item, one day, one preparation decision, zero leftover salvage value, and no capacity or substitution constraints. Reported profit excludes fixed expenses. Historical prepared-minus-sold is labeled unsold; it is not measured food waste. Default results are not evidence of real savings.

### Accuracy in simulation

`py simulate.py` invents 100 businesses with known demand (base level, weekday pattern, slow trend and skewed day-to-day noise, so not the bell curve the model assumes), lets each owner run by habit for 14 days, then compares 36 days of: the owner's habit, the previous method (plain average and spread of sales), the current method, and an oracle that knows the true demand distribution. Results with `--days 50` and the default seed (average across runs; 5th–95th percentile in brackets):

| | Previous method | Current method | Oracle |
|---|---:|---:|---:|
| Forecast error vs true mean demand | 17.7% (11–25) | 11.4% (7–16) | 0% |
| Profit change vs owner's habit | +2.1% (−7 to +21) | +6.4% (−2 to +26) | +9.3% (−2 to +31) |
| Share of the oracle's gain captured (median) | −16% | 57% | 100% |
| Days that ran out | 58.5% | 45.2% | 41.3% |

The previous method under-forecast after sell-outs, made less, sold out more, and learned even lower demand: a spiral the sell-out adjustment removes. Waste changes vary widely by business (the most profitable plan makes *more* than an owner who habitually under-produces), so they are not summarized here; run the script to see them.

Honesty check: on the same businesses, the in-app backtest (run on the owner's own records) reported +7.2% profit against +6.4% actually achieved, and 18.1% less waste against 13.4% actually achieved. Profit figures are close; the waste figure reads somewhat optimistic.

By default the script runs 28 days (14 by habit, 14 compared) and ends with five pass criteria, fixed in advance: the new method has lower forecast error than the old one, raises profit over the owner's habit, makes more profit than the old method, runs out on fewer days than the old method, and the app's backtest profit figure is within 3 percentage points of reality. It exits with status 1 if any fails. With 28 days all five passed for seeds 2026, 1, 42, 777, 5000 and 90210 (profit +4.3% to +6.4% over habit; backtest profit gap +0.4 to +0.7 points).

Options: `--runs`, `--days`, `--warmup`, `--seed`, `--service-level`.

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
python -m unittest -v test_smartprep.py test_records.py test_demand.py
```

Tests cover demand estimation (recovering demand from capped sales, weekday levels, recency, all-sold-out handling), the backtest, global integer optima, service constraints, boundary inputs, independent simulation checks, persistent records, menu prices, deleting items and records, combined plan totals, upgrading older databases, atomic daily saves, fixed-menu hide/restore, and the plan HTTP interface. Frontend plan-display checks require Node.js only: `node test_demo.js`.

## Files and development scope

- `smartprep.py`: optimizer, plan and backtest, CLI, and local HTTP server.
- `demand.py`: demand estimation (sell-outs, weekdays, recency).
- `records.py`: SQLite records, menu, and sales statistics.
- `simulate.py`: accuracy simulation on synthetic businesses.
- `index.html`, `styles.css`, `app.js`, `records.js`: interactive merchant interface.
- `test_*.py`, `test_demo.js`: validation.

This upload is the currently runnable demo. Weather/calendar integrations, holidays, recipes, shopping lists and expiry-aware inventory are not included in this version.

## 中文快速启动

下载并解压仓库，在 `smartprep-demo` 文件夹打开终端，执行 `python smartprep.py --serve`，然后用浏览器访问 `http://127.0.0.1:8765/`。不要直接双击 HTML。保持终端运行；每台电脑的数据独立保存，不会同步到同学的电脑。
