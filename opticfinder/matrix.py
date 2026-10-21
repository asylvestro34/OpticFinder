"""Import factual accessory-table records from public Meraki documentation."""

import json
import re
from itertools import combinations
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import urlopen


MATRIX_URL = (
    "https://documentation.meraki.com/Platform_Management/Product_Information/"
    "Overviews_and_Datasheets/Small-Form_Factor_Pluggable_(SFP)_and_Stacking_Accessories"
)
SNAPSHOT_PATH = Path(__file__).with_name("meraki_matrix.json")


class AccessoryTables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables = []
        self.depth = 0
        self.rows = []
        self.row = []
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.depth += 1
            if self.depth == 1:
                self.rows = []
        if self.depth and tag == "tr":
            self.row = []
        if self.depth and tag in {"th", "td"}:
            self.cell = []
        if self.cell is not None and tag == "br":
            self.cell.append(" ")
        if self.depth and tag in {"th", "td"}:
            if any(name in {"rowspan", "colspan"} and value != "1" for name, value in attrs):
                raise ValueError("Merged accessory-table cells require review before importing.")

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in {"th", "td"} and self.cell is not None:
            self.row.append(" ".join(" ".join(self.cell).split()))
            self.cell = None
        if self.depth and tag == "tr" and self.row:
            self.rows.append(self.row)
        if tag == "table":
            self.depth -= 1
            if self.depth == 0:
                self.tables.append(self.rows)


def _distance_values(text):
    values = re.findall(r"(\d+(?:\.\d+)?)\s*(km|cm|m)\b", text)
    if not values:
        raise ValueError(f"Unrecognized accessory distance: {text}")
    return [float(value) * {"km": 1000, "cm": .01, "m": 1}[unit] for value, unit in values]


def _families(compatibility):
    return sorted(set(re.findall(
        r"\b(?:MS\d+(?:-[A-Z0-9]+)?|MX\d+|C\d+(?:-[A-Z0-9]+)*)\b",
        compatibility,
    )))


def parse_matrix(html, retrieved_on):
    parser = AccessoryTables()
    parser.feed(html)
    records = {}
    for table in parser.tables:
        if not table:
            continue
        headers = table[0]
        optical = "Fiber Description" in headers and "Compatibility" in headers
        direct_attach = "Assembly Type" in headers and any(
            "10GSFP+Cu" in row for row in table[1:]
        )
        if not optical and not direct_attach:
            continue
        for row in table[1:]:
            if len(row) != len(headers):
                raise ValueError("Accessory table columns changed; review the source before importing.")
            data = dict(zip(headers, row))
            part = re.sub(r"\s+|\*", "", data["Meraki Product ID"])
            speed_text = data["Data Rate"]
            speed_match = re.fullmatch(r"(?:(\d+)\s+)?Gigabit", speed_text)
            if not speed_match:
                raise ValueError(f"Unrecognized data rate for {part}: {speed_text}")
            speed = int(speed_match.group(1) or 1)
            compatibility = data["Compatibility"]
            record = records.setdefault(part, {
                "part": part,
                "standard": data["Standard"],
                "speed_gbps": speed,
                "media": "direct_attach" if direct_attach else (
                    "copper" if data["Standard"] == "1000BASE-T" else "fiber"
                ),
                "port_kind": "qsfp" if part.startswith("MA-QSFP") else "sfp",
                "reach_m": {},
                "qualifications": [],
                "sources": ["meraki-accessories"],
            })
            qualification = {"compatibility": compatibility, "families": _families(compatibility)}
            if direct_attach:
                record["assembly_length_m"] = _distance_values(data["Cable Length"])[0]
                record["connector"] = "Integrated SFP+ passive twinax cable"
                record["reach_m"] = {"DAC": record["assembly_length_m"]}
                record["wavelength_nm"] = None
            else:
                description = data["Fiber Description"]
                qualification["fiber_description"] = description
                qualification["documented_distance"] = data["Max Distance"]
                wavelength = data["Wavelength (nm)"]
                record["wavelength_nm"] = int(wavelength) if wavelength.isdigit() else (
                    None if wavelength == "N/A" else wavelength
                )
                record["connector"] = (
                    "RJ45" if record["media"] == "copper" else
                    "MPO12; verify fiber count and polarity"
                    if "MPO12" in data["Standard"] or part == "MA-QSFP-100G-SR4" else
                    "Duplex LC; verify connector polish"
                )
                distances = _distance_values(data["Max Distance"])
                if record["media"] == "copper":
                    reach = dict.fromkeys(("CAT5E", "CAT6", "CAT6A"), distances[0])
                elif "mode conditioning" in description:
                    # Retain the qualification without treating ordinary MMF as a match.
                    reach = {}
                    qualification["requires"] = "LC mode-conditioning cable; not modeled by the planner"
                else:
                    grades = re.findall(r"\b(?:OM[1-5]|OS[12])\b", description)
                    if not grades:
                        raise ValueError(f"Unrecognized fiber description for {part}: {description}")
                    if len(distances) == 1:
                        reach = dict.fromkeys(grades, distances[0])
                    elif len(grades) == len(distances):
                        reach = dict(zip(grades, distances))
                    elif grades == ["OM3", "OM4", "OM5"] and len(distances) == 2:
                        reach = {"OM3": distances[0], "OM4": distances[1], "OM5": distances[1]}
                    else:
                        raise ValueError(f"Ambiguous fiber reaches for {part}: {description}")
                qualification["reach_m"] = reach
                for grade, distance in reach.items():
                    previous = record["reach_m"].get(grade)
                    if previous is not None and previous != distance:
                        raise ValueError(f"Conflicting reach for {part}, {grade}")
                    record["reach_m"][grade] = distance
            record["qualifications"].append(qualification)
    if not records:
        raise ValueError("No optical or direct-attach accessory tables found.")
    return {
        "source_url": MATRIX_URL,
        "retrieved_on": retrieved_on,
        "scope": "Meraki-branded transceivers and data-port DACs in the public accessory tables",
        "exclusions": [
            "Not the complete Cisco TMG matrix; Cisco-branded optics are not imported.",
            "Stacking, StackPower cables and uplink modules are not data-link optics.",
            "Family qualifications do not define the physical ports of each device model.",
            "C9300 listings apply to cloud-managed Meraki deployments only.",
            "MA-SFP-1GB-TX excludes MS130R, MS390 and C9300/X/L.",
            "MA-SFP-10GB-LRM excludes C9300X; OM2 requires 500 MHz/km modal bandwidth.",
            "MA-SFP-10GB-ER has additional MS125 compatibility guidance.",
            "Mode-conditioned LX10 over multimode fiber requires separate cabling modeling.",
        ],
        "accessories": sorted(records.values(), key=lambda item: item["part"]),
    }


def refresh_matrix():
    with urlopen(MATRIX_URL, timeout=30) as response:
        html = response.read().decode("utf-8")
    snapshot = parse_matrix(html, datetime.now(timezone.utc).date().isoformat())
    if SNAPSHOT_PATH.exists():
        previous = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        previous_parts = {item["part"] for item in previous["accessories"]}
        imported_parts = {item["part"] for item in snapshot["accessories"]}
        missing = previous_parts - imported_parts
        if missing:
            raise ValueError(
                "Refresh omitted previously imported accessories; review the source before replacing "
                f"the snapshot: {', '.join(sorted(missing))}"
            )
    # Parse completely before replacing the snapshot; failed imports leave it untouched.
    temporary = SNAPSHOT_PATH.with_suffix(".json.tmp")
    try:
        temporary.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
        temporary.replace(SNAPSHOT_PATH)
    finally:
        temporary.unlink(missing_ok=True)
    return snapshot


def load_matrix():
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


def profiles_for_endpoints(matrix, endpoints):
    profiles = []
    for accessory in matrix["accessories"]:
        eligible = []
        for endpoint in endpoints:
            families = set(endpoint["matrix_families"])
            reaches = {}
            for qualification in accessory["qualifications"]:
                compatibility = qualification["compatibility"]
                supported = bool(families.intersection(qualification["families"]))
                if accessory["part"] == "MA-SFP-1GB-TX":
                    supported = (
                        (
                            any(re.fullmatch(r"MS\d+(?:-X)?", family) for family in families)
                            and not families.intersection({"MS130R", "MS390"})
                            and "All MSes" in compatibility
                        )
                        or (
                            any(re.fullmatch(r"MX\d+", family) for family in families)
                            and "All MXes" in compatibility
                        )
                    )
                if accessory["part"] == "MA-SFP-10GB-LRM" and "C9300X" in families:
                    supported = False
                if supported:
                    reaches.update(qualification.get("reach_m", accessory["reach_m"]))
            if reaches:
                eligible.append((endpoint["id"], reaches))
        # Different qualifications can have different media by family (for example LRM).
        for cable in accessory["reach_m"]:
            by_reach = {}
            for endpoint_id, reaches in eligible:
                if cable in reaches:
                    by_reach.setdefault(reaches[cable], []).append(endpoint_id)
            for reach, endpoint_ids in by_reach.items():
                profile = {
                    "id": f"{accessory['part']}-{cable}-{reach:g}",
                    "standard": accessory["standard"],
                    "speed_gbps": accessory["speed_gbps"],
                    "media": accessory["media"],
                    "parts_by_port_kind": {accessory["port_kind"]: accessory["part"]},
                    "endpoint_ids": endpoint_ids,
                    "reach_m": {cable: reach},
                    "wavelength_nm": accessory["wavelength_nm"],
                    "connector": accessory["connector"],
                    "sources": accessory["sources"],
                }
                if "minimum_distance_m" in accessory:
                    profile["minimum_distance_m"] = accessory["minimum_distance_m"]
                if accessory.get("requirements"):
                    profile["requirements"] = accessory["requirements"]
                if accessory["part"] in {"MA-SFP-10GB-ER", "MA-SFP-10GB-ZR"}:
                    profile["requirements"] = [
                        "Check transmit/receive power and required attenuation before using long-reach optics."
                    ]
                if accessory["part"] == "MA-SFP-10GB-LRM" and cable == "OM2":
                    profile["requirements"] = ["OM2 modal bandwidth must be 500 MHz/km."]
                if accessory["media"] == "direct_attach":
                    profile["assembly_part"] = accessory["part"]
                    profile["assembly_length_m"] = accessory["assembly_length_m"]
                profiles.append(profile)
    return sorted(profiles, key=lambda profile: max(profile["reach_m"].values()))


def link_profiles(matrix, endpoints, additional_accessories):
    """Combine documented modules with native ports, without qualifying an optic by inference."""
    profiles = profiles_for_endpoints(
        {**matrix, "accessories": [*matrix["accessories"], *additional_accessories]}, endpoints
    )
    copper = [profile for profile in profiles if profile["media"] == "copper"]
    profiles = [profile for profile in profiles if profile["media"] != "copper"]
    for speed in (1, 2.5, 5):
        grades = ("CAT5E", "CAT6", "CAT6A", "CAT7", "CAT8")
        for grade in grades:
            parts_by_endpoint = {}
            sources = {"copper-rule", "fluke-copper-categories", "fluke-class-f"}
            if speed > 1:
                sources.add("cisco-mgig-cabling")
            for profile in copper:
                qualification_grade = "CAT6A" if grade in {"CAT7", "CAT8"} else grade
                if profile["speed_gbps"] != speed or qualification_grade not in profile["reach_m"]:
                    continue
                for endpoint_id in profile["endpoint_ids"]:
                    parts_by_endpoint.setdefault(endpoint_id, {}).update(profile["parts_by_port_kind"])
                sources.update(profile["sources"])
            for endpoint in endpoints:
                if any(group["kind"] == "rj45" and speed in group["speeds_gbps"]
                       for group in endpoint["interfaces"]):
                    parts_by_endpoint.setdefault(endpoint["id"], {})["rj45"] = None
            if parts_by_endpoint:
                profiles.append({
                    "id": f"native-and-qualified-copper-{speed:g}-{grade}",
                    "standard": {1: "1000BASE-T", 2.5: "2.5GBASE-T", 5: "5GBASE-T"}[speed],
                    "speed_gbps": speed, "media": "copper",
                    "endpoint_ids": sorted(parts_by_endpoint),
                    "parts_by_endpoint": parts_by_endpoint,
                    "parts_by_port_kind": {"rj45": None},
                    "reach_m": {grade: 100}, "wavelength_nm": None, "connector": "RJ45",
                    "sources": sorted(sources),
                    "installation_checks": [
                        "For Cat7 or Cat8, verify shield continuity and correct shield termination.",
                        "Cat7 must form an RJ45-compatible channel meeting the selected Ethernet "
                        "application requirements; Cat7 labeling alone does not establish Class F performance.",
                        "Use RJ45-compatible TIA Cat8 or ISO Cat8.1, not Cat8.2. "
                        "The listed 100m reach applies only to the selected lower-speed application, "
                        "not 25GBASE-T or 40GBASE-T.",
                    ],
                })
    # Only the explicitly documented rugged alternatives need mixed-part optical profiles.
    optical = [profile for profile in profiles if profile["media"] == "fiber"]
    for left, right in combinations(optical, 2):
        if ("cisco-ge-sfp" in left["sources"]) == ("cisco-ge-sfp" in right["sources"]):
            continue
        standards = {left["standard"], right["standard"]}
        if len(standards) != 1 and standards != {"1000BASE-LX10", "1000BASE-LX/LH"}:
            continue
        if (left["speed_gbps"] != right["speed_gbps"]
                or left["wavelength_nm"] != right["wavelength_nm"]
                or left["connector"] != right["connector"]):
            continue
        grades = left["reach_m"].keys() & right["reach_m"].keys()
        if not grades:
            continue
        profiles.append({
            **left,
            "id": f"{left['id']}-with-{right['id']}",
            "standard": left["standard"] if len(standards) == 1 else "1000BASE-LX/LH / LX10",
            "endpoint_ids": sorted(set(left["endpoint_ids"]) | set(right["endpoint_ids"])),
            "endpoint_groups": [left["endpoint_ids"], right["endpoint_ids"]],
            "parts_by_endpoint": {
                endpoint_id: profile["parts_by_port_kind"]
                for profile in (left, right) for endpoint_id in profile["endpoint_ids"]
            },
            "reach_m": {grade: min(left["reach_m"][grade], right["reach_m"][grade])
                        for grade in sorted(grades)},
            "minimum_distance_m": max(left.get("minimum_distance_m", 0),
                                      right.get("minimum_distance_m", 0)),
            "sources": sorted(set(left["sources"]) | set(right["sources"])),
            "requirements": [
                *left.get("requirements", []), *right.get("requirements", []),
                "Uses interoperable Gigabit optical standards with a different qualified module at each end. Verify the complete optical loss budget."
            ],
        })
    return sorted(profiles, key=lambda profile: max(profile["reach_m"].values()))


def profile_parts(profile, endpoint_id):
    return (profile["parts_by_endpoint"].get(endpoint_id, {})
            if "parts_by_endpoint" in profile else profile["parts_by_port_kind"])
