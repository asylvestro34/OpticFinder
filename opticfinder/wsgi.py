"""Production entry point; run behind a same-host HTTPS reverse proxy."""

import os
from http import HTTPStatus
from urllib.parse import urlsplit

from .web import MAX_BODY, SECURITY_HEADERS, get_response, json_response, plan_response


def create_application(public_origin=None):
    origin = public_origin if public_origin is not None else os.environ.get("OPTICFINDER_PUBLIC_ORIGIN", "")
    parsed = urlsplit(origin)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.path or parsed.query or parsed.fragment
            or parsed.netloc != parsed.hostname or origin != f"https://{parsed.hostname}"):
        raise ValueError(
            "Set OPTICFINDER_PUBLIC_ORIGIN to an HTTPS hostname without a port or path "
            "(for example https://opticfinder.ddns.net)."
        )
    host = parsed.hostname

    def application(environ, start_response):
        response = dispatch(environ)
        status, body, content_type = response
        start_response(f"{status} {HTTPStatus(status).phrase}", [
            ("Content-Type", content_type), ("Content-Length", str(len(body))),
            *SECURITY_HEADERS,
        ])
        return [body]

    def dispatch(environ):
        if environ.get("HTTP_HOST") != host:
            return json_response(403, {"error": "Unrecognized hostname."})
        request_origin = environ.get("HTTP_ORIGIN")
        if request_origin is not None and request_origin != origin:
            return json_response(403, {"error": "Cross-origin requests are not allowed."})
        method = environ.get("REQUEST_METHOD")
        path = environ.get("PATH_INFO")
        if method == "GET":
            return get_response(path)
        if method != "POST":
            return json_response(405, {"error": "Use GET or POST."})
        if path != "/api/plan":
            return json_response(404, {"error": "Not found."})
        if environ.get("CONTENT_TYPE", "").split(";")[0].strip() != "application/json":
            return json_response(415, {"error": "Content-Type must be application/json."})
        if environ.get("HTTP_TRANSFER_ENCODING"):
            return json_response(400, {"error": "Transfer-Encoding is not supported."})
        try:
            length = int(environ.get("CONTENT_LENGTH") or "0")
        except ValueError:
            return json_response(400, {"error": "Invalid Content-Length."})
        if not 0 < length <= MAX_BODY:
            return json_response(413, {"error": "Body must contain 1 to 8192 bytes."})
        body = environ["wsgi.input"].read(length)
        if len(body) != length:
            return json_response(400, {"error": "Incomplete request body."})
        return plan_response(body)

    return application
