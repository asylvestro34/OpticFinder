import json
import subprocess
import sys
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from opticfinder.engine import _combine_cable_options, load_catalog, plan
from opticfinder.server import Handler, serve_local


def request_data(**changes):
    return {
        "endpoint_a": "ms130-24x", "endpoint_b": "ms130-24x",
        "interface_a": "sfp-uplink", "interface_b": "sfp-uplink",
        "speed_gbps": 10, "distance_m": 30, "cable_type": "OM3",
        **changes,
    }


def meraki_request(**changes):
    return {
        "endpoint_a": "ms130-24x", "endpoint_b": "ms130-24x",
        "speed_gbps": 10, "distance_m": 30, "cable_type": "OM3",
        "interface_a": "sfp-uplink", "interface_b": "sfp-uplink",
        **changes,
    }


class MerakiTests(unittest.TestCase):
    def test_port_groups_match_ms130_installation_guide(self):
        expected = {
            "ms130-24p": [
                ("rj45-1g", "24 x 1G RJ45 ports", 24, [1]),
                ("sfp-uplink", "4 x 1G SFP ports", 4, [1]),
            ],
            "ms130-24x": [
                ("rj45-1g", "18 x 1G RJ45 ports", 18, [1]),
                ("rj45-mgig", "6 x 2.5G RJ45 ports", 6, [1, 2.5]),
                ("sfp-uplink", "4 x 10G SFP+ ports", 4, [1, 10]),
            ],
        }
        for endpoint in load_catalog()["endpoints"]:
            if endpoint["id"] not in expected:
                continue
            with self.subTest(model=endpoint["id"]):
                self.assertIn("meraki-ms130", endpoint["sources"])
                self.assertEqual([
                    (group["id"], group["label"], group["port_count"], group["speeds_gbps"])
                    for group in endpoint["interfaces"]
                ], expected[endpoint["id"]])

    def test_meraki_10g_fiber(self):
        result = plan(meraki_request())
        self.assertEqual(result["status"], "not_verified")
        self.assertEqual(result["candidates"][0]["endpoint_optic_candidates"],
                         {"endpoint_a": "MA-SFP-10GB-SR", "endpoint_b": "MA-SFP-10GB-SR"})
        self.assertEqual(result["link_interoperability"], "not_verified")
        self.assertNotIn("HPE", json.dumps(result))

    def test_interface_groups_are_required(self):
        for field in ("interface_a", "interface_b"):
            for value in (None, ""):
                data = meraki_request()
                if value is None:
                    del data[field]
                else:
                    data[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    plan(data)

    def test_meraki_profile_boundaries(self):
        for speed, cable, reach, part in (
            (10, "OM3", 300, "MA-SFP-10GB-SR"),
            (10, "OM4", 400, "MA-SFP-10GB-SR"),
            (10, "OS2", 10000, "MA-SFP-10GB-LR"),
            (1, "OM3", 550, "MA-SFP-1GB-SX"),
            (1, "OM4", 1000, "MA-SFP-1GB-SX"),
            (1, "OS2", 10000, "MA-SFP-1GB-LX10"),
        ):
            with self.subTest(speed=speed, cable=cable):
                data = meraki_request(speed_gbps=speed, cable_type=cable, distance_m=reach)
                result = plan(data)
                self.assertEqual(result["candidates"][0]["endpoint_optic_candidates"]["endpoint_a"], part)
                beyond = plan({**data, "distance_m": reach + .01})
                self.assertFalse(any(
                    candidate["endpoint_optic_candidates"]["endpoint_a"] == part
                    for candidate in beyond["candidates"]
                ))

    def test_1g_only_model_rejects_10g(self):
        self.assertEqual(plan(meraki_request(endpoint_b="ms130-24p"))["status"], "no_catalog_match")
        result = plan(meraki_request(endpoint_b="ms130-24p", speed_gbps=1))
        self.assertEqual(result["candidates"][0]["standard"], "1000BASE-SX")

    def test_native_copper_and_pluggable_copper(self):
        for cable in ("CAT5E", "CAT6", "CAT6A", "CAT7", "CAT8"):
            for a, b in (("rj45-1g", "rj45-1g"), ("rj45-1g", "sfp-uplink"),
                         ("sfp-uplink", "rj45-1g"), ("sfp-uplink", "sfp-uplink")):
                with self.subTest(cable=cable, a=a, b=b):
                    data = meraki_request(cable_type=cable, speed_gbps=1, distance_m=100,
                                          interface_a=a, interface_b=b)
                    result = plan(data)
                    options = result["candidates"][0]["endpoint_connection_options"]
                    for field, interface in (("endpoint_a", a), ("endpoint_b", b)):
                        option = options[field][0]
                        self.assertEqual(option["part"], None if interface == "rj45-1g" else "MA-SFP-1GB-TX")
                        self.assertEqual(option["connection"], "native_rj45" if interface == "rj45-1g" else "transceiver")
                    self.assertEqual(plan({**data, "distance_m": 100.01})["status"], "no_catalog_match")

    def test_selected_copper_interfaces_return_specific_options(self):
        result = plan(meraki_request(cable_type="CAT6", speed_gbps=1,
                                     interface_a="rj45-1g", interface_b="sfp-uplink"))
        self.assertEqual(result["status"], "not_verified")
        options = result["candidates"][0]["endpoint_connection_options"]
        self.assertEqual(options["endpoint_a"][0]["connection"], "native_rj45")
        self.assertEqual(options["endpoint_b"][0]["part"], "MA-SFP-1GB-TX")

    def test_no_native_rj45_fiber_or_unsupported_copper_speeds(self):
        for changes in ({"interface_a": "rj45-1g"}, {"cable_type": "CAT6A", "speed_gbps": 10},
                        {"cable_type": "CAT6", "speed_gbps": 2.5, "interface_a": "rj45-mgig"},
                        {"cable_type": "OS2", "speed_gbps": 25}):
            with self.subTest(changes=changes):
                self.assertEqual(plan(meraki_request(**changes))["status"], "no_catalog_match")

    def test_invalid_interface_and_media(self):
        for changes in ({"interface_a": "port999"}, {"interface_a": []},
                        {"endpoint_a": "ms130-24p", "interface_a": "rj45-mgig"},
                        {"cable_type": "MMF"}, {"fiber": "OM3"}, {"cable_type": "CAT9"},
                        {"cable_type": "CAT8.2"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                plan(meraki_request(**changes))

    def test_meraki_source_and_model_integrity(self):
        catalog = load_catalog()
        sources = {source["id"]: source for source in catalog["sources"]}
        endpoints = {endpoint["id"]: endpoint for endpoint in catalog["endpoints"]}
        for profile in catalog["connection_profiles"]:
            for source in profile["sources"]:
                self.assertIn(sources[source]["state"], {"reviewed", "engineering_rule"})
            for endpoint in profile["endpoint_ids"]:
                self.assertEqual(endpoints[endpoint]["vendor"], "Meraki")


class EngineTests(unittest.TestCase):
    def test_catalog_is_meraki_only(self):
        catalog = load_catalog()
        self.assertTrue(all(endpoint["vendor"] == "Meraki" for endpoint in catalog["endpoints"]))
        self.assertFalse({"c9300-nm-8x", "hpe-560sfp"} & {
            endpoint["id"] for endpoint in catalog["endpoints"]
        })

    def test_symmetric_invalid_inputs(self):
        data = request_data()
        for changes in ({"endpoint_a": "unknown"},
                        {"endpoint_a": []},
                        {"endpoint_b": "hpe-560sfp"},
                        {"endpoint_a": "c9300-nm-8x"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                plan({**data, **changes})

    def test_candidate_does_not_claim_support(self):
        result = plan(request_data())
        self.assertEqual(result["status"], "not_verified")
        self.assertEqual(result["endpoint_support"],
                         {"endpoint_a": "not_verified", "endpoint_b": "not_verified"})
        self.assertEqual(result["link_interoperability"], "not_verified")
        candidate = result["candidates"][0]
        self.assertEqual(candidate["endpoint_optic_candidates"],
                         {"endpoint_a": "MA-SFP-10GB-SR", "endpoint_b": "MA-SFP-10GB-SR"})

    def test_reach_boundaries(self):
        for cable_type, reach in (("OM3", 300), ("OM4", 400)):
            with self.subTest(cable_type=cable_type):
                self.assertEqual(len(plan(request_data(cable_type=cable_type, distance_m=reach))["candidates"]), 1)
                self.assertEqual(plan(request_data(cable_type=cable_type, distance_m=reach + .01))["candidates"], [])

    def test_no_match_is_not_proof_of_incompatibility(self):
        for changes in ({"cable_type": "CAT6A"}, {"speed_gbps": 25}, {"distance_m": 500}):
            result = plan(request_data(**changes))
            self.assertEqual(result["status"], "no_catalog_match")
            self.assertIn("does not establish", result["message"])

    def test_invalid_numbers(self):
        for field in ("distance_m", "speed_gbps"):
            for value in (0, -1, True, None, [], {}, "NaN", "inf", float("nan"), 10**1000):
                with self.subTest(field=field, value=str(value)):
                    with self.assertRaises(ValueError):
                        plan(request_data(**{field: value}))

    def test_unknown_and_missing_inputs(self):
        for data in ([], {}, request_data(endpoint_a="unknown"),
                     request_data(fiber=[]), request_data(extra="unexpected")):
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    plan(data)

    def test_source_provenance(self):
        catalog = load_catalog()
        sources = {source["id"]: source for source in catalog["sources"]}
        for profile in catalog["connection_profiles"]:
            for source in profile["sources"]:
                self.assertIn(sources[source]["state"], {"reviewed", "engineering_rule"})
                self.assertIsNotNone(sources[source]["reviewed_on"])
        for source in sources.values():
            self.assertTrue(source["url"].startswith("https://"))
        self.assertTrue(all(endpoint["vendor"] == "Meraki" for endpoint in catalog["endpoints"]))

    def test_devices_only_lists_all_profiles_and_port_alternatives_without_assumed_length(self):
        result = plan({"mode": "devices", "endpoint_a": "ms130-24x", "endpoint_b": "ms130-24x"})
        self.assertEqual(result["status"], "not_verified")
        self.assertNotIn("distance_m", result["request"])
        self.assertNotIn("speed_gbps", result["request"])
        self.assertFalse(result["exclusions"])
        candidates = result["candidates"]
        dac = [candidate for candidate in candidates if candidate.get("assembly_options")]
        self.assertEqual(len(dac), 1)
        self.assertEqual(dac[0]["assembly_options"], [
            {"part": "MA-CBL-TA-1M", "length_m": 1},
            {"part": "MA-CBL-TA-3M", "length_m": 3},
        ])
        self.assertEqual(dac[0]["cable_options"], {"DAC": 3})
        for assembly in dac[0]["assembly_options"]:
            detailed = plan(request_data(cable_type="DAC", distance_m=assembly["length_m"]))
            self.assertTrue(any(c["assembly_part"] == assembly["part"] for c in detailed["candidates"]))
            beyond = plan(request_data(cable_type="DAC", distance_m=assembly["length_m"] + .01))
            self.assertFalse(any(c["assembly_part"] == assembly["part"] for c in beyond["candidates"]))
        self.assertTrue(any(candidate["cable_options"].get("OM4") == 400 for candidate in candidates))
        copper = next(candidate for candidate in candidates if candidate["standard"] == "1000BASE-T")
        self.assertEqual(sum(c["standard"] == "1000BASE-T" for c in candidates), 1)
        self.assertEqual(copper["cable_options"], {
            "CAT5E": 100, "CAT6": 100, "CAT6A": 100, "CAT7": 100, "CAT8": 100,
        })
        self.assertTrue(any("Cat8.2" in note for note in copper["requirements"]))
        self.assertTrue(any("Class F" in note for note in copper["requirements"]))
        self.assertTrue(any("shield" in note for note in copper["requirements"]))
        self.assertIn("fluke-copper-categories", copper["sources"])
        self.assertIn("fluke-class-f", copper["sources"])
        self.assertEqual(
            {option["connection"] for option in copper["endpoint_connection_options"]["endpoint_a"]},
            {"native_rj45", "transceiver"},
        )
        for candidate in candidates:
            for cable, reach in candidate["cable_options"].items():
                for a in candidate["endpoint_connection_options"]["endpoint_a"]:
                    for b in candidate["endpoint_connection_options"]["endpoint_b"]:
                        with self.subTest(standard=candidate["standard"], cable=cable, a=a, b=b):
                            detailed = plan(request_data(
                                interface_a=a["interface_group"], interface_b=b["interface_group"],
                                speed_gbps=candidate["speed_gbps"], cable_type=cable, distance_m=reach,
                            ))
                            self.assertTrue(any(
                                match["standard"] == candidate["standard"]
                                and (not candidate.get("assembly_options") or {
                                    "part": match.get("assembly_part"),
                                    "length_m": match.get("assembly_length_m"),
                                } in candidate["assembly_options"])
                                and match["endpoint_connection_options"] == {
                                    "endpoint_a": [a], "endpoint_b": [b]
                                }
                                for match in detailed["candidates"]
                            ))

    def test_devices_only_respects_model_qualification_and_port_speeds(self):
        catalog = load_catalog()
        for a, b in (("ms130-24x", "ms130-24p"), ("ms130r-8p", "ms130-24x"),
                     ("mx95", "ms150-24p-4x"), ("ms450-12", "ms450-12"),
                     ("mx67", "mx67")):
            with self.subTest(a=a, b=b):
                result = plan({"mode": "devices", "endpoint_a": a, "endpoint_b": b})
                self.assertTrue(result["candidates"])
                expected = []
                for profile in catalog["connection_profiles"]:
                    endpoints = [next(e for e in catalog["endpoints"] if e["id"] == id_)
                                 for id_ in (a, b)]
                    if (all(e["id"] in profile["endpoint_ids"] for e in endpoints)
                            and all(any(e["id"] in group for e in endpoints)
                                    for group in profile.get("endpoint_groups", []))
                            and all(any(
                                profile["speed_gbps"] in port["speeds_gbps"]
                                and port["kind"] in (
                                    profile["parts_by_endpoint"].get(e["id"], {})
                                    if "parts_by_endpoint" in profile else profile["parts_by_port_kind"]
                                ) for port in e["interfaces"]
                            ) for e in endpoints)):
                        expected.append(profile)
                self.assertEqual(
                    {(c["standard"], c["speed_gbps"], grade, reach)
                     for c in result["candidates"] for grade, maximum in c["cable_options"].items()
                     for reach in ([a["length_m"] for a in c["assembly_options"]]
                                   if c.get("assembly_options") else [maximum])},
                    {(p["standard"], p["speed_gbps"], grade, reach)
                     for p in expected for grade, reach in p["reach_m"].items()},
                )
                for candidate in result["candidates"]:
                    for field, endpoint in zip(("endpoint_a", "endpoint_b"), endpoints):
                        for option in candidate["endpoint_connection_options"][field]:
                            port = next(p for p in endpoint["interfaces"]
                                        if p["id"] == option["interface_group"])
                            self.assertIn(candidate["speed_gbps"], port["speeds_gbps"])
                            for grade, reach in candidate["cable_options"].items():
                                self.assertTrue(any(
                                    p["standard"] == candidate["standard"]
                                    and p["speed_gbps"] == candidate["speed_gbps"]
                                    and p["reach_m"].get(grade) == reach
                                    and p.get("minimum_distance_m", 0) == candidate["minimum_distance_m"]
                                    and (not candidate.get("assembly_options") or {
                                        "part": p.get("assembly_part"), "length_m": p.get("assembly_length_m"),
                                    } in candidate["assembly_options"])
                                    and all(r in candidate["requirements"] for r in p.get("requirements", []))
                                    and port["kind"] in (
                                        p["parts_by_endpoint"].get(endpoint["id"], {})
                                        if "parts_by_endpoint" in p else p["parts_by_port_kind"]
                                    )
                                    and (option["connection"] == "direct_attach" or option["part"] == (
                                        p["parts_by_endpoint"].get(endpoint["id"], {})
                                        if "parts_by_endpoint" in p else p["parts_by_port_kind"]
                                    )[port["kind"]])
                                    for p in expected
                                ))

    def test_combining_grades_preserves_connection_differences_and_sources(self):
        base = {
            "standard": "1000BASE-T", "speed_gbps": 1, "cable": "RJ45",
            "endpoint_connection_options": {"endpoint_a": [{"part": None}]},
            "requirements": [], "minimum_distance_m": 0,
            "cable_options": {"CAT5E": 100}, "sources": ["first"],
        }
        combined = _combine_cable_options([
            base,
            {**base, "cable_options": {"CAT6": 100}, "sources": ["second"]},
            {**base, "cable_options": {"CAT6A": 100}, "sources": ["first"]},
        ])
        self.assertEqual(len(combined), 1)
        self.assertEqual(combined[0]["cable_options"], {"CAT5E": 100, "CAT6": 100, "CAT6A": 100})
        self.assertEqual(combined[0]["sources"], ["first", "second"])
        self.assertEqual(base["cable_options"], {"CAT5E": 100})
        for changes in (
            {"speed_gbps": 2.5}, {"standard": "2.5GBASE-T"},
            {"endpoint_connection_options": {"endpoint_a": [{"part": "optic"}]}},
            {"requirements": ["Cable-specific requirement"]}, {"minimum_distance_m": 2},
            {"assembly_part": "DAC-1M", "assembly_length_m": 1},
            {"cable_options": {"CAT5E": 55}},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(len(_combine_cable_options([base, {**base, **changes}])), 2)

    def test_fiber_grades_combine_without_losing_their_reaches(self):
        result = plan({"mode": "devices", "endpoint_a": "ms130-24x", "endpoint_b": "ms130-24p"})
        sx = [c for c in result["candidates"] if c["standard"] == "1000BASE-SX"]
        self.assertEqual(len(sx), 1)
        self.assertEqual(sx[0]["cable_options"], {"OM1": 220, "OM2": 550, "OM3": 550, "OM4": 1000})

    def test_dac_grouping_preserves_different_speeds_ports_and_requirements(self):
        base = {
            "standard": "10GBASE-CR", "speed_gbps": 10, "cable": "SFP+",
            "endpoint_connection_options": {"endpoint_a": [{"interface_group": "sfp"}]},
            "requirements": [], "minimum_distance_m": 0,
            "cable_options": {"DAC": 1}, "sources": ["first"],
            "assembly_part": "DAC-1M", "assembly_length_m": 1,
        }
        longer = {**base, "assembly_part": "DAC-3M", "assembly_length_m": 3,
                  "cable_options": {"DAC": 3}, "sources": ["second"]}
        combined = _combine_cable_options([longer, base, base])
        self.assertEqual(len(combined), 1)
        self.assertEqual(combined[0]["assembly_options"], [
            {"part": "DAC-1M", "length_m": 1}, {"part": "DAC-3M", "length_m": 3},
        ])
        self.assertEqual(combined[0]["cable_options"], {"DAC": 3})
        self.assertEqual(combined[0]["sources"], ["second", "first"])
        self.assertNotIn("assembly_part", combined[0])
        self.assertEqual(base["assembly_part"], "DAC-1M")
        for changes in ({"speed_gbps": 40}, {"requirements": ["Different firmware required"]},
                        {"minimum_distance_m": 1},
                        {"endpoint_connection_options": {"endpoint_a": [{"interface_group": "qsfp"}]}}):
            with self.subTest(changes=changes):
                self.assertEqual(len(_combine_cable_options([base, {**longer, **changes}])), 2)

    def test_devices_only_validates_inputs_and_never_ignores_filters(self):
        request = {"mode": "devices", "endpoint_a": "ms130-24x", "endpoint_b": "ms130-24p"}
        for changes in ({"endpoint_a": []}, {"endpoint_b": "unknown"}, {"mode": "unknown"},
                        {"interface_a": "sfp-uplink"}, {"distance_m": 30},
                        {"speed_gbps": 1}, {"cable_type": "OM3"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                plan({**request, **changes})
        with self.assertRaises(ValueError):
            plan({"mode": "devices", "endpoint_a": "ms130-24x"})

    def test_devices_only_cli(self):
        command = [sys.executable, "-m", "opticfinder", "check", "--devices-only",
                   "--endpoint-a", "ms130-24x", "--endpoint-b", "ms130-24p"]
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        self.assertTrue(json.loads(result.stdout)["candidates"])
        rejected = subprocess.run([*command, "--distance-m", "30"], capture_output=True, text=True)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("cannot be combined", rejected.stderr)


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def call(self, method, path, body=None, headers=None):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request(method, path, body, headers or {})
            response = connection.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            connection.close()

    def test_pages_and_health(self):
        for path in ("/", "/limitations", "/app.js", "/style.css", "/api/catalog", "/api/matrix", "/health"):
            with self.subTest(path=path):
                status, body, headers = self.call("GET", path)
                self.assertEqual(status, 200)
                self.assertIn("Content-Security-Policy", headers)
                if path == "/":
                    page = body.decode()
                    self.assertIn('<option value="devices" selected>', page)
                    self.assertIn('<label id="port-field-a" hidden>', page)
                    self.assertIn('<label id="port-field-b" hidden>', page)
                    self.assertIn('name="interface_a" required', page)
                    self.assertIn('name="interface_b" required', page)
                    self.assertIn('<fieldset id="link-requirements" hidden disabled>', page)
                    self.assertIn('id="compatibility" role="status"', page)
                    self.assertIn('<legend>Device A</legend>', page)
                    self.assertIn('<legend>Device B</legend>', page)
                    self.assertIn('class="cable-visual" aria-hidden="true"', page)
                    self.assertIn('class="brand-header"', page)
                    self.assertIn("Independent prototype", page)
                    self.assertIn("not an official Cisco tool or endorsed by Cisco", page)
                    self.assertIn('href="/limitations"', page)
                    self.assertIn('id="cable-family" required', page)
                if path == "/limitations":
                    page = body.decode()
                    self.assertIn("text/html", headers["Content-Type"])
                    for section in ("copper", "fiber", "single-mode", "installation"):
                        self.assertIn(f'id="{section}"', page)
                    for text in ("Cat5e", "Cat6A", "Cat7 / Class F", "Cat8",
                                 "25GBASE-T", "40GBASE-T", "30 m", "OM1", "OM5", "OS1", "OS2",
                                 "100GBASE-SR4", "10GBASE-LR", "Up to 55 m"):
                        self.assertIn(text, page)
                    for text in ("MA-SFP", "MA-QSFP", "GLC-", "MS130", "MX95",
                                 'id="planner-scope"', 'id="dac"'):
                        self.assertNotIn(text, page)
                    self.assertIn('href="/"', page)
                    self.assertNotIn('src="/app.js"', page)
                    self.assertNotIn("<select", page)
                    self.assertNotIn("<script", page)
                    self.assertIn('<details id="technical-details">', page)
                    self.assertIn("<summary>Source documentation</summary>", page)

    def test_plan_api(self):
        status, body, _ = self.call("POST", "/api/plan", json.dumps(request_data()),
                                    {"Content-Type": "application/json"})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["status"], "not_verified")

    def test_devices_only_api(self):
        status, body, _ = self.call("POST", "/api/plan", json.dumps({
            "mode": "devices", "endpoint_a": "ms130-24x", "endpoint_b": "ms130-24p",
        }), {"Content-Type": "application/json"})
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertTrue(result["candidates"])
        self.assertEqual({c["speed_gbps"] for c in result["candidates"]}, {1})

    def test_explicit_bind_uses_exact_host_and_same_origin(self):
        with ThreadingHTTPServer(("127.0.0.2", 0), Handler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                host = f"127.0.0.2:{server.server_port}"
                for headers, expected in (
                    ({}, 200),
                    ({"Host": host, "Origin": f"http://{host}"}, 200),
                    ({"Host": f"127.0.0.1:{server.server_port}"}, 403),
                    ({"Origin": "http://example.com"}, 403),
                    ({"Origin": "null"}, 403),
                ):
                    with self.subTest(headers=headers):
                        connection = HTTPConnection("127.0.0.2", server.server_port, timeout=5)
                        try:
                            connection.request("GET", "/health", headers=headers)
                            response = connection.getresponse()
                            self.assertEqual(response.status, expected)
                            response.read()
                        finally:
                            connection.close()
            finally:
                server.shutdown()
                thread.join()

    def test_serve_binds_specific_address_and_rejects_wildcards(self):
        for address in ("0.0.0.0", "224.0.0.1", "example.com", "::1"):
            with self.subTest(address=address), self.assertRaises(ValueError):
                serve_local(8765, address)
        with patch("opticfinder.server.ThreadingHTTPServer") as server, patch("builtins.print"):
            server.return_value.__enter__.return_value.serve_forever.side_effect = KeyboardInterrupt
            serve_local(8765, "192.168.1.25")
            server.assert_called_once_with(("192.168.1.25", 8765), Handler)

    def test_meraki_api_requires_port_groups_and_rejects_other_vendors(self):
        for data in ({"endpoint_a": "ms130-24x", "endpoint_b": "ms130-24x",
                      "speed_gbps": 10, "distance_m": 300, "cable_type": "OM3"},
                     request_data(endpoint_b="c9300-nm-8x")):
            status, body, _ = self.call("POST", "/api/plan", json.dumps(data),
                                        {"Content-Type": "application/json"})
            self.assertEqual(status, 400)
            self.assertIn("error", json.loads(body))

    def test_meraki_api(self):
        for data in (meraki_request(), meraki_request(cable_type="CAT6", speed_gbps=1,
                                                     interface_a="rj45-1g", interface_b="rj45-1g")):
            status, body, _ = self.call("POST", "/api/plan", json.dumps(data),
                                        {"Content-Type": "application/json"})
            self.assertEqual(status, 200)
            self.assertTrue(json.loads(body)["candidates"])

    def test_bad_api_requests(self):
        for body, headers, expected in (
            ("{", {"Content-Type": "application/json"}, 400),
            ("[]", {"Content-Type": "application/json"}, 400),
            ("{}", {"Content-Type": "application/json"}, 400),
            ("{}", {"Content-Type": "text/plain"}, 415),
            ("x" * 8193, {"Content-Type": "application/json"}, 413),
            ("{}", {"Content-Type": "application/json", "Origin": "https://example.com"}, 403),
        ):
            with self.subTest(expected=expected, headers=headers):
                status, data, _ = self.call("POST", "/api/plan", body, headers)
                self.assertEqual(status, expected)
                self.assertIn("error", json.loads(data))

    def test_unrecognized_host_and_path(self):
        self.assertEqual(self.call("GET", "/", headers={"Host": "example.com"})[0], 403)
        self.assertEqual(self.call("GET", "/missing")[0], 404)
        self.assertEqual(self.call("POST", "/missing", "{}")[0], 404)


if __name__ == "__main__":
    unittest.main()
