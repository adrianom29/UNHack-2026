const byId = (id) => document.getElementById(id);
let dailyRows = [],
  regularItems = [],
  editingId = null;
const recordForm = byId("record-form");
// Days the owner has expanded in Past records; kept open across refreshes.
const openDays = new Set();
const today = new Date();
const localDay = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
byId("record-day").value = localDay;
byId("record-day").max = localDay;
async function requestJSON(url, options) {
  const r = await fetch(url, options);
  const data = await readJSON(r);
  if (!r.ok) throw Error(data.error || "Unable to save. Please try again.");
  return data;
}
const postJSON = (url, data) =>
  requestJSON(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

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
const actionButton = (text, label, onClick) => {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = text;
  button.setAttribute("aria-label", label);
  button.addEventListener("click", () => onClick(button));
  return button;
};
const cellRow = (tag, values) => {
  const row = document.createElement("tr");
  for (const value of values) {
    const cell = document.createElement(tag);
    cell.textContent = value;
    row.append(cell);
  }
  return row;
};
const total = (rows, pick) => rows.reduce((sum, r) => sum + pick(r), 0);
const longDate = (day) =>
  new Date(day + "T00:00").toLocaleDateString("en-CA", {
    weekday: "short",
    year: "numeric",
    month: "short",
    day: "numeric",
  });
// One entry per day; expanding a day shows each item recorded on it.
function showHistory() {
  const list = byId("history-days");
  list.replaceChildren();
  const days = new Map();
  for (const r of dailyRows) {
    if (!days.has(r.day)) days.set(r.day, []);
    days.get(r.day).push(r);
  }
  for (const [day, rows] of days) {
    rows.sort((a, b) => a.item.localeCompare(b.item));
    const made = total(rows, (r) => r.prepared),
      sold = total(rows, (r) => r.sold);
    const details = document.createElement("details");
    details.className = "day";
    details.open = openDays.has(day);
    details.addEventListener("toggle", () =>
      details.open ? openDays.add(day) : openDays.delete(day),
    );
    const summary = document.createElement("summary");
    const date = document.createElement("strong");
    date.textContent = longDate(day);
    const stats = document.createElement("span");
    stats.textContent = `${rows.length} item${rows.length === 1 ? "" : "s"} · made ${made} · sold ${sold} · wasted ${made - sold}`;
    summary.append(date, stats);
    details.append(summary);

    const table = document.createElement("table"),
      head = document.createElement("thead"),
      body = document.createElement("tbody");
    head.append(
      cellRow("th", ["Item", "Made", "Sold", "Waste", "Notes", "Action"]),
    );
    for (const r of rows) {
      const row = cellRow("td", [
        r.item,
        r.prepared,
        r.sold,
        r.prepared - r.sold,
        r.notes,
      ]);
      const cell = document.createElement("td");
      cell.className = "actions";
      cell.append(
        actionButton("Edit", `Edit ${r.item} on ${r.day}`, () => editRow(r)),
      );
      row.append(cell);
      body.append(row);
    }
    table.append(head, body);
    const scroll = document.createElement("div");
    scroll.style.overflowX = "auto";
    scroll.append(table);
    const remove = actionButton(
      "Delete day",
      `Delete all records for ${day}`,
      (button) => deleteDay(day, rows.length, button),
    );
    remove.className = "danger";
    details.append(scroll, remove);
    list.append(details);
  }
  byId("history-summary").textContent = days.size
    ? `${days.size} day${days.size === 1 ? "" : "s"} recorded. Click a day to see its items.`
    : "No records yet. Save your first day above.";
}
async function deleteDay(day, count, button) {
  if (
    !confirm(
      `Delete the record for ${longDate(day)} (${count} item${count === 1 ? "" : "s"})? This cannot be undone.`,
    )
  )
    return;
  button.disabled = true;
  try {
    await postJSON("/records/delete-day", { day });
    openDays.delete(day);
    // Stop editing a record that was just deleted with its day.
    if (dailyRows.some((r) => r.id === editingId && r.day === day))
      resetRecordForm();
    await loadRecords();
    byId("history-message").textContent = `Deleted the record for ${longDate(day)}.`;
  } catch (e) {
    byId("history-message").textContent = e.message;
    button.disabled = false;
  }
}
async function loadRecords() {
  dailyRows = (await requestJSON("/records")).records;
  regularItems = (await requestJSON("/items")).items;
  renderMenu();
  const names = [...new Set(dailyRows.map((r) => r.item))].sort();
  byId("item-names").replaceChildren();
  for (const name of [
    ...new Set([...names, ...regularItems.map((r) => r.item)]),
  ].sort())
    byId("item-names").append(new Option(name, name));
  byId("export-records").disabled = !dailyRows.length;
  if (!quickDirty) renderQuickDay();
  showHistory();
  showPlan();
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
    await postJSON("/records", data);
    resetRecordForm();
    await loadRecords();
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
byId("export-records").addEventListener("click", () => {
  const quote = (value) =>
    '"' +
    String(value ?? "")
      .replace(/^[=+@-]/, "'$&")
      .replaceAll('"', '""') +
    '"';
  const csv = [
    ["date", "item", "made", "sold", "waste", "notes"],
    ...dailyRows.map((r) => [
      r.day,
      r.item,
      r.prepared,
      r.sold,
      r.prepared - r.sold,
      r.notes,
    ]),
  ]
    .map((row) => row.map(quote).join(","))
    .join("\r\n");
  const url = URL.createObjectURL(
      new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" }),
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
const QUICK_FIELDS = [
  ["prepared", "Made", "1"],
  ["sold", "Sold", "1"],
];
function addQuickRow(name = "", saved) {
  const row = document.createElement("div");
  row.className = "entry-row";
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
  for (const [field, text, step] of QUICK_FIELDS) {
    const label = document.createElement("label");
    label.textContent = text;
    const input = document.createElement("input");
    input.type = "number";
    input.min = "0";
    input.max = "1000000";
    input.step = step;
    input.dataset.field = field;
    input.setAttribute("aria-label", `${text} for ${name || "new item"}`);
    input.value = saved ? saved[field] : "";
    label.append(input);
    row.append(label);
  }
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
    const row = document.createElement("tr");
    const name = document.createElement("td");
    name.textContent = entry.item;
    row.append(name);
    for (const field of ["price", "cost"]) {
      const cell = document.createElement("td"),
        input = document.createElement("input");
      input.type = "number";
      input.min = "0";
      input.max = "1000000";
      input.step = "0.01";
      input.placeholder = "Not set";
      input.className = "menu-amount";
      input.value = entry[field] ?? "";
      input.setAttribute(
        "aria-label",
        `${field === "price" ? "Price" : "Cost to make"} of ${entry.item} (CAD)`,
      );
      // "change" fires once the owner leaves the box or presses Enter.
      input.addEventListener("change", () => saveAmount(entry, field, input));
      cell.append(input);
      row.append(cell);
    }
    const status = document.createElement("td");
    status.textContent = entry.active ? "On daily sheet" : "Hidden";
    row.append(status);
    const actions = document.createElement("td");
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.textContent = entry.active ? "Hide" : "Restore";
    toggle.setAttribute(
      "aria-label",
      `${entry.active ? "Hide" : "Restore"} ${entry.item}`,
    );
    toggle.addEventListener("click", () =>
      saveMenuItem(
        { item: entry.item, active: !entry.active },
        toggle,
        entry.active
          ? `${entry.item} is hidden from new daily sheets. Past records are kept.`
          : `${entry.item} is back on your daily sheet.`,
      ),
    );
    actions.className = "actions";
    actions.append(
      toggle,
      " ",
      actionButton("Delete", `Delete ${entry.item}`, (button) =>
        deleteMenuItem(entry, button),
      ),
    );
    row.append(actions);
    list.append(row);
  }
  if (!regularItems.length) {
    const row = document.createElement("tr"),
      cell = document.createElement("td");
    cell.colSpan = 5;
    cell.textContent = "No menu items yet. Add your first item below.";
    row.append(cell);
    list.append(row);
  }
}
// Saves one price or cost straight from the menu table. The table is not
// redrawn, so moving from one box to the next keeps the cursor in place.
async function saveAmount(entry, field, input) {
  const label = field === "price" ? "price" : "cost";
  const previous = entry[field] ?? "";
  if (input.value === "" || !input.checkValidity()) {
    input.value = previous;
    byId("menu-message").textContent =
      `Enter a ${label} of 0 or more for ${entry.item}.`;
    return;
  }
  input.disabled = true;
  try {
    const { items } = await postJSON("/items", {
      item: entry.item,
      active: !!entry.active,
      [field]: Number(input.value),
    });
    regularItems = items;
    Object.assign(entry, items.find((i) => i.item === entry.item));
    input.value = entry[field];
    byId("menu-message").textContent = `Saved ${entry.item} ${label}.`;
    showPlan();
  } catch (e) {
    input.value = previous;
    byId("menu-message").textContent = e.message;
  } finally {
    input.disabled = false;
  }
}
async function deleteMenuItem(entry, button) {
  if (quickDirty) {
    byId("menu-message").textContent =
      "Save your daily entries or reload the saved day before changing the menu.";
    return;
  }
  const count = dailyRows.filter((r) => r.item === entry.item).length;
  const warning = count
    ? `Delete ${entry.item} and its ${count} past record(s)? This cannot be undone. To keep the records, use Hide instead.`
    : `Delete ${entry.item} from the menu?`;
  if (!confirm(warning)) return;
  button.disabled = true;
  try {
    await postJSON("/items/delete", { item: entry.item });
    if (byId("record-item").value.trim() === entry.item) resetRecordForm();
    await loadRecords();
    byId("menu-message").textContent = count
      ? `Deleted ${entry.item} and ${count} past record(s).`
      : `Deleted ${entry.item}.`;
  } catch (e) {
    byId("menu-message").textContent = e.message;
    button.disabled = false;
  }
}
async function saveMenuItem(data, button, message) {
  if (quickDirty) {
    byId("menu-message").textContent =
      "Save your daily entries or reload the saved day before changing the menu.";
    return false;
  }
  if (button) button.disabled = true;
  try {
    await postJSON("/items", data);
    await loadRecords();
    byId("menu-message").textContent = message;
    return true;
  } catch (e) {
    byId("menu-message").textContent = e.message;
    return false;
  } finally {
    if (button) button.disabled = false;
  }
}
byId("menu-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const item = byId("menu-name").value.trim();
  const saved = await saveMenuItem(
    {
      item,
      price: Number(byId("menu-price").value),
      cost: Number(byId("menu-cost").value),
      active: true,
    },
    e.submitter,
    `${item} added. It will appear on your daily sheet.`,
  );
  if (saved) byId("menu-form").reset();
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
      const name = value("item").trim();
      if (value("prepared") === "" && value("sold") === "") continue;
      if (QUICK_FIELDS.some(([field]) => value(field) === ""))
        throw Error(
          `Enter both made and sold for ${name || "each item"}, or leave both blank to skip it.`,
        );
      rows.push({
        item: name,
        ...Object.fromEntries(
          QUICK_FIELDS.map(([field]) => [field, Number(value(field))]),
        ),
      });
    }
    if (!rows.length) throw Error("Enter made and sold for at least one item.");
    const saved = await postJSON("/records/batch", { day: quickDay, rows });
    quickDirty = false;
    await loadRecords();
    byId("quick-message").textContent =
      `Saved ${saved.saved} item(s) for ${quickDay}.`;
  } catch (e) {
    byId("quick-message").textContent = e.message;
  } finally {
    button.disabled = false;
  }
});
loadRecords().catch((e) => {
  byId("quick-message").textContent =
    "Could not load saved records: " + e.message;
});
