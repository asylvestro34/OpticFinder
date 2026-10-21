const {test} = require("node:test");
const assert = require("node:assert/strict");
const {readFileSync} = require("node:fs");
const {join} = require("node:path");
const vm = require("node:vm");

function themePage({stored = null, dark = false, storageBlocked = false} = {}) {
  const listeners = {};
  const label = {};
  const toggle = {
    hidden: true,
    querySelector: () => label,
    setAttribute(name, value) { this[name] = value; },
    addEventListener(name, callback) { listeners[name] = callback; },
  };
  const root = {dataset: {}};
  const system = {
    matches: dark,
    addEventListener(name, callback) { listeners.systemChange = callback; },
  };
  const warnings = [];
  const storage = {
    getItem() {
      if (storageBlocked) throw new Error("Storage blocked");
      return stored;
    },
    setItem(key, value) {
      if (storageBlocked) throw new Error("Storage blocked");
      assert.equal(key, "opticfinder-theme");
      stored = value;
    },
  };
  vm.runInNewContext(readFileSync(join(__dirname, "..", "opticfinder", "theme.js"), "utf8"), {
    window: {
      matchMedia: () => system,
      localStorage: storage,
      addEventListener(name, callback) { listeners[name] = callback; },
    },
    document: {
      documentElement: root,
      querySelector: () => toggle,
      addEventListener(name, callback) { listeners[name] = callback; },
    },
    console: {warn: (...args) => warnings.push(args)},
  });
  return {root, toggle, label, system, listeners, warnings, storage, stored: () => stored};
}

test("theme applies system preference before DOM readiness and follows system changes", () => {
  const page = themePage({dark: true});
  assert.equal(page.root.dataset.theme, "dark");
  assert.equal(page.toggle.hidden, true);
  page.listeners.DOMContentLoaded();
  assert.equal(page.toggle.hidden, false);
  assert.equal(page.label.textContent, "Dark");
  assert.equal(page.toggle["aria-label"], "Switch to light theme");
  page.system.matches = false;
  page.listeners.systemChange();
  assert.equal(page.root.dataset.theme, "light");
});

test("manual theme overrides system, persists and synchronizes across pages", () => {
  const page = themePage({stored: "light", dark: true});
  page.listeners.DOMContentLoaded();
  assert.equal(page.root.dataset.theme, "light");
  page.listeners.click();
  assert.equal(page.root.dataset.theme, "dark");
  assert.equal(page.stored(), "dark");
  assert.equal(page.toggle["aria-label"], "Switch to light theme");
  page.system.matches = false;
  page.listeners.systemChange();
  assert.equal(page.root.dataset.theme, "dark");
  page.storage.setItem("opticfinder-theme", "light");
  page.listeners.storage({key: "opticfinder-theme"});
  assert.equal(page.root.dataset.theme, "light");
  page.storage.setItem("opticfinder-theme", null);
  page.listeners.storage({key: null});
  page.system.matches = true;
  page.listeners.systemChange();
  assert.equal(page.root.dataset.theme, "dark");
});

test("invalid or unavailable stored preferences keep the theme switch usable", () => {
  const invalid = themePage({stored: "invalid", dark: true});
  assert.equal(invalid.root.dataset.theme, "dark");
  const blocked = themePage({storageBlocked: true});
  blocked.listeners.DOMContentLoaded();
  blocked.listeners.click();
  assert.equal(blocked.root.dataset.theme, "dark");
  assert.equal(blocked.label.textContent, "Dark");
  assert.equal(blocked.warnings.length, 2);
});

class Element {
  constructor() {
    this.children = [];
    this.textContent = "";
    this.listeners = new Map();
  }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  addEventListener(name, callback) { this.listeners.set(name, callback); }
  setAttribute(name, value) { this[name] = value; }
  get text() {
    return this.textContent + this.children.map((child) =>
      typeof child === "string" ? child : child.text
    ).join(" ");
  }
}

function dashboard() {
  const elements = new Map();
  const document = {
    querySelector(selector) {
      if (!elements.has(selector)) elements.set(selector, new Element());
      return elements.get(selector);
    },
    createElement() { return new Element(); },
  };
  document.querySelector("#planner").querySelector = () => new Element();
  const context = vm.createContext({
    document,
    Option: function(label, value) { this.textContent = label; this.value = value; },
    fetch: () => new Promise(() => {}),
  });
  vm.runInContext(readFileSync(join(__dirname, "..", "opticfinder", "app.js"), "utf8"), context);
  vm.runInContext(`catalog = {endpoints: [
    {id: "a", label: "Meraki MS130-24X"},
    {id: "b", label: "Meraki MS130-24P"}
  ]};`, context);
  return {
    context,
    render(result) {
      context.result = result;
      vm.runInContext("renderResult(result)", context);
    },
    element: (selector) => document.querySelector(selector),
  };
}

test("single-choice dropdowns default without a placeholder; other counts keep it", () => {
  const page = dashboard();
  page.context.select = new Element();
  for (const choices of [
    [{id: "device", label: "Only device"}],
    [{id: "port", label: "Only port"}],
    [{id: 1, label: "1"}],
    [{id: "OS2", label: "OS2"}],
    [],
    [{id: 1, label: "1"}, {id: 10, label: "10"}],
  ]) {
    page.context.choices = choices;
    vm.runInContext('populateSelect(select, choices, "Choose")', page.context);
    const select = page.context.select;
    assert.equal(select.children.length, choices.length === 1 ? 1 : choices.length + 1);
    assert.equal(select.value, choices.length === 1 ? String(choices[0].id) : "");
  }
});

test("a single speed populates and defaults its only cable automatically", () => {
  const page = dashboard();
  const fields = Object.fromEntries(
    ["endpoint_a", "endpoint_b", "interface_a", "interface_b", "speed_gbps", "cable_type", "distance_m"]
      .map((name) => [name, new Element()])
  );
  Object.assign(fields.endpoint_a, {value: "a"});
  Object.assign(fields.endpoint_b, {value: "b"});
  fields.interface_a.value = fields.interface_b.value = "port";
  fields.distance_m.value = "30";
  page.element("#planner").elements = {namedItem: (name) => fields[name]};
  vm.runInContext(`catalog = {
    endpoints: ["a", "b"].map(id => ({id, interfaces: [
      {id: "port", kind: "sfp", speeds_gbps: [1]}
    ]})),
    connection_profiles: [{endpoint_ids: ["a", "b"], speed_gbps: 1,
      parts_by_port_kind: {sfp: "optic"}, reach_m: {OS2: 10000}}],
    cable_types: [{id: "OS2", label: "OS2"}]
  }; updatePlanningOptions();`, page.context);
  assert.equal(fields.speed_gbps.value, "1");
  assert.equal(fields.cable_type.value, "OS2");
  assert.equal(fields.speed_gbps.children.length, 1);
  assert.equal(fields.cable_type.children.length, 1);
  assert.equal(page.element("#link-requirements").hidden, false);
  fields.interface_b.value = "";
  vm.runInContext("updatePlanningOptions()", page.context);
  assert.equal(fields.speed_gbps.value, "");
  assert.equal(fields.cable_type.value, "");
  assert.equal(page.element("#link-requirements").hidden, true);
});

test("endpoint-specific module eligibility and mixed-family groups govern dropdowns", () => {
  const page = dashboard();
  const fields = Object.fromEntries(
    ["endpoint_a", "endpoint_b", "interface_a", "interface_b", "speed_gbps", "cable_type", "distance_m"]
      .map((name) => [name, new Element()])
  );
  fields.endpoint_a.value = "a";
  fields.endpoint_b.value = "b";
  fields.interface_a.value = fields.interface_b.value = "sfp";
  page.element("#planner").elements = {namedItem: (name) => fields[name]};
  vm.runInContext(`catalog = {
    endpoints: ["a", "b"].map(id => ({id, interfaces: [
      {id: "sfp", kind: "sfp", speeds_gbps: [1]},
      {id: "native", kind: "rj45", speeds_gbps: [1, 2.5]}
    ]})),
    connection_profiles: [
      {id: "mixed", endpoint_ids: ["a", "b"], endpoint_groups: [["a"], ["b"]],
        speed_gbps: 1, parts_by_port_kind: {sfp: "ordinary"},
        parts_by_endpoint: {a: {sfp: "ordinary"}, b: {sfp: "rugged"}}, reach_m: {OM3: 550}},
      {id: "native", endpoint_ids: ["a", "b"], speed_gbps: 2.5,
        parts_by_port_kind: {rj45: null}, parts_by_endpoint: {a: {rj45: null}, b: {rj45: null}},
        reach_m: {CAT6: 100}},
      {id: "restricted", endpoint_ids: ["a", "b"], speed_gbps: 1,
        parts_by_port_kind: {sfp: "not-qualified-for-b"},
        parts_by_endpoint: {a: {sfp: "ordinary"}, b: {rj45: null}}, reach_m: {CAT6: 100}}
    ], cable_types: [{id: "OM3", label: "OM3"}, {id: "CAT6", label: "Cat6"}]
  };`, page.context);
  assert.equal(vm.runInContext("profilesForSelection().map(p => p.id).join(',')", page.context), "mixed");
  vm.runInContext("updatePlanningOptions()", page.context);
  assert.equal(fields.speed_gbps.value, "1");
  assert.equal(fields.cable_type.value, "OM3");
  fields.endpoint_b.value = "a";
  assert.equal(vm.runInContext("profilesForSelection().some(p => p.id === 'mixed')", page.context), false);
  fields.endpoint_b.value = "b";
  fields.interface_a.value = fields.interface_b.value = "native";
  vm.runInContext("updatePlanningOptions()", page.context);
  assert.equal(fields.speed_gbps.value, "2.5");
  assert.equal(fields.cable_type.value, "CAT6");
});

test("lifecycle and WAN activation notes follow the selected device and port", () => {
  const page = dashboard();
  const fields = Object.fromEntries(
    ["endpoint_a", "endpoint_b", "interface_a", "interface_b", "speed_gbps", "cable_type", "distance_m"]
      .map((name) => [name, new Element()])
  );
  fields.endpoint_a.value = "mx";
  fields.endpoint_b.value = "ms";
  fields.interface_a.value = "wan";
  fields.interface_b.value = "port";
  page.element("#planner").elements = {namedItem: (name) => fields[name]};
  vm.runInContext(`catalog = {
    endpoints: [
      {id: "mx", end_of_sale: "2026-11-27", wan_requirements: ["Paired WAN activation."],
        interfaces: [{id: "wan", role: "wan"}, {id: "lan", role: "lan"}]},
      {id: "ms", interfaces: [{id: "port"}]}
    ], connection_profiles: [], cable_types: []
  }; updatePlanningOptions();`, page.context);
  assert.match(page.element("#device-notes-a").text, /2026-11-27.*Paired WAN/);
  assert.equal(page.element("#device-notes-b").text, "");
  fields.interface_a.value = "lan";
  vm.runInContext("updatePlanningOptions()", page.context);
  assert.doesNotMatch(page.element("#device-notes-a").text, /Paired WAN/);
  fields.endpoint_a.value = "";
  vm.runInContext("updatePlanningOptions()", page.context);
  assert.equal(page.element("#device-notes-a").text, "");
});

test("planner cable families filter grades, reset stale choices and retain singleton defaults", () => {
  const page = dashboard();
  const fields = Object.fromEntries(
    ["endpoint_a", "endpoint_b", "interface_a", "interface_b", "speed_gbps", "cable_type", "distance_m"]
      .map((name) => [name, new Element()])
  );
  fields.endpoint_a.value = "a";
  fields.endpoint_b.value = "b";
  fields.interface_a.value = fields.interface_b.value = "port";
  fields.distance_m.value = "30";
  page.element("#planner").elements = {namedItem: (name) => fields[name]};
  vm.runInContext(`catalog = {
    endpoints: ["a", "b"].map(id => ({id, interfaces: [
      {id: "port", kind: "sfp", speeds_gbps: [1, 10]}
    ]})),
    connection_profiles: [
      {endpoint_ids: ["a", "b"], speed_gbps: 1, parts_by_port_kind: {sfp: "sx"},
        reach_m: {OM3: 550, OM4: 1000}},
      {endpoint_ids: ["a", "b"], speed_gbps: 1, parts_by_port_kind: {sfp: "lx"},
        reach_m: {OS2: 10000}},
      {endpoint_ids: ["a", "b"], speed_gbps: 10, parts_by_port_kind: {sfp: "dac"},
        reach_m: {DAC: 3}}
    ],
    cable_types: ["OM3", "OM4", "OS2", "DAC"].map(id => ({id, label: id}))
  }; updatePlanningOptions();`, page.context);
  const family = page.element("#cable-family");
  fields.speed_gbps.value = "1";
  vm.runInContext("updateCableTypes()", page.context);
  assert.equal(family.value, "");
  assert.equal(fields.cable_type.disabled, true);
  family.value = "OM";
  vm.runInContext("updateCableGrades()", page.context);
  assert.equal(fields.cable_type.children.map(o => o.value).join(","), ",OM3,OM4");
  fields.cable_type.value = "OM4";
  family.value = "OS";
  vm.runInContext("updateCableGrades()", page.context);
  assert.equal(fields.cable_type.value, "OS2");
  assert.equal(fields.cable_type.children.length, 1);
  fields.speed_gbps.value = "10";
  vm.runInContext("updateCableTypes()", page.context);
  assert.equal(family.value, "DAC");
  assert.equal(fields.cable_type.value, "DAC");
  fields.interface_b.value = "";
  vm.runInContext("updatePlanningOptions()", page.context);
  assert.equal(family.value, "");
  assert.equal(fields.cable_type.value, "");
  assert.equal(fields.cable_type.disabled, true);
});

function result(parts = ["MA-SFP-1GB-SX", "MA-SFP-1GB-SX"], changes = {}) {
  const options = Object.fromEntries(["endpoint_a", "endpoint_b"].map((field, index) =>
    [field, [{
      part: parts[index],
      interface_label: index === 0 ? "4 x 10G SFP+ ports" : "4 x 1G SFP ports",
      connection: parts[index] ? "transceiver" : "native_rj45",
    }]]
  ));
  return {
    status: "not_verified",
    request: {endpoint_a: "a", endpoint_b: "b", speed_gbps: 1, cable_type: "OM3", distance_m: 30},
    candidates: [{
      standard: "1000BASE-SX", cable: "OM3, Duplex LC", documented_profile_reach_m: 550,
      endpoint_connection_options: options, requirements: [],
    }],
    exclusions: [],
    next_steps: ["Verify firmware."],
    sources: [],
    ...changes,
  };
}

function deviceFields(page) {
  const fields = Object.fromEntries(
    ["mode", "endpoint_a", "endpoint_b", "interface_a", "interface_b",
      "speed_gbps", "cable_type", "distance_m"].map(name => [name, new Element()])
  );
  fields.mode.value = "devices";
  fields.endpoint_a.value = "a";
  fields.endpoint_b.value = "b";
  fields.interface_a.value = fields.interface_b.value = "";
  page.element("#planner").elements = {namedItem: name => fields[name]};
  vm.runInContext(`catalog = {
    endpoints: ["a", "b"].map(id => ({id, label: id, interfaces: [
      {id: "port", label: "SFP", kind: "sfp", speeds_gbps: [1, 10]}
    ]})), connection_profiles: [], cable_types: []
  };`, page.context);
  return fields;
}

test("device-only mode requires only devices and hides/disables detailed fields", () => {
  const page = dashboard();
  const fields = deviceFields(page);
  vm.runInContext("updatePlanningOptions()", page.context);
  assert.equal(page.element("#link-requirements").hidden, true);
  assert.equal(page.element("#link-requirements").disabled, true);
  assert.equal(page.element("#port-field-a").hidden, true);
  assert.equal(page.element("#port-field-b").hidden, true);
  assert.equal(fields.interface_a.disabled, true);
  assert.equal(fields.interface_b.disabled, true);
  assert.equal(vm.runInContext("button.disabled", page.context), false);
  fields.endpoint_b.value = "";
  vm.runInContext("updateSubmitState()", page.context);
  assert.equal(vm.runInContext("button.disabled", page.context), true);
  fields.endpoint_b.value = "b";
  fields.mode.value = "detailed";
  vm.runInContext("updatePlanningOptions()", page.context);
  assert.equal(page.element("#port-field-a").hidden, false);
  assert.equal(fields.interface_a.disabled, false);
  assert.equal(vm.runInContext("button.disabled", page.context), true);
  fields.mode.value = "devices";
  vm.runInContext("updatePlanningOptions()", page.context);
  assert.equal(vm.runInContext("button.disabled", page.context), false);
});

test("device-only serialization omits stale detailed filters and never assumes a length", () => {
  const page = dashboard();
  const fields = deviceFields(page);
  fields.speed_gbps.value = "10";
  fields.cable_type.value = "DAC";
  fields.distance_m.value = "30";
  assert.deepEqual(JSON.parse(vm.runInContext("JSON.stringify(planningRequest())", page.context)), {
    mode: "devices", endpoint_a: "a", endpoint_b: "b",
  });
  fields.mode.value = "detailed";
  const detailed = {
    endpoint_a: "a", endpoint_b: "b", interface_a: "port", interface_b: "port",
    speed_gbps: "10", cable_type: "DAC", distance_m: "30",
  };
  page.context.FormData = class {
    constructor() { return Object.entries({mode: "detailed", ...detailed}); }
  };
  assert.deepEqual(
    JSON.parse(vm.runInContext("JSON.stringify(planningRequest())", page.context)), detailed
  );
});

test("device-only cards show alternative ports, cable limits and conditional requirements", () => {
  const page = dashboard();
  const data = result();
  data.request = {mode: "devices", endpoint_a: "a", endpoint_b: "b"};
  Object.assign(data.candidates[0], {
    speed_gbps: 10, cable: "Duplex LC", cable_options: {OM3: 300, OM4: 400},
    minimum_distance_m: 2, requirements: ["Device A (WAN): Check paired WAN activation."],
  });
  data.candidates[0].endpoint_connection_options.endpoint_a.push({
    interface_label: "Alternative SFP ports", part: "MA-SFP-10GB-SR", connection: "transceiver",
  });
  page.render(data);
  assert.match(page.element("#candidates").text, /10 Gbps/);
  assert.match(page.element("#candidates").text, /Choose one port option:.*Alternative SFP ports/);
  assert.match(page.element("#candidates").text, /OM3: 300 m.*OM4: 400 m/);
  assert.match(page.element("#candidates").text, /Minimum cable length: 2 m/);
  assert.match(page.element("#candidates").text, /WAN.*paired WAN/);
  assert.doesNotMatch(page.element("#candidates").text, /3 x|Selected length|undefined/);
  assert.match(page.element("#connection-summary").text, /No cable length/);
});

test("device-only DAC cards show fixed length without implying a route was checked", () => {
  const page = dashboard();
  const data = result([null, null]);
  data.request = {mode: "devices", endpoint_a: "a", endpoint_b: "b"};
  Object.assign(data.candidates[0], {
    speed_gbps: 10, cable_options: {DAC: 3}, assembly_options: [
      {part: "MA-CBL-TA-1M", length_m: 1}, {part: "MA-CBL-TA-3M", length_m: 3},
    ],
  });
  page.render(data);
  assert.equal(page.element("#status").text, "Connection option found");
  assert.equal(page.element("#candidates").children.length, 1);
  assert.match(page.element("#candidates").text, /choose one integrated DAC assembly/);
  assert.match(page.element("#candidates").text, /1 m \(MA-CBL-TA-1M\).*3 m \(MA-CBL-TA-3M\)/);
  assert.doesNotMatch(page.element("#candidates").text,
    /Required route|undefined|Cable grade and max length|one listed transceiver/);
});

test("combined copper grades count as one Ethernet connection with all limits visible", () => {
  const page = dashboard();
  const data = result([null, null]);
  data.request = {mode: "devices", endpoint_a: "a", endpoint_b: "b"};
  Object.assign(data.candidates[0], {
    standard: "1000BASE-T", speed_gbps: 1, cable: "RJ45",
    cable_options: {CAT5E: 100, CAT6: 100, CAT6A: 100, CAT7: 100, CAT8: 100},
  });
  page.render(data);
  assert.equal(page.element("#status").text, "Connection option found");
  assert.equal(page.element("#candidates").children.length, 1);
  assert.match(page.element("#candidates").text, /1 Gbps \| Copper Ethernet/);
  assert.match(page.element("#candidates").text,
    /CAT5E: 100 m.*CAT6: 100 m.*CAT6A: 100 m.*CAT7: 100 m.*CAT8: 100 m/);
});

test("submitting device-only sends only devices and ignores results for changed selections", async () => {
  const page = dashboard();
  const fields = deviceFields(page);
  let finish;
  let sent;
  const responseBody = new Promise(resolve => { finish = resolve; });
  page.context.fetch = async (url, options) => {
    sent = {url, body: JSON.parse(options.body)};
    return {ok: true, json: () => responseBody};
  };
  const submit = page.element("#planner").listeners.get("submit");
  const pending = submit({preventDefault() {}});
  await Promise.resolve();
  assert.deepEqual(sent, {
    url: "/api/plan", body: {mode: "devices", endpoint_a: "a", endpoint_b: "b"},
  });
  fields.endpoint_b.value = "a";
  finish(result());
  await pending;
  assert.equal(page.element("#result").hidden, true);
  assert.equal(vm.runInContext("submitting", page.context), false);
});

test("device-only submission renders current results and surfaces API failures", async () => {
  const page = dashboard();
  deviceFields(page);
  const data = result();
  data.request = {mode: "devices", endpoint_a: "a", endpoint_b: "b"};
  Object.assign(data.candidates[0], {speed_gbps: 1, cable_options: {OM3: 550}});
  page.context.fetch = async () => ({ok: true, json: async () => data});
  const submit = page.element("#planner").listeners.get("submit");
  await submit({preventDefault() {}});
  assert.equal(page.element("#result").hidden, false);
  assert.match(page.element("#candidates").text, /OM3: 550 m/);
  assert.equal(vm.runInContext("button.disabled", page.context), false);
  page.context.fetch = async () => ({ok: false, json: async () => ({error: "Unknown endpoint_a"})});
  await submit({preventDefault() {}});
  assert.equal(page.element("#result").hidden, true);
  assert.equal(page.element("#error").text, "Unknown endpoint_a");
  assert.equal(vm.runInContext("button.disabled", page.context), false);
});

test("result filters combine speed and family, preserve order, and reset for new plans", () => {
  const page = dashboard();
  const base = result().candidates[0];
  const data = result([], {
    request: {mode: "devices", endpoint_a: "a", endpoint_b: "b"},
    candidates: [
      {...base, standard: "DAC 10G", speed_gbps: 10, cable_options: {DAC: 3}},
      {...base, standard: "MMF 10G", speed_gbps: 10, cable_options: {OM3: 300}},
      {...base, standard: "SMF 10G", speed_gbps: 10, cable_options: {OS2: 10000}},
      {...base, standard: "Copper 1G", speed_gbps: 1, cable_options: {CAT6: 100}},
      {...base, standard: "MMF 1G", speed_gbps: 1, cable_options: {OM3: 550}},
    ],
  });
  page.render(data);
  const speed = page.element("#result-speed");
  const family = page.element("#result-family");
  const cards = () => page.element("#candidates");
  assert.equal(page.element("#result-filters").hidden, false);
  assert.equal(speed.value, "");
  assert.equal(family.value, "");
  assert.deepEqual(speed.children.map(option => option.value), ["", "10", "1"]);
  assert.deepEqual(family.children.map(option => option.value), ["", "DAC", "CAT", "OM", "OS"]);
  assert.equal(cards().children.length, 5);
  assert.match(cards().text, /DAC 10G.*MMF 10G.*SMF 10G.*Copper 1G.*MMF 1G/);
  family.value = "OM";
  family.listeners.get("change")();
  assert.equal(cards().children.length, 2);
  assert.match(page.element("#result-count").text, /Showing 2 of 5/);
  speed.value = "10";
  speed.listeners.get("change")();
  assert.equal(family.value, "OM");
  assert.deepEqual(family.children.map(option => option.value), ["", "DAC", "OM", "OS"]);
  assert.equal(cards().children.length, 1);
  assert.match(cards().text, /MMF 10G/);
  family.value = "DAC";
  family.listeners.get("change")();
  assert.match(cards().text, /DAC 10G/);
  speed.value = "1";
  speed.listeners.get("change")();
  assert.equal(family.value, "");
  assert.equal(cards().children.length, 2);
  assert.deepEqual(family.children.map(option => option.value), ["", "CAT", "OM"]);
  speed.value = "";
  speed.listeners.get("change")();
  assert.equal(cards().children.length, 5);
  family.value = "OS";
  family.listeners.get("change")();
  page.render(data);
  assert.equal(speed.value, "");
  assert.equal(family.value, "");
  assert.equal(cards().children.length, 5);
  assert.equal(JSON.parse(page.element("#json").text).candidates.length, 5);
});

test("result filters stay hidden for detailed plans and no matches", () => {
  const page = dashboard();
  page.render(result());
  assert.equal(page.element("#result-filters").hidden, true);
  assert.equal(page.element("#result-count").hidden, true);
  page.render(result([], {
    request: {mode: "devices", endpoint_a: "a", endpoint_b: "b"},
    candidates: [],
  }));
  assert.equal(page.element("#result-filters").hidden, true);
  assert.equal(page.element("#result-count").hidden, true);
});

test("fiber results show readable device cards, quantities and reach instead of API status", () => {
  const page = dashboard();
  page.render(result());
  assert.equal(page.element("#status").text, "Connection option found");
  assert.match(page.element("#candidates").text, /Device A.*Meraki MS130-24X.*Device B.*Meraki MS130-24P/);
  assert.match(page.element("#candidates").text, /2 x MA-SFP-1GB-SX/);
  assert.match(page.element("#candidates").text, /Selected length: 30 m.*Max length: 550 m/);
  assert.doesNotMatch(page.element("#candidates").text, /not_verified|Provisional/);
  assert.equal(page.element("#technical-details").open, false);
  assert.match(page.element("#json").text, /not_verified/);
});

test("transceiver and DAC links use official catalog sources in both planning modes", () => {
  const page = dashboard();
  vm.runInContext(`catalog.sources = [
    {id: "meraki-accessories", url: "https://documentation.meraki.com/accessories"},
    {id: "cisco-ge-sfp", url: "https://www.cisco.com/gigabit-sfp"}
  ];`, page.context);
  const linksIn = element => [
    ...(element.href ? [element] : []),
    ...element.children.filter(child => typeof child !== "string").flatMap(linksIn),
  ];
  for (const browse of [false, true]) {
    const data = result(["MA-SFP-1GB-SX", "GLC-SX-MM-RGD"]);
    if (browse) {
      data.request = {mode: "devices", endpoint_a: "a", endpoint_b: "b"};
      Object.assign(data.candidates[0], {speed_gbps: 1, cable_options: {OM3: 550}});
    }
    page.render(data);
    const links = linksIn(page.element("#candidates"));
    assert.deepEqual(links.map(link => link.href), [
      "https://documentation.meraki.com/accessories", "https://www.cisco.com/gigabit-sfp",
    ]);
    for (const link of links) {
      assert.equal(link.target, "_blank");
      assert.equal(link.rel, "noopener noreferrer");
      assert.match(link["aria-label"], /Official vendor documentation.*opens in a new tab/);
    }
    const dac = result([null, null]);
    if (browse) {
      dac.request = {mode: "devices", endpoint_a: "a", endpoint_b: "b"};
      Object.assign(dac.candidates[0], {
        speed_gbps: 10, cable_options: {DAC: 3},
        assembly_options: [{part: "MA-CBL-TA-1M", length_m: 1}, {part: "MA-CBL-TA-3M", length_m: 3}],
      });
    } else {
      Object.assign(dac.candidates[0], {assembly_part: "MA-CBL-TA-3M", assembly_length_m: 3});
    }
    page.render(dac);
    const dacLinks = linksIn(page.element("#candidates"));
    assert.equal(dacLinks.length, browse ? 2 : 1);
    assert.ok(dacLinks.every(link => link.href === "https://documentation.meraki.com/accessories"));
  }
  page.render(result([null, null]));
  assert.equal(linksIn(page.element("#candidates")).length, 0);
});

test("mixed copper connection only counts the pluggable optic", () => {
  const page = dashboard();
  page.render(result([null, "MA-SFP-1GB-TX"]));
  assert.match(page.element("#candidates").text, /1 x MA-SFP-1GB-TX/);
  assert.match(page.element("#candidates").text, /No transceiver needed/);
});

test("native copper needs no transceivers", () => {
  const page = dashboard();
  page.render(result([null, null]));
  assert.match(page.element("#candidates").text, /No transceivers needed/);
  assert.doesNotMatch(page.element("#candidates").text, /Parts needed:/);
});

test("DAC is shown as one fixed-length assembly, not two optics", () => {
  const page = dashboard();
  const data = result([null, null]);
  Object.assign(data.candidates[0], {assembly_part: "MA-CBL-TA-3M", assembly_length_m: 3});
  data.request.distance_m = 2;
  for (const options of Object.values(data.candidates[0].endpoint_connection_options)) {
    options[0].connection = "direct_attach";
  }
  page.render(data);
  assert.match(page.element("#candidates").text, /1 x MA-CBL-TA-3M/);
  assert.match(page.element("#candidates").text, /Required route: 2 m.*Assembly length: 3 m/);
  assert.doesNotMatch(page.element("#candidates").text, /native RJ45|2 x MA-CBL/);
});

test("alternatives keep option-specific installation requirements visible", () => {
  const page = dashboard();
  const data = result();
  data.candidates.push({...data.candidates[0], requirements: ["Check required attenuation."]});
  page.render(data);
  assert.equal(page.element("#status").text, "2 connection options found");
  assert.match(page.element("#candidates").text, /Check required attenuation/);
});

test("general copper installation guidance is collapsed and deduplicated in both modes", () => {
  const page = dashboard();
  for (const browse of [false, true]) {
    const data = result([null, null]);
    if (browse) data.request = {mode: "devices", endpoint_a: "a", endpoint_b: "b"};
    Object.assign(data.candidates[0], {
      cable: "RJ45", speed_gbps: 1, cable_options: {CAT6: 100, CAT7: 100, CAT8: 100},
      installation_checks: ["Verify shield continuity and termination.", "Cat8.2 is excluded."],
      requirements: ["Device A (WAN): Activate the selected port."],
    });
    data.candidates.push({...data.candidates[0], standard: "Alternative copper option"});
    page.render(data);
    assert.doesNotMatch(page.element("#candidates").text, /shield|Cat8.2/);
    assert.match(page.element("#candidates").text, /Activate the selected port/);
    assert.match(page.element("#next").text, /shield continuity.*Cat8.2.*Verify firmware/);
    assert.equal(page.element("#next").children.length, 3);
    assert.equal(page.element("#technical-details").open, false);
    assert.match(page.element("#json").text, /shield continuity/);
  }
  page.render(result());
  assert.doesNotMatch(page.element("#next").text, /shield|Cat8.2/);
});

test("no match explains the limitation and clears previous cards", () => {
  const page = dashboard();
  page.render(result());
  page.element("#technical-details").open = true;
  page.render(result([], {candidates: [], exclusions: ["1000BASE-T: 101m exceeds the catalog's 100m limit."]}));
  assert.equal(page.element("#status").text, "No connection option found");
  assert.match(page.element("#message").text, /101m exceeds/);
  assert.equal(page.element("#candidates").children.length, 0);
  assert.equal(page.element("#technical-details").open, false);
});
