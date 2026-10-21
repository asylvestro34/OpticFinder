const {test} = require("node:test");
const assert = require("node:assert/strict");
const {readFileSync} = require("node:fs");
const {join} = require("node:path");
const vm = require("node:vm");

class Element {
  constructor() {
    this.children = [];
    this.textContent = "";
  }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  addEventListener() {}
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
