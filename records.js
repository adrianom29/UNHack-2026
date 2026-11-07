const byId = (id) => document.getElementById(id);
let dailyRows = [],
  regularItems = [],
  editingId = null,
  historyStats = null;
const recordForm = byId("record-form"),
  itemSelect = byId("history-item");
const today = new Date();
const localDay = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
byId("record-day").value = localDay;
byId("record-day").max = localDay;
async function requestJSON(url, options) {
  const r = await fetch(url, options);
  const data = await r.json();
  if (!r.ok) throw Error(data.error || "Unable to save. Please try again.");
  return data;
}
function invalidateModel(message) {
  latest = null;
  historySource = null;
  download.disabled = true;
  results.textContent = message;
  plot.innerHTML = "";
  byId("data-source").textContent =
    "Model source: records changed. Apply records again or calculate using manual inputs.";
}
function resetRecordForm() {
  editingId = null;
  recordForm.reset();
  byId("record-day").value = localDay;
  byId("save-record").textContent = "Save daily record";
  byId("cancel-edit").hidden = true;
}
function editRow(r) {
  byId("record-details").open = true;
  editingId = r.id;
  for (const key of ["day", "item", "prepared", "sold", "notes"])
    byId("record-" + key).value = r[key];
  byId("save-record").textContent = "Save changes";
  byId("cancel-edit").hidden = false;
  byId("record-message").textContent =
    "Editing an existing record. Save changes to update it.";
  byId("record-day").focus();
}
async function showHistory() {
  const item = itemSelect.value;
  historyStats = null;
  byId("use-history").disabled = true;
  const body = byId("records-body");
  body.replaceChildren();
  for (const r of dailyRows.filter((r) => r.item === item)) {
    const row = document.createElement("tr");
    for (const value of [
      r.day + " / " + r.item,
      r.prepared,
      r.sold,
      r.prepared - r.sold,
      r.prepared === 0
        ? "No preparation"
        : r.sold === r.prepared
          ? "Possible stockout"
          : "Stock remained",
      r.notes,
    ]) {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.append(cell);
    }
    const cell = document.createElement("td"),
      button = document.createElement("button");
    button.textContent = "Edit";
    button.type = "button";
    button.addEventListener("click", () => editRow(r));
    cell.append(button);
    row.append(cell);
    body.append(row);
  }
  if (!item) {
    byId("history-summary").textContent =
      "No records yet. Add your first day above.";
    return;
  }
  try {
    const s = await requestJSON(
      "/history-summary?item=" + encodeURIComponent(item),
    );
    if (itemSelect.value !== item) return;
    historyStats = s;
    byId("history-summary").textContent =
      `${s.count} usable days; ${s.excluded_zero_prepared} zero-preparation days excluded. ` +
      (s.count ? `Sales average: ${fmt(s.mu)} portions. ` : "") +
      (s.sigma !== null
        ? `Sample standard deviation: ${fmt(s.sigma)}. `
        : "At least two usable days are needed to estimate variation. ") +
      `${s.possible_stockouts} possible stockout days. ` +
      (s.possible_stockouts
        ? "Sales may underestimate demand; this estimate does not correct for lost sales. "
        : "") +
      (s.count < 7
        ? "Very limited history: treat estimates as provisional. "
        : "") +
      "All saved dates for this item are included; missing dates are not treated as zero sales.";
    byId("use-history").disabled = s.count < 2;
  } catch (e) {
    byId("history-summary").textContent = e.message;
  }
}
async function loadRecords(preferred) {
  dailyRows = (await requestJSON("/records")).records;
  regularItems = (await requestJSON("/items")).items;
  renderMenu();
  const names = [...new Set(dailyRows.map((r) => r.item))].sort();
  const previous = preferred || itemSelect.value;
  itemSelect.replaceChildren();
  byId("item-names").replaceChildren();
  for (const name of names) itemSelect.add(new Option(name, name));
  for (const name of [
    ...new Set([...names, ...regularItems.map((r) => r.item)]),
  ].sort())
    byId("item-names").append(new Option(name, name));
  if (names.includes(previous)) itemSelect.value = previous;
  byId("export-records").disabled = !dailyRows.length;
  if (!quickDirty) renderQuickDay();
  await showHistory();
}
recordForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const button = byId("save-record");
  button.disabled = true;
  const data = {
    day: byId("record-day").value,
    item: byId("record-item").value.trim(),
    prepared: Number(byId("record-prepared").value),
    sold: Number(byId("record-sold").value),
    notes: byId("record-notes").value,
  };
  if (editingId !== null) data.id = editingId;
  try {
    await requestJSON("/records", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    resetRecordForm();
    invalidateModel(
      "Records updated. Apply saved records to refresh your recommendation.",
    );
    await loadRecords(data.item);
    byId("record-message").textContent = "Saved on this computer.";
  } catch (e) {
    byId("record-message").textContent = e.message;
  } finally {
    button.disabled = false;
  }
});
byId("cancel-edit").addEventListener("click", () => {
  resetRecordForm();
  byId("record-message").textContent = "Edit cancelled.";
});
itemSelect.addEventListener("change", showHistory);
byId("use-history").addEventListener("click", async () => {
  if (!historyStats || historyStats.count < 2) return;
  const s = historyStats;
  form.elements.mu.value = s.mu;
  form.elements.sigma.value = s.sigma;
  form.elements.baseline.value = s.baseline;
  byId("data-source").textContent =
    `Model source: recorded sales for ${s.item}, ${s.first_day} to ${s.last_day} (${s.count} days). Sales moments are used as approximate normal parameters, not a fitted demand forecast. ${s.possible_stockouts} possible stockout days; unmet demand is not estimated. Baseline is the latest usable day's preparation. Price and cost remain your manual estimates.`;
  historySource = {
    ...s,
    method: "sales moments as approximate latent normal parameters",
  };
  await calculate();
});
form.addEventListener("input", (e) => {
  if (["mu", "sigma", "baseline"].includes(e.target.name)) {
    historySource = null;
    byId("data-source").textContent =
      "Model source: manually edited demand inputs. Calculate to update the recommendation.";
  }
  latest = null;
  download.disabled = true;
  results.textContent = "Inputs changed. Calculate to refresh results.";
  plot.innerHTML = "";
});
byId("export-records").addEventListener("click", () => {
  const quote = (value) =>
    '"' +
    String(value)
      .replace(/^[=+@-]/, "'$&")
      .replaceAll('"', '""') +
    '"';
  const csv = [
    [
      "date",
      "item",
      "prepared",
      "sold",
      "unsold",
      "possible_stockout",
      "notes",
    ],
    ...dailyRows.map((r) => [
      r.day,
      r.item,
      r.prepared,
      r.sold,
      r.prepared - r.sold,
      r.prepared > 0 && r.sold === r.prepared,
      r.notes,
    ]),
  ]
    .map((row) => row.map(quote).join(","))
    .join("\r\n");
  const url = URL.createObjectURL(
      new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8" }),
    ),
    a = document.createElement("a");
  a.href = url;
  a.download = "smartprep-daily-records.csv";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
let quickDirty = false,
  quickDay = localDay;
byId("quick-day").value = localDay;
byId("quick-day").max = localDay;
function addQuickRow(name = "", saved) {
  const row = document.createElement("div");
  row.className = "record-grid";
  const itemLabel = document.createElement("label");
  itemLabel.textContent = "Item";
  const item = document.createElement("input");
  item.value = name;
  item.maxLength = 80;
  item.dataset.field = "item";
  item.placeholder = "e.g. Chicken sandwich";
  item.readOnly = !!name;
  itemLabel.append(item);
  row.append(itemLabel);
  const counts = document.createElement("div");
  counts.className = "record-grid";
  for (const field of ["prepared", "sold"]) {
    const label = document.createElement("label");
    label.textContent = field === "prepared" ? "Prepared" : "Sold";
    const input = document.createElement("input");
    input.type = "number";
    input.min = "0";
    input.max = "1000000";
    input.step = "1";
    input.dataset.field = field;
    input.setAttribute("aria-label", `${field} for ${name || "new item"}`);
    input.value = saved ? saved[field] : "";
    label.append(input);
    counts.append(label);
  }
  row.append(counts);
  row.addEventListener("input", () => {
    quickDirty = true;
    byId("quick-message").textContent = "Unsaved changes.";
  });
  byId("quick-rows").append(row);
}
function renderQuickDay() {
  byId("quick-rows").replaceChildren();
  const names = [
    ...new Set([
      ...regularItems.filter((r) => r.active).map((r) => r.item),
      ...dailyRows.filter((r) => r.day === quickDay).map((r) => r.item),
    ]),
  ].sort();
  for (const name of names)
    addQuickRow(
      name,
      dailyRows.find((r) => r.day === quickDay && r.item === name),
    );
  if (!names.length) addQuickRow();
  quickDirty = false;
}
function renderMenu() {
  const list = byId("menu-list");
  list.replaceChildren();
  for (const entry of regularItems) {
    const row = document.createElement("p");
    const label = document.createElement("span");
    label.textContent =
      entry.item + (entry.active ? " — On daily sheet " : " — Hidden ");
    row.append(label);
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = entry.active ? "Hide" : "Restore";
    button.setAttribute(
      "aria-label",
      `${entry.active ? "Hide" : "Restore"} ${entry.item}`,
    );
    button.addEventListener("click", () =>
      changeMenu(entry.item, !entry.active, button),
    );
    row.append(button);
    list.append(row);
  }
  if (!regularItems.length) {
    list.textContent =
      "No regular items yet. Add your products above to get started.";
  }
}
async function changeMenu(item, active, button) {
  if (quickDirty) {
    byId("menu-message").textContent =
      "Save your daily entries or reload the saved day before changing the menu.";
    return;
  }
  if (button) button.disabled = true;
  try {
    await requestJSON("/items", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ item, active }),
    });
    await loadRecords();
    byId("menu-message").textContent = active
      ? `${item.trim()} is on your regular menu. It will appear on future dates.`
      : `${item} is hidden from new daily sheets. Historical records are kept.`;
    byId("menu-name").value = "";
  } catch (e) {
    byId("menu-message").textContent = e.message;
  } finally {
    if (button) button.disabled = false;
  }
}
byId("menu-form").addEventListener("submit", (e) => {
  e.preventDefault();
  changeMenu(byId("menu-name").value, true, e.submitter);
});
byId("add-quick-item").addEventListener("click", () => {
  addQuickRow();
});
byId("quick-day").addEventListener("change", () => {
  if (quickDirty) {
    byId("quick-day").value = quickDay;
    byId("quick-message").textContent =
      "Save your changes or reload the saved day before changing dates.";
    return;
  }
  quickDay = byId("quick-day").value;
  renderQuickDay();
  byId("quick-message").textContent = "";
});
byId("reset-day").addEventListener("click", () => {
  renderQuickDay();
  byId("quick-message").textContent =
    "Unsaved changes cleared. Showing saved records.";
});
byId("quick-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const button = byId("save-day");
  button.disabled = true;
  try {
    const rows = [];
    for (const row of byId("quick-rows").children) {
      const value = (field) =>
        row.querySelector(`[data-field="${field}"]`).value;
      const prepared = value("prepared"),
        sold = value("sold");
      if (prepared === "" && sold === "") continue;
      if (prepared === "" || sold === "")
        throw Error(
          "Enter both prepared and sold for each item, or leave both blank.",
        );
      rows.push({
        item: value("item").trim(),
        prepared: Number(prepared),
        sold: Number(sold),
      });
    }
    if (!rows.length)
      throw Error("Enter prepared and sold for at least one item.");
    const saved = await requestJSON("/records/batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ day: quickDay, rows }),
    });
    quickDirty = false;
    await loadRecords();
    invalidateModel(
      "Daily records saved. Apply records to update your recommendation.",
    );
    byId("quick-message").textContent =
      `Saved ${saved.saved} item(s) for ${quickDay}. Existing entries updated; notes preserved.`;
  } catch (e) {
    byId("quick-message").textContent = e.message;
  } finally {
    button.disabled = false;
  }
});
loadRecords().catch((e) => {
  byId("record-message").textContent =
    "Could not load saved records: " + e.message;
});
