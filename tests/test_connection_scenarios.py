"""Named end-to-end planning scenarios for supported Meraki connection types."""

import unittest

from opticfinder.engine import plan


def scenario(endpoint_a, interface_a, endpoint_b, interface_b, speed, cable, distance):
    return {
        "endpoint_a": endpoint_a,
        "interface_a": interface_a,
        "endpoint_b": endpoint_b,
        "interface_b": interface_b,
        "speed_gbps": speed,
        "cable_type": cable,
        "distance_m": distance,
    }


VALID_SCENARIOS = (
    {
        "name": "10G SR over OM3 between MS130-24X uplinks",
        "request": scenario("ms130-24x", "sfp-uplink", "ms130-24x", "sfp-uplink", 10, "OM3", 30),
        "standard": "10GBASE-SR",
        "parts": ("MA-SFP-10GB-SR", "MA-SFP-10GB-SR"),
        "connections": ("transceiver", "transceiver"),
        "reach_m": 300,
    },
    {
        "name": "10G SR at its OM4 catalog reach",
        "request": scenario("ms130-24x", "sfp-uplink", "ms130-24x", "sfp-uplink", 10, "OM4", 400),
        "standard": "10GBASE-SR",
        "parts": ("MA-SFP-10GB-SR", "MA-SFP-10GB-SR"),
        "connections": ("transceiver", "transceiver"),
        "reach_m": 400,
    },
    {
        "name": "10G LR over OS2",
        "request": scenario("ms130-24x", "sfp-uplink", "ms130-24x", "sfp-uplink", 10, "OS2", 1000),
        "standard": "10GBASE-LR",
        "parts": ("MA-SFP-10GB-LR", "MA-SFP-10GB-LR"),
        "connections": ("transceiver", "transceiver"),
        "reach_m": 10000,
    },
    {
        "name": "1G SX over OM3 between MS130 models",
        "request": scenario("ms130-24x", "sfp-uplink", "ms130-24p", "sfp-uplink", 1, "OM3", 30),
        "standard": "1000BASE-SX",
        "parts": ("MA-SFP-1GB-SX", "MA-SFP-1GB-SX"),
        "connections": ("transceiver", "transceiver"),
        "reach_m": 550,
    },
    {
        "name": "1G SX over OM4 at its catalog reach",
        "request": scenario("ms130-24x", "sfp-uplink", "ms130-24p", "sfp-uplink", 1, "OM4", 1000),
        "standard": "1000BASE-SX",
        "parts": ("MA-SFP-1GB-SX", "MA-SFP-1GB-SX"),
        "connections": ("transceiver", "transceiver"),
        "reach_m": 1000,
    },
    {
        "name": "1G LX10 over OS2",
        "request": scenario("ms130-24p", "sfp-uplink", "ms130-24p", "sfp-uplink", 1, "OS2", 1000),
        "standard": "1000BASE-LX10",
        "parts": ("MA-SFP-1GB-LX10", "MA-SFP-1GB-LX10"),
        "connections": ("transceiver", "transceiver"),
        "reach_m": 10000,
    },
    {
        "name": "1G native copper over Cat5e",
        "request": scenario("ms130-24x", "rj45-1g", "ms130-24p", "rj45-1g", 1, "CAT5E", 100),
        "standard": "1000BASE-T",
        "parts": (None, None),
        "connections": ("native_rj45", "native_rj45"),
        "reach_m": 100,
    },
    {
        "name": "1G native copper to SFP copper module over Cat6",
        "request": scenario("ms130-24x", "rj45-1g", "ms130-24p", "sfp-uplink", 1, "CAT6", 100),
        "standard": "1000BASE-T",
        "parts": (None, "MA-SFP-1GB-TX"),
        "connections": ("native_rj45", "transceiver"),
        "reach_m": 100,
    },
    {
        "name": "1G SFP copper module to native copper over Cat6A",
        "request": scenario("ms130-24p", "sfp-uplink", "ms130-24x", "rj45-1g", 1, "CAT6A", 100),
        "standard": "1000BASE-T",
        "parts": ("MA-SFP-1GB-TX", None),
        "connections": ("transceiver", "native_rj45"),
        "reach_m": 100,
    },
    {
        "name": "1G SFP copper modules at both ends",
        "request": scenario("ms130-24x", "sfp-uplink", "ms130-24p", "sfp-uplink", 1, "CAT6", 50),
        "standard": "1000BASE-T",
        "parts": ("MA-SFP-1GB-TX", "MA-SFP-1GB-TX"),
        "connections": ("transceiver", "transceiver"),
        "reach_m": 100,
    },
)


INVALID_SCENARIOS = (
    (
        "10G on an MS130-24P 1G uplink",
        scenario("ms130-24x", "sfp-uplink", "ms130-24p", "sfp-uplink", 10, "OM3", 30),
    ),
    (
        "fiber on a native RJ45 port",
        scenario("ms130-24x", "rj45-1g", "ms130-24x", "sfp-uplink", 1, "OM3", 30),
    ),
    (
        "copper above its 100m catalog reach",
        scenario("ms130-24x", "rj45-1g", "ms130-24x", "rj45-1g", 1, "CAT6", 100.01),
    ),
)


class ConnectionScenarioTests(unittest.TestCase):
    def test_supported_connection_scenarios(self):
        for case in VALID_SCENARIOS:
            with self.subTest(scenario=case["name"]):
                result = plan(case["request"])
                self.assertEqual(result["status"], "not_verified")
                matches = [
                    candidate for candidate in result["candidates"]
                    if candidate["standard"] == case["standard"]
                ]
                self.assertEqual(len(matches), 1)
                candidate = matches[0]
                self.assertEqual(candidate["standard"], case["standard"])
                self.assertEqual(candidate["documented_profile_reach_m"], case["reach_m"])
                for field, part, connection in zip(
                    ("endpoint_a", "endpoint_b"), case["parts"], case["connections"]
                ):
                    option = candidate["endpoint_connection_options"][field][0]
                    self.assertEqual(option["part"], part)
                    self.assertEqual(option["connection"], connection)

    def test_incompatible_connection_scenarios(self):
        for name, request in INVALID_SCENARIOS:
            with self.subTest(scenario=name):
                result = plan(request)
                self.assertEqual(result["status"], "no_catalog_match")
                self.assertEqual(result["candidates"], [])


if __name__ == "__main__":
    unittest.main()
