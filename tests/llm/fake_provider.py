"""Fake OpenAI-compatible chat-completions provider on loopback, run in its OWN process.

A separate process is unaffected by any offline guard another test installed in the pytest worker.
Control files in a state directory: config.json (reply, mode), requests/N.json (recorded requests).
Modes: "good" (reply as chat completion), "big" (2 MB of whitespace before the reply).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path


def _serve(state_dir: str) -> None:
    from http.server import BaseHTTPRequestHandler, HTTPServer

    root = Path(state_dir)

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            n = len(list((root / "requests").glob("*.json")))
            (root / "requests" / f"{n:04d}.json").write_text(
                json.dumps({"path": self.path, "headers": dict(self.headers), "body": body.decode("utf-8")}),
                encoding="utf-8",
            )
            cfg = json.loads((root / "config.json").read_text(encoding="utf-8"))
            content = cfg["reply"] if isinstance(cfg["reply"], str) else json.dumps(cfg["reply"])
            payload = json.dumps({"choices": [{"message": {"role": "assistant", "content": content}}]}).encode()
            if cfg["mode"] == "big":
                payload = b" " * 2_000_000 + payload
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            try:
                self.wfile.write(payload)
            except OSError:
                pass

        def log_message(self, *a):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), H)
    (root / "port").write_text(str(httpd.server_address[1]), encoding="utf-8")
    httpd.serve_forever()


class FakeProvider:
    """Dict-like handle used by the tests: keys bodies, headers, reply, mode, url, env."""

    def __init__(self, state_dir: Path, api_key: str = "sekret-key-123", reply=None):
        self.root = Path(state_dir)
        (self.root / "requests").mkdir(parents=True, exist_ok=True)
        self.api_key = api_key
        self._cfg = {"reply": reply, "mode": "good"}
        self._write()
        env = {k: v for k, v in os.environ.items() if k not in ("PETS_OFFLINE", "PYTHONPATH")}
        self.proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), str(self.root)], env=env)
        for _ in range(200):
            if (self.root / "port").exists() and (self.root / "port").read_text(encoding="utf-8"):
                break
            time.sleep(0.05)
        self.url = f"http://127.0.0.1:{(self.root / 'port').read_text(encoding='utf-8')}/v1"

    def _write(self):
        (self.root / "config.json").write_text(json.dumps(self._cfg), encoding="utf-8")

    def _requests(self):
        return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((self.root / "requests").glob("*.json"))]

    def __getitem__(self, key):
        if key == "bodies":
            return [r["body"].encode("utf-8") for r in self._requests()]
        if key == "headers":
            return [(r["path"], r["headers"]) for r in self._requests()]
        if key == "url":
            return self.url
        if key == "env":
            return {"PETS_LLM_ENDPOINT": self.url, "PETS_LLM_MODEL": "m", "PETS_LLM_API_KEY": self.api_key}
        return self._cfg[key]

    def __setitem__(self, key, value):
        self._cfg[key] = value
        self._write()

    def close(self):
        self.proc.kill()
        self.proc.wait()


if __name__ == "__main__":
    _serve(sys.argv[1])
