"use strict";
const form = document.querySelector("#planner");
const button = form.querySelector("button");
const error = document.querySelector("#error");
const requirements = document.querySelector("#link-requirements");
const compatibilityMessage = document.querySelector("#compatibility");
let catalog;
let submitting = false;

async function getJSON(url, options) {
  const response = await fetch(url, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
  return body;
}

function populateSelect(select, choices, placeholder) {
  const options = choices.map((choice) => new Option(choice.label, String(choice.id)));
  if (choices.length !== 1) options.unshift(new Option(placeholder, ""));
  select.replaceChildren(...options);
  select.value = choices.length === 1 ? String(choices[0].id) : "";
}

function updateInterfaces(endpointField) {
  const interfaceField = endpointField === "endpoint_a" ? "interface_a" : "interface_b";
  const interfaceSelect = form.elements.namedItem(interfaceField);
  const endpoint = catalog.endpoints.find(
    (item) => item.id === form.elements.namedItem(endpointField).value
  );
  populateSelect(interfaceSelect, endpoint?.interfaces || [], "Select an interface group");
  interfaceSelect.disabled = !endpoint;
}

async function initialize() {
  try {
    catalog = await getJSON("/api/catalog");
    for (const field of ["endpoint_a", "endpoint_b"]) {
      populateSelect(form.elements.namedItem(field), catalog.endpoints, "Select a device");
      updateInterfaces(field);
    }
    for (const field of ["endpoint_a", "endpoint_b"]) {
      form.elements.namedItem(field).addEventListener("change", () => {
        updateInterfaces(field);
        updatePlanningOptions();
      });
    }
    for (const field of ["interface_a", "interface_b"]) {
      form.elements.namedItem(field).addEventListener("change", updatePlanningOptions);
    }
    form.elements.namedItem("speed_gbps").addEventListener("change", updateCableTypes);
    document.querySelector("#cable-family").addEventListener("change", updateCableGrades);
    form.elements.namedItem("cable_type").addEventListener("change", updateSubmitState);
    form.elements.namedItem("distance_m").addEventListener("input", updateSubmitState);
    updatePlanningOptions();
  } catch (err) {
    error.textContent = `Unable to load catalog: ${err.message}`;
  }
}

function selectedInterfaces() {
  return ["endpoint_a", "endpoint_b"].map((field, index) => {
    const endpoint = catalog.endpoints.find((item) => item.id === form.elements.namedItem(field).value);
    const interfaceField = index === 0 ? "interface_a" : "interface_b";
    const selectedInterface = endpoint?.interfaces.find(
      (item) => item.id === form.elements.namedItem(interfaceField).value
    );
    return {endpoint, selectedInterface};
  });
}

function profilesForSelection() {
  const selections = selectedInterfaces();
  if (selections.some(({endpoint, selectedInterface}) => !endpoint || !selectedInterface)) return [];
  return catalog.connection_profiles.filter((profile) =>
    selections.every(({endpoint, selectedInterface}) =>
      profile.endpoint_ids.includes(endpoint.id)
      && selectedInterface.speeds_gbps.includes(profile.speed_gbps)
      && Object.hasOwn(
        profile.parts_by_endpoint ? (profile.parts_by_endpoint[endpoint.id] || {})
          : profile.parts_by_port_kind, selectedInterface.kind
      )
    )
    && (profile.endpoint_groups || []).every((group) =>
      selections.some(({endpoint}) => group.includes(endpoint.id))
    )
  );
}

function updatePlanningOptions() {
  document.querySelector("#result").hidden = true;
  error.textContent = "";
  selectedInterfaces().forEach(({endpoint, selectedInterface}, index) => {
    document.querySelector(`#device-notes-${index === 0 ? "a" : "b"}`).textContent = [
      ...(endpoint?.end_of_sale ? [`Published end of sale: ${endpoint.end_of_sale}.`] : []),
      ...(selectedInterface?.requirements || []),
      ...(selectedInterface?.role === "wan" ? (endpoint.wan_requirements || []) : []),
    ].join(" ");
  });
  const speedSelect = form.elements.namedItem("speed_gbps");
  const cableSelect = form.elements.namedItem("cable_type");
  const profiles = profilesForSelection();
  requirements.hidden = profiles.length === 0;
  requirements.disabled = profiles.length === 0;
  populateSelect(speedSelect, [], "Select a speed");
  populateSelect(cableSelect, [], "Select a cable type");
  populateSelect(document.querySelector("#cable-family"), [], "Select a cable family");
  cableSelect.disabled = true;
  if (!profiles.length) {
    const endpointsSelected = ["endpoint_a", "endpoint_b"].every(
      (field) => form.elements.namedItem(field).value
    );
    const interfacesSelected = ["interface_a", "interface_b"].every(
      (field) => form.elements.namedItem(field).value
    );
    compatibilityMessage.textContent = endpointsSelected && interfacesSelected
      ? "Those port groups have no matching option in the current catalog. Try another device or port-group combination."
      : "Choose a device and port group at each end to see available link options.";
    updateSubmitState();
    return;
  }
  compatibilityMessage.textContent = "Choose a speed, cable type, and total cable length.";
  const speeds = [...new Set(profiles.map((profile) => profile.speed_gbps))].sort((a, b) => a - b);
  populateSelect(speedSelect, speeds.map((speed) => ({id: speed, label: String(speed)})), "Select a speed");
  updateCableTypes();
}

function updateCableTypes() {
  const choices = availableCableTypes();
  populateSelect(document.querySelector("#cable-family"),
    [
      {id: "OM", label: "Multimode"},
      {id: "OS", label: "Single Mode"},
      {id: "CAT", label: "Copper Ethernet"},
      {id: "DAC", label: "Direct Attach (DAC)"},
    ].filter((family) => choices.some((choice) => choice.id.startsWith(family.id))),
    "Select a cable family");
  updateCableGrades();
}

function availableCableTypes() {
  const speed = Number(form.elements.namedItem("speed_gbps").value);
  const profiles = profilesForSelection().filter((profile) => profile.speed_gbps === speed);
  const cableIds = new Set(profiles.flatMap((profile) => Object.keys(profile.reach_m)));
  return catalog.cable_types.filter((item) => cableIds.has(item.id));
}

function updateCableGrades() {
  const family = document.querySelector("#cable-family").value;
  const cableSelect = form.elements.namedItem("cable_type");
  populateSelect(cableSelect, family
    ? availableCableTypes().filter((item) => item.id.startsWith(family)) : [],
  "Select a cable type / grade");
  cableSelect.disabled = !family;
  updateSubmitState();
}

function updateSubmitState() {
  document.querySelector("#result").hidden = true;
  button.disabled = submitting || !form.elements.namedItem("speed_gbps").value
    || !form.elements.namedItem("cable_type").value
    || !form.elements.namedItem("distance_m").value
    || requirements.disabled;
}

function textElement(tag, text, className) {
  const element = document.createElement(tag);
  element.textContent = text;
  if (className) element.className = className;
  return element;
}

function renderResult(result) {
  const hasMatches = result.candidates.length > 0;
  document.querySelector("#status").textContent = hasMatches
    ? `${result.candidates.length === 1 ? "Connection option" : `${result.candidates.length} connection options`} found`
    : "No connection option found";
  document.querySelector("#message").textContent = hasMatches
    ? "Matches the documented catalog for your selections."
    : "No option in the current catalog meets these selections. "
      + (result.exclusions[0] || "Try a different speed, cable type, or length.");
  const request = result.request;
  const cableType = request.cable_type || request.fiber;
  document.querySelector("#connection-summary").textContent =
    `${request.speed_gbps} Gbps | ${cableType} | ${request.distance_m} m required`;
  const candidateContainer = document.querySelector("#candidates");
  candidateContainer.replaceChildren();
  for (const candidate of result.candidates) {
    const article = document.createElement("article");
    article.className = "connection-option";
    article.append(textElement("h3", candidate.standard));
    const endpoints = document.createElement("div");
    endpoints.className = "result-endpoints";
    const parts = new Map();
    for (const [field, label] of [["endpoint_a", "Device A"], ["endpoint_b", "Device B"]]) {
      const endpoint = catalog.endpoints.find((item) => item.id === request[field]);
      const card = document.createElement("div");
      card.className = "result-device";
      card.append(textElement("h4", label), textElement("p", endpoint.label, "device-name"));
      for (const option of candidate.endpoint_connection_options[field]) {
        const description = option.connection === "direct_attach"
          ? "Integrated DAC connector"
          : option.part || "No transceiver needed";
        card.append(
          textElement("p", option.interface_label, "port-description"),
          textElement("p", description, "part-number")
        );
        if (option.part) parts.set(option.part, (parts.get(option.part) || 0) + 1);
      }
      endpoints.append(card);
    }
    article.append(endpoints);
    article.append(textElement("p", candidate.assembly_part
      ? `Parts needed: 1 x ${candidate.assembly_part} (${candidate.assembly_length_m} m integrated cable). No separate optics needed.`
      : parts.size
        ? `Parts needed: ${[...parts].map(([part, quantity]) => `${quantity} x ${part}`).join(", ")}, plus the cable below.`
        : "No transceivers needed. Use the cable below.",
    "parts-summary"));
    article.append(textElement("p", candidate.assembly_part
      ? `Required route: ${request.distance_m} m | Assembly length: ${candidate.assembly_length_m} m`
      : `Cable: ${cableType} | Selected length: ${request.distance_m} m | Max length: ${candidate.documented_profile_reach_m} m`,
    "cable-summary"));
    if (!candidate.assembly_part) {
      article.append(textElement("p", candidate.cable, "port-description"));
    }
    for (const requirement of candidate.requirements) {
      article.append(textElement("p", requirement, "connection-requirement"));
    }
    candidateContainer.append(article);
  }
  document.querySelector("#exclusions").replaceChildren(
    ...(result.exclusions.length ? result.exclusions : ["None for these selections."])
      .map((text) => textElement("li", text))
  );
  document.querySelector("#next").replaceChildren(
    ...result.next_steps.map((text) => textElement("li", text))
  );
  document.querySelector("#sources").replaceChildren(...result.sources.map((source) => {
    const li = document.createElement("li");
    const link = textElement("a", source.title);
    link.href = source.url;
    link.rel = "noreferrer";
    li.append(link, ` - ${source.state}; reviewed: ${source.reviewed_on || "not yet"}. ${source.scope}`);
    return li;
  }));
  document.querySelector("#technical-details").open = false;
  document.querySelector("#json").textContent = JSON.stringify(result, null, 2);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  error.textContent = "";
  document.querySelector("#result").hidden = true;
  submitting = true;
  button.disabled = true;
  let completed = false;
  try {
    const result = await getJSON("/api/plan", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(Object.fromEntries(new FormData(form))),
    });
    renderResult(result);
    completed = true;
  } catch (err) {
    error.textContent = err.message;
  } finally {
    submitting = false;
    updateSubmitState();
    document.querySelector("#result").hidden = !completed;
  }
});

initialize();
