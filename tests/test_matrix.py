import unittest
import json
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from opticfinder.engine import load_catalog, plan
from opticfinder.matrix import load_matrix, parse_matrix, profiles_for_endpoints, refresh_matrix


def connection(**changes):
    return {
        "endpoint_a": "ms130-24x", "endpoint_b": "ms130-24x",
        "interface_a": "sfp-uplink", "interface_b": "sfp-uplink",
        "speed_gbps": 10, "distance_m": 30, "cable_type": "OM3",
        **changes,
    }


class MatrixTests(unittest.TestCase):
    def test_snapshot_covers_all_reviewed_transceiver_and_data_dac_parts(self):
        matrix = load_matrix()
        self.assertEqual({accessory["part"] for accessory in matrix["accessories"]}, {
            "MA-SFP-1GB-SX", "MA-SFP-1GB-LX10", "MA-SFP-1GB-TX",
            "MA-SFP-10GB-SR", "MA-SFP-10GB-LR", "MA-SFP-10GB-LRM",
            "MA-SFP-10GB-ER", "MA-SFP-10GB-ZR",
            "MA-QSFP-40G-SR4", "MA-QSFP-40G-LR4", "MA-QSFP-40G-CSR4",
            "MA-QSFP-40G-SR-BD", "MA-QSFP-100G-LR4", "MA-QSFP-100G-SR4",
            "MA-CBL-TA-1M", "MA-CBL-TA-3M",
        })
        for accessory in matrix["accessories"]:
            with self.subTest(part=accessory["part"]):
                self.assertTrue(accessory["qualifications"])
                self.assertTrue(accessory["reach_m"])
                self.assertEqual(accessory["sources"], ["meraki-accessories"])

    def test_matrix_has_family_coverage_beyond_modeled_devices(self):
        coverage = load_catalog()["matrix_coverage"]
        self.assertTrue({"MS120", "MS130", "MS450", "MX75", "MX600"} <= set(coverage["families"]))
        self.assertEqual(coverage["accessory_count"], 16)
        self.assertEqual(coverage["modeled_device_count"], 37)
        self.assertEqual(coverage["additional_accessory_count"], 4)

    def test_optics_are_generated_from_matrix_not_hardcoded_profiles(self):
        catalog = load_catalog()
        parts = {
            part for profile in catalog["connection_profiles"]
            if "ms130-24x" in profile["endpoint_ids"]
            for part in profile["parts_by_port_kind"].values()
        }
        self.assertIn("MA-SFP-10GB-ER", parts)
        self.assertNotIn("MA-SFP-10GB-ZR", parts)
        self.assertNotIn("MA-SFP-10GB-LRM", parts)
        self.assertNotIn("MA-QSFP-100G-SR4", parts)

    def test_er_reach_and_model_qualification(self):
        result = plan(connection(cable_type="OS2", distance_m=40000))
        self.assertEqual(result["candidates"][0]["endpoint_optic_candidates"]["endpoint_a"],
                         "MA-SFP-10GB-ER")
        self.assertIn("attenuation", result["candidates"][0]["requirements"][0])
        self.assertEqual(plan(connection(cable_type="OS2", distance_m=40000.01))["candidates"], [])
        self.assertEqual(plan(connection(
            endpoint_b="ms130-24p", cable_type="OS2", distance_m=20000,
        ))["candidates"], [])

    def test_longer_reach_is_an_alternative_not_a_replacement_for_lr(self):
        candidates = plan(connection(cable_type="OS2", distance_m=1000))["candidates"]
        self.assertEqual([candidate["standard"] for candidate in candidates],
                         ["10GBASE-LR", "10GBASE-ER"])

    def test_older_fiber_grades_and_os1(self):
        for cable, reach in (("OM1", 26), ("OM2", 82)):
            with self.subTest(cable=cable):
                self.assertEqual(len(plan(connection(cable_type=cable, distance_m=reach))["candidates"]), 1)
                self.assertEqual(plan(connection(
                    cable_type=cable, distance_m=reach + .01,
                ))["candidates"], [])
        self.assertTrue(plan(connection(cable_type="OS1"))["candidates"])

    def test_dac_is_one_assembly_not_two_optics(self):
        for distance, expected in (
            (1, ["MA-CBL-TA-1M", "MA-CBL-TA-3M"]),
            (1.01, ["MA-CBL-TA-3M"]),
            (3, ["MA-CBL-TA-3M"]),
            (3.01, []),
        ):
            with self.subTest(distance=distance):
                result = plan(connection(cable_type="DAC", distance_m=distance))
                self.assertEqual([candidate["assembly_part"] for candidate in result["candidates"]], expected)
                for candidate in result["candidates"]:
                    self.assertEqual(candidate["endpoint_optic_candidates"],
                                     {"endpoint_a": None, "endpoint_b": None})
                    for options in candidate["endpoint_connection_options"].values():
                        self.assertEqual(options[0]["connection"], "direct_attach")
        self.assertEqual(plan(connection(cable_type="DAC", interface_b="rj45-1g"))["candidates"], [])
        self.assertEqual(plan(connection(cable_type="DAC", endpoint_b="ms130-24p"))["candidates"], [])

    def test_family_specific_media_and_negative_qualifications(self):
        endpoints = [
            {"id": "mx95-test", "matrix_families": ["MX95"]},
            {"id": "ms225-test", "matrix_families": ["MS225"]},
            {"id": "c9300x-test", "matrix_families": ["C9300", "C9300X"]},
            {"id": "ms390-test", "matrix_families": ["MS390"]},
        ]
        profiles = profiles_for_endpoints(load_matrix(), endpoints)
        for profile in profiles:
            if "MA-SFP-10GB-LRM" in profile["id"]:
                self.assertNotIn("c9300x-test", profile["endpoint_ids"])
                if "OM3" in profile["reach_m"]:
                    self.assertNotIn("mx95-test", profile["endpoint_ids"])
                if "OS2" in profile["reach_m"]:
                    self.assertIn("mx95-test", profile["endpoint_ids"])
            if "MA-SFP-1GB-TX" in profile["id"]:
                self.assertNotIn("ms390-test", profile["endpoint_ids"])
                self.assertNotIn("c9300x-test", profile["endpoint_ids"])

    def test_parser_retains_but_does_not_offer_mode_conditioned_lx10(self):
        accessory = next(item for item in load_matrix()["accessories"]
                         if item["part"] == "MA-SFP-1GB-LX10")
        qualified = next(item for item in accessory["qualifications"] if "requires" in item)
        self.assertEqual(qualified["reach_m"], {})
        self.assertFalse(set(accessory["reach_m"]) & {"OM1", "OM2", "OM3", "OM4"})

    def test_parser_fails_explicitly_for_unrecognized_source(self):
        for html in ("<html>Unavailable</html>",
                     '<table><tr><td colspan="2">Changed layout</td></tr></table>'):
            with self.subTest(html=html), self.assertRaises(ValueError):
                parse_matrix(html, "2026-10-20")

    def test_parser_imports_facts_and_normalizes_spacing(self):
        headers = ("Meraki Product ID", "Standard", "Wavelength (nm)", "Fiber Type",
                   "Fiber Description", "Max Distance", "Data Rate", "Compatibility")
        values = ("MA- SFP - 10GB -SR", "10GBASE-SR", "850", "MMF", "OM3",
                  "300 m", "10 Gigabit", "MS130-X / MS225")
        html = "<table><tr>" + "".join(f"<th>{header}</th>" for header in headers)
        html += "</tr><tr>" + "".join(f"<td>{value}</td>" for value in values) + "</tr></table>"
        matrix = parse_matrix(html, "2026-10-20")
        record = matrix["accessories"][0]
        self.assertEqual(record["part"], "MA-SFP-10GB-SR")
        self.assertEqual(record["reach_m"], {"OM3": 300})
        self.assertEqual(record["qualifications"][0]["families"], ["MS130-X", "MS225"])
        self.assertEqual(record["speed_gbps"], 10)

    def test_failed_refresh_does_not_replace_the_snapshot(self):
        with TemporaryDirectory() as directory:
            snapshot_path = Path(directory) / "matrix.json"
            original = json.dumps({"accessories": [{"part": "missing-part"}]})
            snapshot_path.write_text(original, encoding="utf-8")
            replacement = {"accessories": [{"part": "different-part"}]}
            with (
                patch("opticfinder.matrix.SNAPSHOT_PATH", snapshot_path),
                patch("opticfinder.matrix.urlopen", return_value=BytesIO(b"<html></html>")),
                patch("opticfinder.matrix.parse_matrix", return_value=replacement),
                self.assertRaisesRegex(ValueError, "missing-part"),
            ):
                refresh_matrix()
            self.assertEqual(snapshot_path.read_text(encoding="utf-8"), original)
            self.assertFalse(snapshot_path.with_suffix(".json.tmp").exists())


if __name__ == "__main__":
    unittest.main()
