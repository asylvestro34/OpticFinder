"""Conservative planning against a bundled, manually curated catalog."""

import json
import math
from pathlib import Path

from .matrix import link_profiles, load_matrix, profile_parts


def load_catalog() -> dict:
    catalog = json.loads(Path(__file__).with_name("catalog.json").read_text(encoding="utf-8"))
    matrix = load_matrix()
    catalog["endpoints"].sort(key=lambda endpoint: (
        endpoint["kind"] != "switch", endpoint["label"]
    ))
    catalog["connection_profiles"] = link_profiles(
        matrix, catalog["endpoints"], catalog["additional_accessories"]
    )
    catalog["matrix_coverage"] = {
        "source_url": matrix["source_url"],
        "retrieved_on": matrix["retrieved_on"],
        "accessory_count": len(matrix["accessories"]),
        "additional_accessory_count": len(catalog["additional_accessories"]),
        "families": sorted({
            family for accessory in matrix["accessories"]
            for qualification in accessory["qualifications"] for family in qualification["families"]
        }),
        "modeled_device_count": len(catalog["endpoints"]),
        "scope": matrix["scope"],
        "exclusions": matrix["exclusions"],
    }
    for source in catalog["sources"]:
        if source["id"] == "meraki-accessories":
            source["retrieved_on"] = matrix["retrieved_on"]
    return catalog


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError(f"{name} must be a positive finite number.")
    try:
        number = float(value)
    except (ValueError, OverflowError):
        raise ValueError(f"{name} must be a positive finite number.") from None
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be a positive finite number.")
    return number


def _combine_cable_options(candidates: list[dict]) -> list[dict]:
    grouped = []
    for candidate in candidates:
        candidate = {**candidate, "cable_options": dict(candidate["cable_options"])}
        if "assembly_part" in candidate:
            candidate["assembly_options"] = [{
                "part": candidate.pop("assembly_part"),
                "length_m": candidate.pop("assembly_length_m"),
            }]
        connection = {key: value for key, value in candidate.items()
                      if key not in {"cable_options", "sources", "assembly_options"}}
        for existing in grouped:
            if ("assembly_options" in candidate) != ("assembly_options" in existing):
                continue
            if connection != {key: value for key, value in existing.items()
                              if key not in {"cable_options", "sources", "assembly_options"}}:
                continue
            if "assembly_options" in candidate:
                for assembly in candidate["assembly_options"]:
                    if assembly not in existing["assembly_options"]:
                        existing["assembly_options"].append(assembly)
                existing["assembly_options"].sort(key=lambda assembly: (assembly["length_m"], assembly["part"]))
                for grade, reach in candidate["cable_options"].items():
                    existing["cable_options"][grade] = max(existing["cable_options"].get(grade, 0), reach)
            elif any(grade in existing["cable_options"] and existing["cable_options"][grade] != reach
                     for grade, reach in candidate["cable_options"].items()):
                continue
            else:
                existing["cable_options"].update(candidate["cable_options"])
            existing["sources"] = list(dict.fromkeys([*existing["sources"], *candidate["sources"]]))
            break
        else:
            grouped.append(candidate)
    return grouped


def plan(request: dict) -> dict:
    """Return candidates, never infer host qualification from optic specifications."""
    if not isinstance(request, dict):
        raise ValueError("Request must be a JSON object.")
    common = {"endpoint_a", "endpoint_b", "interface_a", "interface_b",
              "speed_gbps", "distance_m"}
    fields = ("endpoint_a", "endpoint_b")
    browse = request.get("mode") == "devices"
    cable_fields = set(request) & {"fiber", "cable_type"}
    required = set(fields) | {"mode"} if browse else common | cable_fields
    if (not required <= set(request) or set(request) - required
            or (not browse and len(cable_fields) != 1)):
        if browse:
            raise ValueError("Device-only mode requires only mode, endpoint_a and endpoint_b.")
        raise ValueError("Provide endpoint_a, endpoint_b, speed_gbps, distance_m and cable_type; "
                         "interface_a and interface_b are required. Only Meraki endpoints are supported.")
    catalog = load_catalog()
    endpoints = {item["id"]: item for item in catalog["endpoints"]}
    selected = {}
    for field in fields:
        if not isinstance(request[field], str) or request[field] not in endpoints:
            raise ValueError(f"Unknown {field}; choose a model from the catalog.")
        endpoint = endpoints[request[field]]
        if endpoint["vendor"] != "Meraki":
            raise ValueError("Only Meraki endpoints are supported.")
        selected[field] = endpoint
    if not browse:
        speed = _number(request["speed_gbps"], "speed_gbps")
        distance = _number(request["distance_m"], "distance_m")
        cable_field = next(iter(cable_fields))
        fiber = request[cable_field]
        cable_types = {entry["id"] for entry in catalog["cable_types"]}
        if not isinstance(fiber, str) or fiber.upper() not in cable_types:
            raise ValueError(f"cable_type must be one of: {', '.join(sorted(cable_types))}.")
        fiber = fiber.upper()
        if cable_field == "fiber" and not fiber.startswith(("OM", "OS")):
            raise ValueError("Use cable_type for copper and DAC; fiber must be an OM or OS grade.")
    interfaces = {}
    for field, key in zip(fields, ("interface_a", "interface_b")):
        choices = selected[field].get("interfaces", [])
        if browse:
            interfaces[field] = choices
            continue
        interface_id = request[key]
        if not isinstance(interface_id, str) or interface_id not in {
            item["id"] for item in choices
        }:
            raise ValueError(f"Unknown {key}; choose an interface group for the selected device.")
        interfaces[field] = [next(item for item in choices if item["id"] == interface_id)]
    candidates = []
    matched_sources = set()
    exclusions = []
    for profile in catalog["connection_profiles"]:
        if any(endpoint["id"] not in profile["endpoint_ids"] for endpoint in selected.values()):
            continue
        if any(not any(endpoint["id"] in group for endpoint in selected.values())
               for group in profile.get("endpoint_groups", [])):
            continue
        if browse:
            speed = profile["speed_gbps"]
        else:
            reach = profile["reach_m"].get(fiber)
            if profile["speed_gbps"] != speed or reach is None:
                continue
            if distance > reach:
                exclusions.append(f"{profile['standard']}: {distance:g}m exceeds the catalog's {reach:g}m limit.")
                continue
            if distance < profile.get("minimum_distance_m", 0):
                exclusions.append(
                    f"{profile['standard']}: requires at least {profile['minimum_distance_m']:g}m of cable."
                )
                continue
        options = {}
        for field, endpoint in selected.items():
            choices = interfaces[field]
            options[field] = [
                {
                    "interface_group": item["id"],
                    "interface_label": item["label"],
                    "connection": (
                        "direct_attach" if profile["media"] == "direct_attach" else
                        "native_rj45" if item["kind"] == "rj45" else "transceiver"
                    ),
                    "part": (
                        None if profile["media"] == "direct_attach" else
                        profile_parts(profile, endpoint["id"])[item["kind"]]
                    ),
                }
                for item in choices
                if speed in item["speeds_gbps"]
                and item["kind"] in profile_parts(profile, endpoint["id"])
            ]
        if any(not values for values in options.values()):
            if not browse:
                exclusions.append(f"{profile['standard']}: a selected interface cannot provide this medium/speed.")
            continue
        candidates.append({
            "standard": profile["standard"],
            "endpoint_connection_options": options,
            "endpoint_optic_candidates": {
                field: values[0]["part"] if len(values) == 1 else None
                for field, values in options.items()
            },
            "cable": profile["connector"] if browse else f"{fiber}, {profile['connector']}",
            "wavelength_nm": profile["wavelength_nm"],
            **({
                "speed_gbps": speed,
                "cable_options": profile["reach_m"],
                "minimum_distance_m": profile.get("minimum_distance_m", 0),
            } if browse else {"documented_profile_reach_m": reach}),
            "catalog_endpoint_match": "documented",
            "sources": profile["sources"],
            "requirements": list(dict.fromkeys([
                *profile.get("requirements", []),
                *(f"{'Device A' if field == 'endpoint_a' else 'Device B'}"
                  f"{' (' + item['label'] + ')' if browse else ''}: {requirement}"
                  for field, endpoint in selected.items()
                  for item in interfaces[field]
                  if item["id"] in {option["interface_group"] for option in options[field]}
                  for requirement in [
                      *item.get("requirements", []),
                      *(endpoint.get("wan_requirements", [])
                        if item.get("role") == "wan" else []),
                  ]),
            ])),
            **({
                "assembly_part": profile["assembly_part"],
                "assembly_length_m": profile["assembly_length_m"],
            } if "assembly_part" in profile else {}),
        })
        matched_sources.update(profile["sources"])
    if browse:
        candidates = _combine_cable_options(candidates)
    next_steps = []
    for field in fields:
        next_steps.append(
            f"{field}: verify the physical port, current Meraki firmware and accessory "
            "restrictions in the public Meraki documentation. Port groups do not specify a physical port."
        )
    next_steps.extend([
        ("Choose one port option at each end and a listed cable grade. Verify route length, "
         "minimum reach, channel certification or fiber loss budget, polarity and port settings."
         if browse else
         "Verify channel certification, total length including patch leads and port negotiation settings."
         if fiber.startswith("CAT") else
         "Use the listed integrated DAC assembly; no separate transceivers are needed."
         if fiber == "DAC" else
         "Verify both optics' specifications, link loss budget, fiber path, polarity and port settings."),
        "Validate the complete link in a lab before purchasing or deploying.",
    ])
    source_ids = {source for endpoint in selected.values() for source in endpoint["sources"]}
    source_ids.update(matched_sources)
    status = "not_verified" if candidates else "no_catalog_match"
    return {
        "status": status,
        "request": dict(request) if browse else {
            **request, "speed_gbps": speed, "distance_m": distance, cable_field: fiber
        },
        "endpoint_support": {field: "not_verified" for field in fields},
        "link_interoperability": "not_verified",
        "candidates": candidates,
        "message": (
            "Provisional connection options only. Not a validated end-to-end parts list."
            if candidates else
            "No connection profile in this limited catalog matches these requirements. "
            "This does not establish that a compatible solution does not exist."
        ),
        "next_steps": next_steps,
        "exclusions": exclusions,
        "sources": [source for source in catalog["sources"] if source["id"] in source_ids],
    }
