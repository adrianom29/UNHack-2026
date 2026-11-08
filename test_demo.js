// Frontend check for the plan display: node test_demo.js (no server needed).
const fs = require("fs"),
  vm = require("vm"),
  assert = require("assert");
const element = () => ({
  innerHTML: "",
  textContent: "",
  value: "0",
  disabled: false,
  addEventListener() {},
});
const elements = Object.fromEntries(
  ["results", "error", "download", "risk-preference"].map((k) => [
    k,
    element(),
  ]),
);
let reply,
  requested = [];
const context = {
  document: { getElementById: (k) => elements[k] },
  fetch: async (url) => {
    requested.push(url);
    return {
      ok: reply.ok,
      status: reply.status || 200,
      json: async () => {
        if (reply.body === undefined) throw SyntaxError("Unexpected token <");
        return reply.body;
      },
    };
  },
  console,
  Blob,
  URL,
  setTimeout,
};
vm.createContext(context);
vm.runInContext(fs.readFileSync("app.js", "utf8"), context);
const item = (name, make, demand, last, extra = {}) => ({
  item: name,
  target_day: "2026-11-08",
  recommended_quantity: make,
  predicted_demand: demand,
  last_quantity: last,
  provisional: false,
  days_used: 12,
  sellouts_adjusted: 0,
  all_sold_out: false,
  ...extra,
});
const show = () => vm.runInContext("showPlan()", context);
(async () => {
  reply = {
    ok: true,
    body: {
      items: [
        item("Soup <hot>", 83, 80.4, 100, { sellouts_adjusted: 1 }),
        item("Bread", 36, 32, 40, { provisional: true, days_used: 3 }),
        item("Pie", 12, 10, 10, { all_sold_out: true }),
      ],
      waiting: [{ item: "Cake", reason: "Save at least two days" }],
      min_days: 7,
      totals: {
        source: "backtest",
        checked_items: 2,
        checked_days: 28,
        forecast_error_pct: 12.4,
        previous_waste: 28,
        predicted_waste: 9.8,
        previous_profit: 520,
        predicted_profit: 598,
        waste_reduction_pct: 65,
        profit_increase_pct: 15,
      },
    },
  };
  elements["risk-preference"].value = "0.9";
  await show();
  const html = elements.results.innerHTML;
  assert(requested[0].endsWith("/plan?service_level=0.9"));
  assert(html.includes("65.0%") && html.includes("less waste"), "waste %");
  assert(html.includes("15.0%") && html.includes("more profit"), "profit %");
  assert(html.includes("Plan for <strong>Sunday, November 8"));
  assert(html.includes("10 vs. 28 items wasted over the last 28 days"));
  assert(html.includes("±12%"));
  assert(html.includes("Checked: SmartPrep replayed your last 28 days"));
  assert(html.includes("Soup &lt;hot&gt;"), "item name is escaped");
  assert(html.includes("<strong>83</strong>") && html.includes("<strong>36</strong>"));
  assert(html.includes("adjusted for 1 sold-out day"));
  assert(html.includes("provisional: 3 of 7 days recorded"));
  assert(html.includes("sold out every day"));
  assert(html.includes("Cake: Save at least two days"));
  assert(!/mean|std|σ|μ/i.test(html), "no statistics jargon");
  assert(!elements.download.disabled);

  Object.assign(reply.body.totals, {
    source: "estimate",
    forecast_error_pct: null,
    profit_increase_pct: -4,
    previous_profit: -10,
    waste_reduction_pct: null,
    previous_waste: 0,
  });
  await show();
  assert(elements.results.innerHTML.includes("4.0%"));
  assert(elements.results.innerHTML.includes("less profit"));
  assert(elements.results.innerHTML.includes("no waste recorded so far"));
  assert(elements.results.innerHTML.includes("Estimate only"));
  assert(elements.results.innerHTML.includes("Not checked yet"));

  reply = {
    ok: true,
    body: { items: [], waiting: [], totals: {} },
  };
  await show();
  assert(elements.results.innerHTML.includes("Add items to your menu"));
  assert(elements.download.disabled);

  reply = { ok: false, body: { error: "Service level must be" } };
  await show();
  assert(elements.error.textContent.includes("Service level"));

  // An outdated server answers /plan with an HTML 404 page.
  reply = { ok: false, status: 404 };
  await show();
  assert(elements.error.textContent.includes("older copy still running"));
  console.log(
    "PASS: combined plan, percentages, escaping, waiting items, error states",
  );
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
