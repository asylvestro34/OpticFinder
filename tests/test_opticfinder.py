import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from opticfinder.engine import load_catalog, plan
from opticfinder.server import Handler


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
        for cable in ("CAT5E", "CAT6", "CAT6A"):
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
                        {"cable_type": "MMF"}, {"fiber": "OM3"}, {"cable_type": "CAT7"}):
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
