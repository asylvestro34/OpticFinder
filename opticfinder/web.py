"""Shared responses for the local server and production WSGI entry point."""

import json
from pathlib import Path

from .engine import load_catalog, plan
from .matrix import load_matrix

MAX_BODY = 8192
SECURITY_HEADERS = [
    ("Cache-Control", "no-store"),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("Content-Security-Policy",
     "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"),
]
STATIC_ROUTES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/limitations": ("limitations.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/theme.js": ("theme.js", "text/javascript; charset=utf-8"),
    "/favicon.svg": ("favicon.svg", "image/svg+xml"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}


def json_response(status, value):
    return status, json.dumps(value, allow_nan=False).encode(), "application/json"


def get_response(path):
    if path == "/api/catalog":
        return json_response(200, load_catalog())
    if path == "/api/matrix":
        return json_response(200, load_matrix())
    if path == "/health":
        return json_response(200, {"status": "ok"})
    if path in STATIC_ROUTES:
        filename, content_type = STATIC_ROUTES[path]
        return 200, Path(__file__).with_name(filename).read_bytes(), content_type
    return json_response(404, {"error": "Not found."})


def plan_response(body):
    try:
        result = plan(json.loads(body))
    except (ValueError, UnicodeDecodeError) as exc:
        return json_response(400, {"error": str(exc)})
    return json_response(200, result)
