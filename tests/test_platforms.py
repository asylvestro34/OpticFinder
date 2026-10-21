import unittest
from datetime import date

from opticfinder.engine import load_catalog, plan
from opticfinder.matrix import load_matrix, parse_matrix, profile_parts


def link(a, group_a, b, group_b, speed, cable, distance=30):
    return plan({
        "endpoint_a": a, "interface_a": group_a,
        "endpoint_b": b, "interface_b": group_b,
        "speed_gbps": speed, "cable_type": cable, "distance_m": distance,
    })


class PlatformTests(unittest.TestCase):
    def test_complete_current_model_inventory_and_lifecycle(self):
        expected = {
            "ms130-8", "ms130-8p", "ms130-8p-i", "ms130-8x", "ms130-12x",
            "ms130-24", "ms130-24p", "ms130-24x", "ms130-48", "ms130-48p", "ms130-48x",
            "ms130r-8p", "ms450-12",
            "ms150-24t-4g", "ms150-24p-4g", "ms150-24t-4x", "ms150-24p-4x",
            "ms150-24mp-4x", "ms150-48t-4g", "ms150-48lp-4g", "ms150-48fp-4g",
            "ms150-48t-4x", "ms150-48lp-4x", "ms150-48fp-4x", "ms150-48mp-4x",
            "mx67", "mx67w", "mx67c", "mx68", "mx68w", "mx68cw", "mx75",
            "mx85", "mx95", "mx105", "mx250", "mx450",
        }
        catalog = load_catalog()
        self.assertEqual({endpoint["id"] for endpoint in catalog["endpoints"]}, expected)
        self.assertEqual(len(catalog["endpoints"]), len(expected))
        self.assertEqual(catalog["schema_version"], 6)
        reviewed = date.fromisoformat(catalog["platform_scope"]["reviewed_on"])
        for endpoint in catalog["endpoints"]:
            with self.subTest(model=endpoint["id"]):
                self.assertTrue(endpoint["sources"])
                self.assertEqual(endpoint["label"], f"Meraki {endpoint['id'].upper()}")
                self.assertGreaterEqual(date.fromisoformat(
                    endpoint.get("end_of_sale", "9999-12-31")), reviewed)
        self.assertEqual({
            endpoint["id"]: endpoint["end_of_sale"]
            for endpoint in catalog["endpoints"] if "end_of_sale" in endpoint
        }, {"ms450-12": "2026-10-29", "mx67c": "2026-11-27", "mx68cw": "2026-11-27"})

    def test_every_ms_port_group_matches_documented_counts_and_speeds(self):
        # Each tuple: 1G RJ45 count, multigigabit count/speeds, uplink count/speeds.
        expected = {
            "ms130-8": (8, 0, [], 2, [1]),
            "ms130-8p": (8, 0, [], 2, [1]),
            "ms130-8p-i": (8, 0, [], 2, [1]),
            "ms130-8x": (6, 2, [1, 2.5], 2, [1, 10]),
            "ms130-12x": (8, 4, [1, 2.5], 2, [1, 10]),
            "ms130-24": (24, 0, [], 4, [1]),
            "ms130-24p": (24, 0, [], 4, [1]),
            "ms130-24x": (18, 6, [1, 2.5], 4, [1, 10]),
            "ms130-48": (48, 0, [], 4, [1]),
            "ms130-48p": (48, 0, [], 4, [1]),
            "ms130-48x": (40, 8, [1, 2.5], 4, [1, 10]),
            "ms130r-8p": (8, 0, [], 2, [1]),
            "ms150-24t-4g": (24, 0, [], 4, [1]),
            "ms150-24p-4g": (24, 0, [], 4, [1]),
            "ms150-24t-4x": (24, 0, [], 4, [1, 10]),
            "ms150-24p-4x": (24, 0, [], 4, [1, 10]),
            "ms150-24mp-4x": (16, 8, [1, 2.5, 5], 4, [1, 10]),
            "ms150-48t-4g": (48, 0, [], 4, [1]),
            "ms150-48lp-4g": (48, 0, [], 4, [1]),
            "ms150-48fp-4g": (48, 0, [], 4, [1]),
            "ms150-48t-4x": (48, 0, [], 4, [1, 10]),
            "ms150-48lp-4x": (48, 0, [], 4, [1, 10]),
            "ms150-48fp-4x": (48, 0, [], 4, [1, 10]),
            "ms150-48mp-4x": (32, 16, [1, 2.5, 5], 4, [1, 10]),
        }
        endpoints = {endpoint["id"]: endpoint for endpoint in load_catalog()["endpoints"]}
        for model, (copper, mgig, mgig_speeds, uplinks, uplink_speeds) in expected.items():
            with self.subTest(model=model):
                groups = [("rj45-1g", "rj45", copper, [1])]
                if mgig:
                    groups.append(("rj45-mgig", "rj45", mgig, mgig_speeds))
                groups.append(("sfp-uplink", "sfp", uplinks, uplink_speeds))
                self.assertEqual([
                    (g["id"], g["kind"], g["port_count"], g["speeds_gbps"])
                    for g in endpoints[model]["interfaces"]
                ], groups)
        self.assertEqual([
            (g["kind"], g["port_count"], g["speeds_gbps"])
            for g in endpoints["ms450-12"]["interfaces"]
        ], [("qsfp", 12, [40]), ("qsfp", 2, [100])])

    def test_every_mx_port_group_counts_roles_and_speeds(self):
        small = [("rj45-lan", 3, [1], "lan"), ("rj45-wan", 1, [1], "wan"),
                 ("rj45-convertible", 1, [1], "lan_wan")]
        desktop = [("rj45-lan", 10, [1], "lan"), ("rj45-wan", 2, [1], "wan")]
        mid = [("rj45-lan", 4, [1], "lan"), ("sfp-lan", 2, [1, 10], "lan"),
               ("rj45-wan", 2, [1, 2.5], "wan"), ("sfp-wan", 2, [1, 10], "wan")]
        large = [("rj45-lan", 8, [1], "lan"), ("sfp-lan", 8, [1], "lan"),
                 ("sfp-plus-lan", 8, [10], "lan"), ("sfp-wan", 2, [10], "wan")]
        expected = {
            "mx67": small, "mx67w": small, "mx67c": small,
            "mx68": desktop, "mx68w": desktop, "mx68cw": desktop,
            "mx75": [*desktop, ("sfp-wan", 1, [1], "wan")],
            "mx85": [("rj45-lan", 8, [1], "lan"), ("sfp-lan", 2, [1], "lan"),
                     ("rj45-wan", 2, [1], "wan"), ("sfp-wan", 2, [1], "wan")],
            "mx95": mid, "mx105": mid, "mx250": large, "mx450": large,
        }
        for endpoint in load_catalog()["endpoints"]:
            if endpoint["kind"] != "security_appliance":
                continue
            with self.subTest(model=endpoint["id"]):
                self.assertEqual([
                    (g["id"], g["port_count"], g["speeds_gbps"], g["role"])
                    for g in endpoint["interfaces"]
                ], expected[endpoint["id"]])
                for group in endpoint["interfaces"]:
                    self.assertEqual(group["kind"], "sfp" if group["id"].startswith("sfp") else "rj45")

    def test_every_group_has_a_working_rated_speed_profile_and_valid_label(self):
        catalog = load_catalog()
        for endpoint in catalog["endpoints"]:
            for group in endpoint["interfaces"]:
                with self.subTest(model=endpoint["id"], group=group["id"]):
                    speed = max(group["speeds_gbps"])
                    self.assertTrue(group["label"].startswith(f"{group['port_count']} x {speed:g}G "))
                    self.assertFalse(any(word in group["label"].lower() for word in ("management", "stack")))
                    profiles = [
                        p for p in catalog["connection_profiles"]
                        if endpoint["id"] in p["endpoint_ids"]
                        and p["speed_gbps"] == speed
                        and group["kind"] in profile_parts(p, endpoint["id"])
                        and all(endpoint["id"] in ids for ids in p.get("endpoint_groups", []))
                    ]
                    self.assertTrue(profiles)
                    profile = profiles[0]
                    cable = next(iter(profile["reach_m"]))
                    self.assertTrue(link(endpoint["id"], group["id"], endpoint["id"], group["id"],
                                         speed, cable, min(30, profile["reach_m"][cable]))["candidates"])

    def test_mx_to_ms_and_mx_to_mx_fiber_and_dac(self):
        for a, group_a, b, group_b in (
            ("mx95", "sfp-lan", "ms150-24p-4x", "sfp-uplink"),
            ("mx105", "sfp-wan", "ms130-24x", "sfp-uplink"),
            ("mx250", "sfp-plus-lan", "mx450", "sfp-wan"),
        ):
            with self.subTest(a=a, b=b):
                fiber = link(a, group_a, b, group_b, 10, "OM3")
                self.assertEqual(fiber["candidates"][0]["endpoint_optic_candidates"],
                                 {"endpoint_a": "MA-SFP-10GB-SR", "endpoint_b": "MA-SFP-10GB-SR"})
                dac = link(a, group_a, b, group_b, 10, "DAC", 2)
                self.assertEqual([c["assembly_part"] for c in dac["candidates"]], ["MA-CBL-TA-3M"])
        for model, group in (("mx75", "sfp-wan"), ("mx85", "sfp-lan"), ("mx250", "sfp-lan")):
            self.assertTrue(link(model, group, "ms130-24p", "sfp-uplink", 1, "OM3")["candidates"])
            self.assertEqual(link(model, group, "ms130-24x", "sfp-uplink", 10, "OM3")["candidates"], [])

    def test_multigigabit_exact_reach_and_speed_boundaries(self):
        for a, group_a, b, group_b, speed in (
            ("ms130-24x", "rj45-mgig", "mx95", "rj45-wan", 2.5),
            ("ms150-24mp-4x", "rj45-mgig", "ms150-48mp-4x", "rj45-mgig", 5),
        ):
            for cable in ("CAT5E", "CAT6", "CAT6A", "CAT7", "CAT8"):
                with self.subTest(speed=speed, cable=cable):
                    result = link(a, group_a, b, group_b, speed, cable, 100)
                    self.assertEqual(len(result["candidates"]), 1)
                    self.assertEqual(result["candidates"][0]["endpoint_optic_candidates"],
                                     {"endpoint_a": None, "endpoint_b": None})
                    self.assertEqual(link(a, group_a, b, group_b, speed, cable, 100.01)["candidates"], [])
        for a, group_a, b, group_b, speed in (
            ("mx95", "rj45-lan", "ms150-24mp-4x", "rj45-mgig", 2.5),
            ("mx95", "rj45-wan", "ms150-24mp-4x", "rj45-mgig", 5),
            ("ms130-24x", "rj45-mgig", "ms150-24mp-4x", "rj45-mgig", 5),
            ("ms150-24mp-4x", "rj45-mgig", "ms150-48mp-4x", "rj45-mgig", 10),
        ):
            for cable in ("CAT6A", "CAT7", "CAT8"):
                self.assertEqual(link(a, group_a, b, group_b, speed, cable)["candidates"], [])

    def test_higher_copper_categories_do_not_qualify_optics_or_unsupported_speeds(self):
        for cable in ("CAT7", "CAT8"):
            for speed in (10, 25, 40):
                with self.subTest(cable=cable, speed=speed):
                    self.assertEqual(link("ms150-24mp-4x", "rj45-mgig",
                                          "ms150-48mp-4x", "rj45-mgig", speed, cable)["candidates"], [])
            rugged = link("ms130r-8p", "sfp-uplink", "ms130-24p", "sfp-uplink", 1, cable)
            self.assertEqual(rugged["candidates"][0]["endpoint_optic_candidates"], {
                "endpoint_a": "GLC-T-RGD", "endpoint_b": "MA-SFP-1GB-TX",
            })

    def test_native_copper_does_not_require_ordinary_copper_sfp_qualification(self):
        for model, group in (("ms130r-8p", "rj45-1g"), ("mx67", "rj45-lan")):
            result = link(model, group, "ms130-24p", "rj45-1g", 1, "CAT5E", 100)
            self.assertEqual(len(result["candidates"]), 1)
            self.assertEqual(result["candidates"][0]["endpoint_optic_candidates"],
                             {"endpoint_a": None, "endpoint_b": None})
            mixed = link(model, group, "ms130-24p", "sfp-uplink", 1, "CAT6")
            self.assertEqual(mixed["candidates"][0]["endpoint_optic_candidates"],
                             {"endpoint_a": None, "endpoint_b": "MA-SFP-1GB-TX"})

    def test_rugged_modules_and_mixed_module_reaches_in_both_directions(self):
        for cable, reach, rugged, ordinary in (
            ("OM1", 220, "GLC-SX-MM-RGD", "MA-SFP-1GB-SX"),
            ("OM3", 550, "GLC-SX-MM-RGD", "MA-SFP-1GB-SX"),
            ("OM4", 1000, "GLC-SX-MM-RGD", "MA-SFP-1GB-SX"),
            ("OS2", 10000, "GLC-LX-SM-RGD", "MA-SFP-1GB-LX10"),
            ("CAT6", 100, "GLC-T-RGD", "MA-SFP-1GB-TX"),
        ):
            for reverse in (False, True):
                a, b = (("ms130-24p", "ms130r-8p") if reverse else ("ms130r-8p", "ms130-24p"))
                with self.subTest(cable=cable, reverse=reverse):
                    result = link(a, "sfp-uplink", b, "sfp-uplink", 1, cable, reach)
                    self.assertEqual(len(result["candidates"]), 1)
                    self.assertEqual(list(result["candidates"][0]["endpoint_optic_candidates"].values()),
                                     [ordinary, rugged] if reverse else [rugged, ordinary])
                    self.assertEqual(link(a, "sfp-uplink", b, "sfp-uplink",
                                          1, cable, reach + .01)["candidates"], [])
        rugged = link("ms130r-8p", "sfp-uplink", "ms130r-8p", "sfp-uplink", 1, "OM3", 1000)
        self.assertEqual(len(rugged["candidates"]), 1)
        self.assertEqual(set(rugged["candidates"][0]["endpoint_optic_candidates"].values()),
                         {"GLC-SX-MM-RGD"})
        short = link("ms130r-8p", "sfp-uplink", "ms130-24p", "sfp-uplink", 1, "OM3", 1.99)
        self.assertEqual(short["candidates"], [])
        self.assertTrue(any("at least 2m" in text for text in short["exclusions"]))
        zx = link("ms130r-8p", "sfp-uplink", "ms130r-8p", "sfp-uplink", 1, "OS2", 70000)
        self.assertEqual(zx["candidates"][0]["endpoint_optic_candidates"]["endpoint_a"], "GLC-ZX-SM-RGD")
        self.assertIn("attenuator", zx["candidates"][0]["requirements"][0])

    def test_ms450_40g_and_100g_media_and_reach(self):
        for speed, group, cable, reach, part, connector in (
            (40, "qsfp-40g", "OM3", 100, "MA-QSFP-40G-SR4", "MPO12"),
            (40, "qsfp-40g", "OM3", 300, "MA-QSFP-40G-CSR4", "MPO12"),
            (40, "qsfp-40g", "OM3", 100, "MA-QSFP-40G-SR-BD", "Duplex LC"),
            (40, "qsfp-40g", "OS2", 10000, "MA-QSFP-40G-LR4", "Duplex LC"),
            (100, "qsfp-100g", "OM3", 70, "MA-QSFP-100G-SR4", "MPO12"),
            (100, "qsfp-100g", "OM4", 100, "MA-QSFP-100G-SR4", "MPO12"),
            (100, "qsfp-100g", "OS2", 10000, "MA-QSFP-100G-LR4", "Duplex LC"),
        ):
            with self.subTest(part=part, cable=cable):
                candidates = link("ms450-12", group, "ms450-12", group, speed, cable, reach)["candidates"]
                matching = [c for c in candidates if c["endpoint_optic_candidates"]["endpoint_a"] == part]
                self.assertEqual(len(matching), 1)
                self.assertIn(connector, matching[0]["cable"])
                self.assertFalse(any(
                    c["endpoint_optic_candidates"]["endpoint_a"] == part
                    for c in link("ms450-12", group, "ms450-12", group,
                                  speed, cable, reach + .01)["candidates"]
                ))
        self.assertEqual(link("ms450-12", "qsfp-40g", "ms450-12", "qsfp-100g",
                              100, "OM4")["candidates"], [])
        sr4 = next(a for a in load_matrix()["accessories"] if a["part"] == "MA-QSFP-100G-SR4")
        self.assertIn("MPO12", sr4["connector"])

    def test_100g_sr4_import_preserves_mpo_connector_after_refresh(self):
        headers = ["Meraki Product ID", "Standard", "Wavelength (nm)", "Fiber Description",
                   "Max Distance", "Data Rate", "Compatibility"]
        values = ["MA-QSFP-100G-SR4", "100GBASE-SR4", "850", "OM3, OM4/OM5",
                  "70 m, 100 m", "100 Gigabit", "MS450"]
        html = "<table><tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr><tr>"
        html += "".join(f"<td>{v}</td>" for v in values) + "</tr></table>"
        self.assertIn("MPO12", parse_matrix(html, "2026-10-20")["accessories"][0]["connector"])

    def test_wan_and_convertible_constraints_are_visible_only_when_relevant(self):
        wan = link("mx95", "sfp-wan", "ms130-24x", "sfp-uplink", 10, "OM3")
        self.assertTrue(any("paired" in text for text in wan["candidates"][0]["requirements"]))
        lan = link("mx95", "sfp-lan", "ms130-24x", "sfp-uplink", 10, "OM3")
        self.assertEqual(lan["candidates"][0]["requirements"], [])
        convertible = link("mx67", "rj45-convertible", "ms130-24p", "rj45-1g", 1, "CAT6")
        self.assertTrue(any("cannot serve both roles" in text
                            for text in convertible["candidates"][0]["requirements"]))

    def test_family_specific_optics_do_not_leak_to_other_families(self):
        ms150 = link("ms150-24p-4x", "sfp-uplink", "ms150-48fp-4x", "sfp-uplink", 10, "OS2", 80000)
        self.assertEqual(ms150["candidates"][0]["endpoint_optic_candidates"]["endpoint_a"], "MA-SFP-10GB-ZR")
        self.assertEqual(link("ms150-24p-4x", "sfp-uplink", "ms130-24x", "sfp-uplink",
                              10, "OS2", 80000)["candidates"], [])
        self.assertEqual(link("mx95", "sfp-lan", "ms150-24p-4x", "sfp-uplink",
                              10, "OM3", 301)["candidates"], [])


if __name__ == "__main__":
    unittest.main()
