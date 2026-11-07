const form = document.getElementById("inputs"),
  results = document.getElementById("results"),
  error = document.getElementById("error"),
  plot = document.getElementById("plot"),
  download = document.getElementById("download");
let latest,
  historySource = null;
const fmt = (n) =>
  n.toLocaleString("en-CA", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
async function calculate(e) {
  if (e) e.preventDefault();
  error.textContent = "";
  download.disabled = true;
  try {
    const inputs = Object.fromEntries(
      [...new FormData(form)].map(([k, v]) => [k, Number(v)]),
    );
    const response = await fetch("/calculate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(inputs),
    });
    const r = await response.json();
    if (!response.ok) throw Error(r.error);
    latest = r;
    if (historySource) latest.history_source = historySource;
    const a = r.baseline,
      b = r.optimal;
    results.innerHTML = `<span>${r.inputs.service_level ? "Best expected profit within your service target" : "Profit-maximizing preparation quantity"}</span><div class="hero">${b.quantity} portions</div><p>${b.quantity - a.quantity >= 0 ? "+" : ""}${b.quantity - a.quantity} portions compared with your current plan.</p><table><thead><tr><th>Daily metric</th><th>Current</th><th>Recommended</th></tr></thead><tbody>${[
      ["Quantity (portions)", a.quantity, b.quantity],
      ["Expected profit (CAD)", fmt(a.profit), fmt(b.profit)],
      ["Expected waste (portions)", fmt(a.waste), fmt(b.waste)],
      [
        "Stockout probability",
        fmt(a.stockout_probability * 100) + "%",
        fmt(b.stockout_probability * 100) + "%",
      ],
      [
        "Expected unmet demand (portions)",
        fmt(a.unmet_demand),
        fmt(b.unmet_demand),
      ],
    ]
      .map((row) => "<tr>" + row.map((x) => `<td>${x}</td>`).join("") + "</tr>")
      .join(
        "",
      )}</tbody></table><p>Recommended − current: profit ${fmt(r.delta.profit)} CAD; waste ${fmt(r.delta.waste)} portions; stockout probability ${fmt(100 * r.delta.stockout_probability)} percentage points.</p><p>Expected demand after clipping: ${fmt(r.effective_mean)} portions.</p>`;
    if (r.inputs.service_level) {
      results.innerHTML += `<p>Target: at least ${fmt(100 * r.inputs.service_level)}% of days covered. Estimated coverage: ${fmt(100 * (1 - b.stockout_probability))}%.</p><p>Compared with profit-first (${r.profit_only.quantity} portions): ${b.quantity - r.profit_only.quantity} extra portions, CAD ${fmt(r.profit_only.profit - b.profit)} less expected profit, and ${fmt(b.waste - r.profit_only.waste)} more expected leftover portions.</p>`;
    }
    const points = r.curve,
      xmax = Math.max(...points.map((d) => d.quantity)),
      lo = Math.min(0, ...points.map((d) => d.profit)),
      hi = Math.max(1, ...points.map((d) => d.profit)),
      x = (q) => 65 + (q / xmax) * 550,
      y = (v) => 210 - ((v - lo) / (hi - lo)) * 175;
    plot.innerHTML = `<line x1="65" y1="210" x2="615" y2="210" stroke="#9ab3a6"/><text x="10" y="24" font-size="12">CAD</text><text x="0" y="45" font-size="12">${fmt(hi)}</text><text x="0" y="210" font-size="12">${fmt(lo)}</text><polyline fill="none" stroke="#176c4e" stroke-width="3" points="${points.map((d) => x(d.quantity) + "," + y(d.profit)).join(" ")}"/>${[
      [b, "#176c4e", "Recommended"],
      [a, "#a76c22", "Current"],
    ]
      .map(
        ([d, col, label], i) =>
          `<line x1="${x(d.quantity)}" x2="${x(d.quantity)}" y1="35" y2="210" stroke="${col}" stroke-dasharray="4 4"/><text x="${i ? 420 : 65}" y="${i ? 18 : 18}" fill="${col}" font-size="12">${label} ${d.quantity} portions</text>`,
      )
      .join(
        "",
      )}<text x="65" y="235" font-size="12">0</text><text x="530" y="235" font-size="12">${xmax} portions</text>`;
    download.disabled = false;
  } catch (exc) {
    error.textContent = exc.message;
    results.textContent = "Unable to calculate. Please check your inputs.";
    plot.innerHTML = "";
    latest = null;
  }
}
form.addEventListener("submit", calculate);
download.addEventListener("click", () => {
  if (!latest) return;
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(latest, null, 2)], {
      type: "application/json",
    }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = "smartprep-result.json";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
calculate();
