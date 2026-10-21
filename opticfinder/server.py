"""Development server, intentionally restricted to this machine."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .engine import load_catalog, plan
from .matrix import load_matrix

MAX_BODY = 8192


class Handler(BaseHTTPRequestHandler):
    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(10)

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, value: dict) -> None:
        self._send(status, json.dumps(value, allow_nan=False).encode(), "application/json")

    def _local_request(self) -> bool:
        expected = f"127.0.0.1:{self.server.server_port}"
        if self.headers.get("Host") != expected:
            self._json(403, {"error": "Use the printed http://127.0.0.1 URL."})
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin != f"http://{expected}":
            self._json(403, {"error": "Cross-origin requests are not allowed."})
            return False
        return True

    def do_GET(self) -> None:
        if not self._local_request():
            return
        if self.path == "/api/catalog":
            self._json(200, load_catalog())
        elif self.path == "/api/matrix":
            self._json(200, load_matrix())
        elif self.path == "/health":
            self._json(200, {"status": "ok"})
        elif self.path in {"/", "/limitations", "/app.js", "/style.css"}:
            filename, content_type = {
                "/": ("index.html", "text/html; charset=utf-8"),
                "/limitations": ("limitations.html", "text/html; charset=utf-8"),
                "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                "/style.css": ("style.css", "text/css; charset=utf-8"),
            }[self.path]
            self._send(200, Path(__file__).with_name(filename).read_bytes(), content_type)
        else:
            self._json(404, {"error": "Not found."})

    def do_POST(self) -> None:
        self.close_connection = True
        if not self._local_request():
            return
        if self.path != "/api/plan":
            self._json(404, {"error": "Not found."})
            return
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            self._json(415, {"error": "Content-Type must be application/json."})
            return
        if self.headers.get("Transfer-Encoding"):
            self._json(400, {"error": "Transfer-Encoding is not supported."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json(400, {"error": "Invalid Content-Length."})
            return
        if not 0 < length <= MAX_BODY:
            self._json(413, {"error": "Body must contain 1 to 8192 bytes."})
            return
        try:
            data = self.rfile.read(length)
            if len(data) != length:
                raise ValueError("Incomplete request body.")
            result = plan(json.loads(data))
        except (ValueError, UnicodeDecodeError) as exc:
            self._json(400, {"error": str(exc)})
            return
        except TimeoutError:
            self._json(408, {"error": "Request body timed out."})
            return
        self._json(200, result)


def serve_local(port: int) -> None:
    with ThreadingHTTPServer(("127.0.0.1", port), Handler) as server:
        print(f"OpticFinder: http://127.0.0.1:{server.server_port} (local development only)", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nOpticFinder stopped.", flush=True)
