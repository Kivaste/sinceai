"""Loopback UI command."""
import argparse
import hmac
import secrets
import json
import socket
import _socket
import os
from socketserver import TCPServer
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

from pets_release.ui.jobs import Jobs, SCENARIOS, scenarios
from pets_release.offline import install
from pets_release.manifest.value_scan import identifier_shape_counts


def local_listener(host, port):
    """Pre-bind the sole socket before the guard, retaining only an accept-only FD wrapper.

    Python's socket.accept() constructs a new socket wrapper and is blocked by the guard too.
    Wrap only descriptors returned by this listener's _accept(); never restore socket factories.
    """
    raw_socket = _socket.socket

    class AcceptedSocket(socket.socket):
        def __init__(self, descriptor):
            raw_socket.__init__(self, fileno=descriptor)
            self._io_refs = 0
            self._closed = False

    class LoopbackServer(HTTPServer):
        def server_bind(self):
            TCPServer.server_bind(self)  # HTTPServer's default performs a hostname lookup.
            self.server_name = "127.0.0.1"
            self.server_port = self.socket.getsockname()[1]

        def get_request(self):
            descriptor, address = self.socket._accept()
            connection = AcceptedSocket(descriptor)
            if address[0] != "127.0.0.1":
                connection.close()
                raise OSError("Non-loopback client refused")
            return connection, address

    return LoopbackServer((host, port), Handler)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # Requests carry capabilities; never log URLs or browser input.

    def respond(self, status, body, content_type="text/html"):
        if identifier_shape_counts(body):
            status, body, content_type = 422, "Unsafe artefact refused", "text/plain"
        if not isinstance(body, str):
            body = json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False)
            content_type = "application/json"
        body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def dispatch(self):
        supplied = parse_qs(urlsplit(self.path).query).get("token", [])
        if len(supplied) != 1 or not hmac.compare_digest(supplied[0], self.server.token):
            self.respond(403, "Forbidden")
            return
        path = urlsplit(self.path).path
        jobs = self.server.jobs
        if self.command == "GET" and path == "/api/scenarios":
            self.respond(200, scenarios())
        elif self.command == "GET" and path == "/api/result":
            self.respond(200, jobs.snapshot())
        elif self.command == "GET" and path == "/dashboard":
            try:
                dashboard = jobs.dashboard()
            except Exception:
                dashboard = None
            self.respond(200 if dashboard else 422, dashboard or "Dashboard unavailable")
        elif self.command == "POST" and path == "/api/run":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 1024:
                    raise ValueError
                node = json.loads(self.rfile.read(length))
                if set(node) != {"scenario"} or node["scenario"] not in SCENARIOS:
                    raise ValueError
            except (ValueError, TypeError):
                self.respond(400, "Invalid run request")
                return
            started = jobs.start(node["scenario"])
            self.respond(202 if started else 409, {"started": started})
        elif self.command == "GET" and path == "/":
            self.respond(200, "<!doctype html><title>Purpose-first PETs</title><h1>Choose a sharing scenario</h1>")
        else:
            self.respond(404, "Not found")

    do_GET = dispatch
    do_POST = dispatch


def serve(argv=None):
    parser = argparse.ArgumentParser(description="Local purpose-first PETs UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--kit", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--created", required=True)
    parser.add_argument("--plan", default="hand", choices=("hand", "measured"))
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        install()
        raise
    if args.host != "127.0.0.1":
        install()
        parser.exit(2, "UI binds only 127.0.0.1\n")
    if len(os.environ.get("PETS_HMAC_KEY", "")) < 32:
        install()
        parser.exit(2, "Set PETS_HMAC_KEY in the server environment (at least 32 characters)\n")
    server = local_listener(args.host, args.port)
    install()
    server.jobs = Jobs(args)
    server.token = secrets.token_urlsafe(32)
    print(f"http://127.0.0.1:{server.server_port}/?token={server.token}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
