"""Opt-in real-kit HTTP evidence and headless Edge screenshots; no row values are printed.

Run only on a clean pinned head, with PETS_HMAC_KEY supplied by the caller's environment.
The output folder and optional CLI reference must be outside the repository.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

from pets_release.manifest.value_scan import identifier_shape_counts


def capture():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kit", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--created", default="2026-11-07T08:00:00Z")
    parser.add_argument("--reference")
    parser.add_argument("--measured", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    revision = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    if subprocess.check_output(["git", "-C", str(root), "status", "--porcelain"], text=True).strip():
        raise SystemExit("Clean worktree required")
    evidence = Path(args.out).resolve()
    evidence.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, PYTHONPATH=str(root / "src"), PYTHONUTF8="1", TZ="UTC")
    env.pop("PETS_OFFLINE", None)
    server = subprocess.Popen([sys.executable, "-m", "pets_release.ui", "--kit", args.kit,
                               "--out", str(evidence / "runs"), "--created", args.created, "--port", "0",
                               *(["--measured"] if args.measured else [])],
                              env=env, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def get(url):
        with urlopen(url, timeout=90) as response:
            body = response.read().decode()
        try:
            node = json.loads(body)
        except ValueError:
            node = body
        if identifier_shape_counts(node):
            raise RuntimeError("HTTP identifier-shape scan failed")
        if env["PETS_HMAC_KEY"] in body:
            raise RuntimeError("HTTP key guard failed")
        return node

    def screenshot(url, name):
        edge = Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe"
        process = subprocess.run([str(edge), "--headless", "--disable-gpu", "--no-first-run",
                                  "--disable-background-networking", "--disable-extensions",
                                  "--hide-scrollbars", "--window-size=1440,1200",
                                  f"--user-data-dir={evidence / ('edge-' + name)}",
                                  f"--screenshot={evidence / (name + '.png')}", url],
                                 capture_output=True, timeout=90, check=False)
        if process.returncode != 0 or not (evidence / (name + ".png")).is_file():
            raise RuntimeError("Edge screenshot failed")

    try:
        url = server.stdout.readline().strip()
        if not url.startswith("http://127.0.0.1:"):
            raise RuntimeError("UI did not start")
        get(url)
        screenshot(url, "choose")
        run_url = url.replace("/?", "/api/run?")
        request = Request(run_url, data=b'{"scenario":"HEALTH-S1"}', headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=90) as response:
            accepted = json.loads(response.read())
        if identifier_shape_counts(accepted) or not accepted.get("started"):
            raise RuntimeError("UI did not accept run")
        deadline = time.monotonic() + 2400
        while time.monotonic() < deadline:
            report = get(url.replace("/?", "/api/result?"))
            if report["status"] != "RUNNING":
                break
            time.sleep(1)
        else:
            raise RuntimeError("UI run timed out")
        get(url.replace("/?", "/result?"))
        screenshot(url.replace("/?", "/result?"), "result")
        if args.measured:
            if report.get("measured", {}).get("privacy", {}).get("status") != "measured":
                raise RuntimeError("UI privacy was not measured")
        # D41: never decode, store, print or screenshot real-kit rows. Count transport
        # bytes only; screenshots above contain aggregates, with no rows auto-loaded.
        with urlopen(url.replace("/?", "/rows?"), timeout=300) as response:
            row_status = response.status
            row_bytes = 0
            for chunk in iter(lambda: response.read(65536), b""):
                row_bytes += len(chunk)
        same_bytes = None
        if args.reference:
            release = evidence / "runs" / "run-1"
            reference = Path(args.reference)
            same_bytes = {p.name: p.read_bytes() for p in release.iterdir()} == {
                p.name: p.read_bytes() for p in reference.iterdir()}
        record = {"revision": revision, "http": report, "sameBytesAsCLI": same_bytes,
                  "protectedRowsHTTP": {"status": row_status, "bytes": row_bytes}}
        (evidence / "http-evidence.json").write_text(json.dumps(record, sort_keys=True, indent=2), encoding="utf-8")
        print(json.dumps({"revision": revision, "status": report["status"], "gate": report.get("gate"),
                          "steps": report["steps"], "sameBytesAsCLI": same_bytes,
                          "protectedRowsHTTP": {"status": row_status, "bytes": row_bytes}}, sort_keys=True))
        if report["status"] != "RELEASED" or same_bytes is False or row_status != 200 or row_bytes <= 0:
            return 1
        get(url.replace("/?", "/dashboard?"))
        return 0
    finally:
        server.terminate()
        stdout, stderr = server.communicate(timeout=30)
        if env["PETS_HMAC_KEY"] in stdout + stderr:
            raise RuntimeError("Server log key guard failed")


if __name__ == "__main__":
    raise SystemExit(capture())
