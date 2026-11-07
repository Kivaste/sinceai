"""Approved seam: real loopback HTTP server and real CLI, synthetic mini-kit only."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import pytest
from contextlib import contextmanager
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen

from pets_release.manifest.value_scan import identifier_shape_counts

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "run"))
from run_helpers import CREATED, ROOT, TEST_KEY, build_kit, coarse_qis
from run_helpers import cli, run_args


def launch_args(kit, out, *extra):
    return [sys.executable, "-m", "pets_release.ui", "--kit", str(kit), "--out", str(out),
            "--created", CREATED, "--port", "0", *extra]


def server_env():
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), PETS_HMAC_KEY=TEST_KEY,
               PYTHONUTF8="1", TZ="UTC")
    env.pop("PETS_OFFLINE", None)
    return env


@contextmanager
def running(tmp_path, *, extra_env=None, edit=coarse_qis, probe=False):
    kit = build_kit(tmp_path / "kit", edit)
    env = server_env()
    env.update(extra_env or {})
    command = launch_args(kit, tmp_path / "out")
    if probe:
        trigger, output = tmp_path / "probe-start", tmp_path / "probe-result.json"
        code = f'''
import json, pathlib, runpy, socket, subprocess, sys, threading, time
def probe():
    trigger = pathlib.Path({str(trigger)!r})
    while not trigger.exists():
        time.sleep(0.02)
    try:
        socket.socket()
        blocked = False
    except OSError as exc:
        blocked = "offline guard" in str(exc)
    child = subprocess.run([sys.executable, "-c", "import socket; socket.socket()"], capture_output=True)
    pathlib.Path({str(output)!r}).write_text(json.dumps([blocked, child.returncode != 0 and b"offline guard" in child.stderr]))
threading.Thread(target=probe, daemon=True).start()
sys.argv = {command[2:]!r}
runpy.run_module("pets_release.ui", run_name="__main__")
'''
        command = [sys.executable, "-c", code]
    proc = subprocess.Popen(command, env=env, cwd=ROOT,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        line = proc.stdout.readline().strip()
        assert line.startswith("http://127.0.0.1:"), "server did not announce a loopback URL"
        yield proc, line, kit, tmp_path / "out"
    finally:
        proc.terminate()
        proc.ui_logs = proc.communicate(timeout=30)


def request(url, path="/", *, auth=True, data=None, method=None):
    parts = urlsplit(url)
    target = f"{parts.scheme}://{parts.netloc}{path}"
    if auth:
        target += ("&" if "?" in path else "?") + parts.query
    req = Request(target, data=None if data is None else json.dumps(data).encode(), method=method,
                  headers={"Content-Type": "application/json"})
    try:
        response = urlopen(req, timeout=60)
    except HTTPError as exc:
        response = exc
    with response:
        body = response.read().decode()
        try:
            node = json.loads(body)
        except ValueError:
            node = body
        assert identifier_shape_counts(node) == {}, "HTTP response contains an identifier shape"
        assert TEST_KEY not in body
        return response.status, body


def test_non_loopback_bind_is_refused(tmp_path):
    """Rule: only literal 127.0.0.1 may bind; wildcard/LAN/hostname -> usage refusal."""
    kit = build_kit(tmp_path / "kit", coarse_qis)
    for host in ("0.0.0.0", "192.0.2.1", "localhost", "::1"):
        proc = subprocess.run(launch_args(kit, tmp_path / "out", "--host", host), env=server_env(),
                              cwd=ROOT, capture_output=True, text=True, timeout=20)
        assert proc.returncode == 2
        assert "only 127.0.0.1" in proc.stderr


def test_every_request_needs_a_fresh_launch_token(tmp_path):
    """Rule: missing/wrong token -> 403, including POST; launch tokens never repeat."""
    tokens = []
    for i in range(2):
        with running(tmp_path / str(i)) as (_, url, _, _):
            tokens.append(parse_qs(urlsplit(url).query)["token"][0])
            for path, data in (("/", None), ("/api/scenarios", None), ("/api/run", {"scenario": "HEALTH-S1"})):
                assert request(url, path, auth=False, data=data)[0] == 403
                assert request(url, path + "?token=wrong", auth=False, data=data)[0] == 403
            assert request(url)[0] == 200
    assert tokens[0] != tokens[1] and min(map(len, tokens)) >= 32


def result(url):
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        status, body = request(url, "/api/result")
        assert status == 200
        node = json.loads(body)
        if node["status"] not in ("RUNNING", "IDLE"):
            return node
        time.sleep(0.1)
    raise AssertionError("run did not complete")


def test_health_release_matches_cli_bytes_and_rechecks_both_tiers(tmp_path):
    """Rule: HTTP run -> real run/gate/verify/verify-full; same release bytes as CLI."""
    with running(tmp_path) as (_, url, kit, out):
        status, body = request(url, "/api/scenarios")
        assert status == 200
        scenarios = json.loads(body)
        assert {s["scenario"] for s in scenarios} == {"HEALTH-S1", "CS-S1"}
        health = next(s for s in scenarios if s["scenario"] == "HEALTH-S1")
        assert health["purposeChecks"] == ["H-U2", "H-U4", "H-U6", "H-U7", "H-U8"]
        assert health["floors"] and health["sacrifices"] and health["recipient"]
        assert request(url, "/api/run", data={"scenario": "HEALTH-S1"})[0] == 202
        report = result(url)
        assert report["status"] == "RELEASED", report
        assert [(s["name"], s["exit"]) for s in report["steps"]] == [
            ("run", 0), ("verify (limited)", 0), ("verify --full", 0)]
        assert report["gate"]["total"] > 0
        assert report["gate"]["passed"] == report["gate"]["total"]
        assert report["personK"]["belowK"] == 0
        assert report["exportAssertions"] and report["assertionEvidence"]
        assert report["measured"]["utility"]
        release = out / "run-1"
        assert (release / "privacy_manifest.json").is_file()
        other = tmp_path / "cli-release"
        proc = cli(*run_args(kit, other))
        assert proc.returncode == 0, "reference CLI failed"
        assert {p.name: p.read_bytes() for p in release.iterdir()} == {
            p.name: p.read_bytes() for p in other.iterdir()}


def test_server_and_children_are_offline_while_loopback_http_works(tmp_path):
    """Rule: bound local HTTP stays usable; new server/child sockets stay blocked."""
    with running(tmp_path, probe=True) as (_, url, _, _):
        status, body = request(url)
        assert status == 200
        assert not any(asset in body for asset in ('src="http', 'href="http', "fonts.googleapis", "cdn."))
        (tmp_path / "probe-start").touch()
        output = tmp_path / "probe-result.json"
        deadline = time.monotonic() + 20
        while not output.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert json.loads(output.read_text()) == [True, True]
        assert request(url, "/api/scenarios")[0] == 200


def test_only_aggregate_routes_and_scanned_dashboard_are_served(tmp_path):
    """Rule: no filesystem routes, even planted files; dashboard uses current scanned manifest."""
    with running(tmp_path) as (_, url, kit, out):
        for path in ("/kit/data/health/ed_visits.csv", "/ed_visits.csv", "/rowmap_ed_visits.csv",
                     "/../kit/metadata/scenarios.json", "/%2e%2e/kit/metadata/scenarios.json",
                     "/privacy_manifest.json", "/out/run-1/ed_visits.csv"):
            assert request(url, path)[0] == 404
        (out / "ed_visits.csv").write_text("planted file must not be served")
        assert request(url, "/ed_visits.csv")[0] == 404
        assert request(url, "/api/run", data={"scenario": "HEALTH-S1"})[0] == 202
        assert result(url)["status"] == "RELEASED"
        status, dashboard = request(url, "/dashboard")
        assert status == 200
        assert "Utility" in dashboard and "HEALTH-S1" in dashboard
        assert "file:///" not in dashboard
        manifest_path = out / "run-1" / "privacy_manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["residualRisks"][0]["note"] = "planted.person@example.test"
        manifest_path.write_text(json.dumps(manifest))
        # Production scan must actually see the planted identifier; this is not an inert fixture.
        assert identifier_shape_counts(manifest).get("EMAIL", 0) > 0
        assert request(url, "/dashboard")[0] == 422


def test_key_is_required_from_server_environment_and_never_echoed(tmp_path):
    """Rule: absent server key -> startup refusal; browser keys rejected, never reflected/logged."""
    kit = build_kit(tmp_path / "missing" / "kit", coarse_qis)
    for key in ("", "too-short"):
        proc = subprocess.Popen(launch_args(kit, tmp_path / "missing" / "out"),
                                env=dict(server_env(), PETS_HMAC_KEY=key), cwd=ROOT,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            assert not proc.stdout.readline(), "server must refuse a missing/short environment key"
            assert proc.wait(timeout=20) == 2
        finally:
            proc.terminate()
            stdout, stderr = proc.communicate(timeout=20)
            assert TEST_KEY not in stdout + stderr
    with running(tmp_path / "valid") as (proc, url, _, _):
        for field in ("key", "PETS_HMAC_KEY", "env", "out", "kit", "created"):
            assert request(url, "/api/run", data={"scenario": "HEALTH-S1", field: TEST_KEY})[0] == 400
        assert json.loads(request(url, "/api/result")[1])["status"] == "IDLE"
    assert TEST_KEY not in "".join(proc.ui_logs)


def test_choose_and_refused_result_views_show_purpose_and_failing_checks(tmp_path):
    """Rule: browser can choose either scenario and see the real gate refusal, never fabricated success."""
    def plant(folder):
        import pandas as pd
        coarse_qis(folder)
        path = folder / "ed_visits.csv"
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        frame.loc[0, "disposition"] = "4111 1111 1111 1111"
        frame.to_csv(path, index=False, lineterminator="\n")

    with running(tmp_path, edit=plant) as (_, url, _, _):
        status, choose = request(url)
        assert status == 200
        assert all(text in choose for text in ("HEALTH-S1", "CS-S1", "Purpose checks", "Privacy floors", "Run scenario"))
        assert request(url, "/api/run", data={"scenario": "HEALTH-S1"})[0] == 202
        report = result(url)
        assert report["status"] == "REFUSED"
        assert any(r["check"] == "rescan.payment-cards" and r["hits"] > 0 for r in report["failures"])
        status, refused = request(url, "/result")
        assert status == 200
        assert "REFUSED" in refused and "rescan.payment-cards" in refused
        assert request(url, "/dashboard")[0] == 422
