import json
import unittest
from io import BytesIO
from unittest.mock import patch
from wsgiref.util import setup_testing_defaults
from wsgiref.validate import validator

from opticfinder.wsgi import create_application


class WSGITests(unittest.TestCase):
    def call(self, path="/", method="GET", body=b"", validate_wsgi=True, **changes):
        environ = {}
        setup_testing_defaults(environ)
        environ.update({
            "REQUEST_METHOD": method, "PATH_INFO": path, "QUERY_STRING": "",
            "HTTP_HOST": "opticfinder.ddns.net", "CONTENT_LENGTH": str(len(body)),
            "CONTENT_TYPE": "application/json", "wsgi.input": BytesIO(body),
            **changes,
        })
        response = {}

        def start_response(status, headers, exc_info=None):
            response["status"] = int(status.split()[0])
            response["headers"] = dict(headers)

        app = create_application("https://opticfinder.ddns.net")
        if validate_wsgi:
            app = validator(app)
        result = app(environ, start_response)
        try:
            response["body"] = b"".join(result)
        finally:
            if hasattr(result, "close"):
                result.close()
        self.assertEqual(int(response["headers"]["Content-Length"]), len(response["body"]))
        self.assertIn("Content-Security-Policy", response["headers"])
        self.assertEqual(response["headers"]["Cache-Control"], "no-store")
        return response

    def test_configuration_requires_explicit_https_origin(self):
        for origin in ("", "http://example.com", "https://example.com/", "https://user@example.com",
                       "https://example.com:443", "https://example.com?query=1",
                       "https://example.com#fragment"):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                create_application(origin)
        with patch.dict("os.environ", {"OPTICFINDER_PUBLIC_ORIGIN": "https://opticfinder.ddns.net"}):
            self.assertTrue(callable(create_application()))

    def test_all_public_get_routes(self):
        for path in ("/", "/limitations", "/app.js", "/style.css",
                     "/api/catalog", "/api/matrix", "/health"):
            with self.subTest(path=path):
                self.assertEqual(self.call(path)["status"], 200)
        self.assertEqual(self.call("/missing")["status"], 404)
        self.assertEqual(self.call("/../README.md")["status"], 404)

    def test_host_and_origin_are_not_inferred_from_forwarding_headers(self):
        for changes in (
            {"HTTP_HOST": "example.com"},
            {"HTTP_HOST": "127.0.0.1:8765", "HTTP_X_FORWARDED_HOST": "opticfinder.ddns.net"},
            {"HTTP_ORIGIN": "http://opticfinder.ddns.net"},
            {"HTTP_ORIGIN": "https://example.com"},
            {"HTTP_ORIGIN": "null"},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(self.call(**changes)["status"], 403)
        self.assertEqual(self.call(HTTP_ORIGIN="https://opticfinder.ddns.net")["status"], 200)

    def test_public_plan_matches_existing_engine(self):
        request = {
            "endpoint_a": "mx95", "endpoint_b": "ms150-24p-4x",
            "interface_a": "sfp-lan", "interface_b": "sfp-uplink",
            "speed_gbps": 10, "distance_m": 30, "cable_type": "OM3",
        }
        response = self.call("/api/plan", "POST", json.dumps(request).encode(),
                             HTTP_ORIGIN="https://opticfinder.ddns.net")
        self.assertEqual(response["status"], 200)
        self.assertEqual(json.loads(response["body"])["candidates"][0]["endpoint_optic_candidates"],
                         {"endpoint_a": "MA-SFP-10GB-SR", "endpoint_b": "MA-SFP-10GB-SR"})

    def test_public_devices_only_plan(self):
        response = self.call("/api/plan", "POST", json.dumps({
            "mode": "devices", "endpoint_a": "mx95", "endpoint_b": "ms150-24p-4x",
        }).encode(), HTTP_ORIGIN="https://opticfinder.ddns.net")
        self.assertEqual(response["status"], 200)
        result = json.loads(response["body"])
        self.assertTrue(result["candidates"])
        self.assertNotIn("distance_m", result["request"])

    def test_request_bounds_and_errors(self):
        for body, changes, expected in (
            (b"{}", {}, 400), (b"[]", {}, 400), (b"{", {}, 400),
            (b"\xff", {}, 400),
            (b"{}", {"CONTENT_TYPE": "text/plain"}, 415),
            (b"", {}, 413), (b"x" * 8193, {}, 413),
            (b"{}", {"CONTENT_LENGTH": "10"}, 400),
            (b"{}", {"HTTP_TRANSFER_ENCODING": "chunked"}, 400),
            (b"{}", {"HTTP_ORIGIN": "https://example.com"}, 403),
        ):
            with self.subTest(changes=changes, expected=expected):
                response = self.call("/api/plan", "POST", body, **changes)
                self.assertEqual(response["status"], expected)
                self.assertIn("error", json.loads(response["body"]))
        self.assertEqual(self.call("/", "POST", b"{}")["status"], 404)
        self.assertEqual(self.call("/", "DELETE")["status"], 405)
        self.assertEqual(self.call("/api/plan", "POST", b"{}", validate_wsgi=False,
                                   CONTENT_LENGTH="invalid")["status"], 400)


if __name__ == "__main__":
    unittest.main()
