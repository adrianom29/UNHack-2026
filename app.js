const results = document.getElementById("results"),
  error = document.getElementById("error"),
  download = document.getElementById("download"),
  riskPreference = document.getElementById("risk-preference");
let latest = null;
const fmt = (n) =>
  n.toLocaleString("en-CA", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
const whole = (n) => Math.round(n).toLocaleString("en-CA");
const escapeHTML = (s) =>
  String(s).replace(
    /[&<>"']/g,
    (ch) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        ch
      ],
  );
// Every SmartPrep route answers with JSON; anything else means the page is
// being served by something other than an up-to-date SmartPrep server.
async function readJSON(response) {
  try {
    return await response.json();
  } catch {
    throw Error(
      response.status === 404 || response.status === 405
        ? "The server doesn't recognize this request. It may be an older copy still running, or Live Server. Stop it (Ctrl+C), run `py smartprep.py --serve` again, and open http://127.0.0.1:8765/."
        : "The SmartPrep server did not respond. Run `py smartprep.py --serve` and open http://127.0.0.1:8765/.",
    );
  }
}

// A percentage card. `pct` is null when there is nothing to compare with.
function card(label, pct, better, worse, detail) {
  let value, note;
  if (pct === null) {
    value = "—";
    note = detail;
  } else if (Math.abs(pct) < 0.05) {
    value = "No change";
    note = detail;
  } else {
    value = `${Math.abs(pct).toFixed(1)}%`;
    note = `${pct > 0 ? better : worse} · ${detail}`;
  }
  return `<div class="card"><span>${label}</span><strong>${value}</strong><small>${note}</small></div>`;
}

function planRow(i) {
  const notes = [];
  if (i.provisional)
    notes.push(`provisional: ${i.days_used} of ${latest.min_days} days recorded`);
  if (i.all_sold_out)
    notes.push(
      "sold out every day, so real demand is unknown; try making a little more",
    );
  else if (i.sellouts_adjusted)
    notes.push(
      `adjusted for ${i.sellouts_adjusted} sold-out day${i.sellouts_adjusted === 1 ? "" : "s"}`,
    );
  const note = notes.length
    ? `<br /><small class="note">${notes.join(" · ")}</small>`
    : "";
  return `<tr><td>${escapeHTML(i.item)}${note}</td><td><strong>${i.recommended_quantity}</strong></td><td>${whole(i.predicted_demand)}</td><td>${i.last_quantity}</td></tr>`;
}

async function showPlan() {
  error.textContent = "";
  download.disabled = true;
  try {
    const response = await fetch(
      "/plan?service_level=" + encodeURIComponent(riskPreference.value),
    );
    const r = await readJSON(response);
    if (!response.ok) throw Error(r.error);
    latest = r;
    const t = r.totals,
      checked = t.source === "backtest";
    // Backtest totals cover the checked days; estimates are per day.
    const period = checked ? `over the last ${t.checked_days} days` : "per day";
    let html = "";
    if (r.items.length) {
      const target = new Date(r.items[0].target_day + "T00:00");
      html +=
        `<p>Plan for <strong>${target.toLocaleDateString("en-CA", { weekday: "long", month: "long", day: "numeric" })}</strong></p>` +
        `<div class="cards">` +
        card(
          "Predicted waste reduction",
          t.waste_reduction_pct,
          "less waste",
          "more waste",
          t.previous_waste > 0
            ? `${whole(t.predicted_waste)} vs. ${whole(t.previous_waste)} items wasted ${period}`
            : "no waste recorded so far",
        ) +
        card(
          "Predicted profit increase",
          t.profit_increase_pct,
          "more profit",
          "less profit",
          t.previous_profit > 0
            ? `CAD ${fmt(t.predicted_profit)} vs. CAD ${fmt(t.previous_profit)} ${period}`
            : `CAD ${fmt(t.predicted_profit)} expected ${period}`,
        ) +
        `<div class="card"><span>Forecast accuracy</span><strong>${t.forecast_error_pct === null ? "Not checked yet" : `±${Math.round(t.forecast_error_pct)}%`}</strong><small>${t.forecast_error_pct === null ? `needs items with more than ${r.min_days} days of records` : "typical miss per item per day, on days that did not sell out"}</small></div>` +
        `</div>` +
        `<p class="${checked ? "" : "note"}">${
          checked
            ? `Checked: SmartPrep replayed your last ${t.checked_days} days for ${t.checked_items} item(s), planning each day only from the days before it, and compared that with what you actually made and sold.`
            : `Estimate only: these numbers will be checked against your real results once items have more than ${r.min_days} days of records.`
        }</p>` +
        `<div style="overflow-x: auto"><table><thead><tr><th>Item</th><th>Make tomorrow</th><th>Expected to sell</th><th>Made last time</th></tr></thead><tbody>` +
        r.items.map(planRow).join("") +
        `</tbody></table></div>`;
    }
    if (r.waiting.length) {
      html +=
        `<p class="note">Not planned yet:</p><ul class="note">` +
        r.waiting
          .map((w) => `<li>${escapeHTML(w.item)}: ${escapeHTML(w.reason)}</li>`)
          .join("") +
        `</ul>`;
    }
    results.innerHTML =
      html ||
      "Add items to your menu and save at least two days of records to get a plan.";
    download.disabled = !r.items.length;
  } catch (exc) {
    latest = null;
    results.textContent = "No plan available yet.";
    error.textContent = exc.message;
  }
}

riskPreference.addEventListener("change", showPlan);
download.addEventListener("click", () => {
  if (!latest) return;
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(latest, null, 2)], {
      type: "application/json",
    }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = "smartprep-plan.json";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
