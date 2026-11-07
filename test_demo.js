// Optional integration check: start python smartprep.py --serve first, then node test_demo.js.
const fs = require("fs"),
  vm = require("vm"),
  assert = require("assert");
const fields = { p: 12, c: 5, mu: 80, sigma: 15, baseline: 100 };
const elements = Object.fromEntries(
  ["inputs", "results", "error", "plot", "download"].map((k) => [
    k,
    {
      innerHTML: "",
      textContent: "",
      addEventListener: (event, fn) => {
        elements[k][event] = fn;
      },
    },
  ]),
);
const context = {
  document: { getElementById: (k) => elements[k] },
  FormData: class {
    *[Symbol.iterator]() {
      yield* Object.entries(fields);
    }
  },
  fetch: (url, opts) =>
    fetch((process.env.SMARTPREP_URL || "http://127.0.0.1:8765") + url, opts),
  console,
  Blob,
  URL,
  setTimeout,
};
vm.createContext(context);
vm.runInContext(
  fs.readFileSync("app.js", "utf8"),
  context,
);
(async () => {
  await vm.runInContext("calculate()", context);
  assert(
    elements.results.innerHTML.includes("83 portions"),
    elements.error.textContent,
  );
  assert(elements.plot.innerHTML.includes("polyline"));
  fields.sigma = 0;
  await vm.runInContext("calculate()", context);
  assert(elements.results.innerHTML.includes("80 portions"));
  fields.sigma = 15;
  fields.c = 0;
  await vm.runInContext("calculate()", context);
  assert(elements.error.textContent.includes("no finite"));
  assert(elements.download.disabled);
  console.log(
    "PASS: default render, recalculation, chart update, invalid-input state",
  );
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
