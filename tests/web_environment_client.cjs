// Kör den levererade klientkoden med en liten DOM-testdubbel och utan nätverk.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const source = fs.readFileSync(path.join(__dirname, "../src/web/static/environment.js"), "utf8");

function setup() {
  const events = {};
  const select = { value: "demo", disabled: false };
  const button = { disabled: false };
  const message = { hidden: true, textContent: "" };
  const draft = { method: "post", values: [["salary", "45000"]], hasAttribute: () => false };
  const picker = {
    method: "post", dataset: { currentDatabase: "demo" }, action: "http://127.0.0.1:8767/miljo",
    values: [["database", "lakebase"], ["csrf_token", "token"]],
    matches: () => true, hasAttribute: () => true,
    elements: { namedItem: () => select },
    querySelector: query => query.startsWith("button") ? button : message,
  };
  const state = { confirms: 0, fetches: 0, navigations: [], allow: true, response: { ok: true, url: "http://127.0.0.1:8765/" } };
  const dialog = {
    addEventListener: (_name, fn) => { dialog.closed = fn; },
    showModal: () => { state.confirms++; queueMicrotask(() => { dialog.returnValue = state.allow ? "discard" : "cancel"; dialog.closed(); }); },
  };
  const document = { readyState: "interactive", forms: [picker, draft],
    querySelector: () => dialog, addEventListener: (name, fn) => { events[name] = fn; } };
  vm.runInNewContext(source, {
    document, window: {
      location: { assign: url => state.navigations.push(url) },
    },
    FormData: class { constructor(form) { this.values = form.values; } [Symbol.iterator]() { return this.values[Symbol.iterator](); } },
    AbortController, setTimeout, clearTimeout,
    fetch: async (_url, options) => {
      state.fetches++;
      assert.equal(options.method, "POST");
      assert.equal(options.headers.Accept, "application/json");
      assert.deepEqual([...options.body], picker.values);
      return { ok: state.response.ok, json: async () => state.response };
    },
  });
  const submit = async () => { select.value = "lakebase"; await events.submit({ target: picker, preventDefault() {} }); };
  return { events, select, button, message, draft, picker, document, state, submit };
}

(async () => {
  let test = setup();
  await test.submit();
  assert.deepEqual(test.state.navigations, ["http://127.0.0.1:8765/"]);
  assert.equal(test.state.confirms, 0);

  test = setup();
  test.draft.values = [["salary", "46000"]];
  test.state.allow = false;
  await test.submit();
  assert.equal(test.state.confirms, 1);
  assert.equal(test.state.fetches, 0);
  assert.equal(test.select.value, "demo");
  assert.deepEqual(test.draft.values, [["salary", "46000"]]);
  test.state.allow = true;
  await test.submit();
  assert.deepEqual(test.state.navigations, ["http://127.0.0.1:8765/"]);

  test = setup();
  test.draft.values = [["salary", "46000"]];
  test.state.response = { ok: false, message: "Fel databas på målporten" };
  await test.submit();
  assert.equal(test.message.textContent, "Fel databas på målporten");
  assert.equal(test.select.value, "demo");
  assert.equal(test.button.disabled, false);
  assert.deepEqual(test.state.navigations, []);
  assert.deepEqual(test.draft.values, [["salary", "46000"]]);

  test = setup();
  const xhr = {};
  test.events["htmx:beforeRequest"]({ detail: { requestConfig: { verb: "post" }, xhr } });
  await test.submit();
  assert.equal(test.state.fetches, 0);
  assert.match(test.message.textContent, /pågående/);
  test.events["htmx:afterRequest"]({ detail: { xhr } });
  await test.submit();
  assert.equal(test.state.fetches, 1);

  test = setup();
  const added = { method: "post", values: [["reason", ""]], hasAttribute: () => false };
  test.document.forms.push(added);
  test.events["htmx:load"]();
  added.values = [["reason", "osparat"]];
  test.state.allow = false;
  await test.submit();
  assert.equal(test.state.confirms, 1);
  assert.equal(test.state.fetches, 0);
  console.log("Klientprov godkända: byte, avbryt, osparat formulär, målmiljöfel, pågående skrivning och HTMX-formulär.");
})().catch(error => { console.error(error); process.exitCode = 1; });
