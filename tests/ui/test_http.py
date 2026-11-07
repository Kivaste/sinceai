"""Approved seam: real loopback HTTP server and real CLI, synthetic mini-kit only."""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request

import pytest

from pets_release.manifest import canonical_bytes
from pets_release.manifest.value_scan import identifier_shape_counts

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "run"))
from run_helpers import CREATED, ROOT, TEST_KEY, build_kit, cli, coarse_qis, run_args


def launch_args(kit, out, *extra):
    return [sys.executable, "-m", "pets_release.ui", "--kit", str(kit), "--out", str(out),
            "--created", CREATED, "--port", "0", *extra]


def server_env():
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), PETS_HMAC_KEY=TEST_KEY,
               PYTHONUTF8="1", TZ="UTC")
    env.pop("PETS_OFFLINE", None)
    return env


def urlopen(request, *, timeout):
    """Synthetic browser boundary: a clean client, even if this pytest worker is guarded.

    Never restore worker sockets or alter the production server/child guard. Only
    this test-only loopback client starts without the inherited offline hook.
    """
    if isinstance(request, str):
        request = Request(request)
    assert urlsplit(request.full_url).hostname == "127.0.0.1"
    node = {"url": request.full_url, "method": request.get_method(), "headers": dict(request.headers),
            "data": None if request.data is None else request.data.decode("utf-8"), "timeout": timeout}
    code = '''
import json, sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen
node = json.load(sys.stdin)
request = Request(node["url"], method=node["method"], headers=node["headers"],
                  data=None if node["data"] is None else node["data"].encode("utf-8"))
try:
    response = urlopen(request, timeout=node["timeout"])
except HTTPError as exc:
    response = exc
with response:
    sys.stdout.buffer.write(str(response.status).encode() + b"\\n" + response.read())
'''
    proc = subprocess.run([sys.executable, "-c", code], input=json.dumps(node).encode(),
                          env=server_env(), capture_output=True, timeout=timeout + 5, check=False)
    assert proc.returncode == 0, "synthetic HTTP client failed"
    status, body = proc.stdout.split(b"\n", 1)
    response = io.BytesIO(body)
    response.status = int(status)
    return response


@contextmanager
def running(tmp_path, *, extra_env=None, edit=coarse_qis, probe=False, verifier_unavailable=False,
            remove_refusal_report=False, record_commands=False, launch_extra=(), measured_kit=False,
            swap_during_verify=False):
    kit = build_kit(tmp_path / "kit", edit)
    if measured_kit:
        prepare_measured_kit(kit)
    env = server_env()
    env.update(extra_env or {})
    command = launch_args(kit, tmp_path / "out", *launch_extra)
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
    output = pathlib.Path({str(output)!r})
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps([blocked, child.returncode != 0 and b"offline guard" in child.stderr]))
    temporary.replace(output)
threading.Thread(target=probe, daemon=True).start()
sys.argv = {command[2:]!r}
runpy.run_module("pets_release.ui", run_name="__main__")
'''
        command = [sys.executable, "-c", code]
    if verifier_unavailable or remove_refusal_report or record_commands or swap_during_verify:
        # Fault only at the external-process boundary, after a real successful run.
        # Never replace a production check with a passing stub.
        code = f'''
import json, pathlib, runpy, subprocess, sys
original = subprocess.run
manifest_path = pathlib.Path({str(tmp_path / 'out' / 'run-1' / 'privacy_manifest.json')!r})
swap = {{}}
def external_process(command, *args, **kwargs):
    if {record_commands!r}:
        with pathlib.Path({str(tmp_path / 'commands.jsonl')!r}).open("a") as handle:
            handle.write(json.dumps(command) + "\\n")
    if {verifier_unavailable!r} and len(command) > 3 and command[3] == "verify" and pathlib.Path({str(tmp_path / 'verifier-unavailable')!r}).exists():
        raise FileNotFoundError("synthetic unavailable executable")
    if swap and len(command) > 3 and command[3] == "verify":
        # A concurrent writer restores the signed manifest A only while a verifier runs.
        manifest_path.write_bytes(swap["A"])
        try:
            return original(command, *args, **kwargs)
        finally:
            manifest_path.write_bytes(swap["B"])
    result = original(command, *args, **kwargs)
    if {swap_during_verify!r} and len(command) > 3 and command[3] == "run" and result.returncode == 0:
        from pets_release.manifest import canonical_bytes
        swap["A"] = manifest_path.read_bytes()
        planted = json.loads(swap["A"])
        planted["residualRisks"][0]["description"] = "Synthetic planted claim"
        swap["B"] = canonical_bytes(planted)
        manifest_path.write_bytes(swap["B"])
    if {remove_refusal_report!r} and len(command) > 3 and command[3] == "run" and result.returncode == 1:
        pathlib.Path({str(tmp_path / 'out' / 'run-1.scoring' / 'refusal_report.json')!r}).unlink()
    return result
subprocess.run = external_process
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
        shapes = identifier_shape_counts(node)
        if path.split("?")[0] in {"/rows", "/api/rows"} and response.status == 200:
            # Independently allow only the contract-checked keyed pseudonym shape, not identifiers.
            shapes.pop("HEX64_OUTSIDE_TOKEN", None)
        assert shapes == {}, "HTTP response contains an identifier shape"
        assert TEST_KEY not in body
        return response.status, body


def test_non_loopback_bind_is_refused(tmp_path):
    """Rule: only literal 127.0.0.1 may bind; wildcard/LAN/hostname -> usage refusal."""
    kit = build_kit(tmp_path / "kit", coarse_qis)
    for host in ("0.0.0.0", "192.0.2.1", "localhost", "::1"):
        proc = subprocess.run(launch_args(kit, tmp_path / "out", "--host", host), env=server_env(),
                              cwd=ROOT, capture_output=True, text=True, timeout=20, check=False)
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
    """Rule: default HTTP run omits --plan and matches the CLI's default search bytes."""
    with running(tmp_path, record_commands=True) as (_, url, kit, out):
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
        attested = [c["status"] for c in json.loads((out / "run-1" / "privacy_manifest.json").read_bytes())["gate"]["checks"]]
        assert report["gate"]["passed"] + report["gate"]["notApplicable"] == report["gate"]["total"] == len(attested)
        signed = json.loads((out / "run-1" / "privacy_manifest.json").read_bytes())
        person_k = next(c for c in signed["gate"]["checks"] if c["check"] == "producer.person-k")
        # Only the verified manifest is a source: the plain run has no measured minimum k, and the
        # unsigned scoring sidecar is never read.
        assert signed["measured"]["privacy"]["status"] == "not_measured"
        assert report["personK"] == {"belowK": 0, "persons": person_k["denominator"]["n"], "minK": None, "k": 5}
        assert report["exportAssertions"] and report["assertionEvidence"]
        assert report["measured"]["utility"]
        assert report["measured"]["privacy"]["status"] == "not_measured"
        release = out / "run-1"
        assert (release / "privacy_manifest.json").is_file()
        other = tmp_path / "cli-release"
        proc = cli("run", "--scenario", "HEALTH-S1", "--kit", str(kit), "--out", str(other),
                   "--created", CREATED)
        assert proc.returncode == 0, "reference CLI failed"
        commands = [json.loads(line) for line in (tmp_path / "commands.jsonl").read_text().splitlines()]
        run = next(command for command in commands if command[3] == "run")
        assert "--plan" not in run, "default UI must preserve the CLI search default"
        assert {p.name: p.read_bytes() for p in release.iterdir()} == {
            p.name: p.read_bytes() for p in other.iterdir()}


def prepare_measured_kit(kit):
    """Hand-made metadata/aggregate baselines for the existing synthetic health tables."""
    path = kit / "metadata" / "scenarios.json"
    scenarios = json.loads(path.read_text())
    scenarios[0]["utility_requirements"] = ["H-U2", "H-U4", "H-U6", "H-U7", "H-U8"]
    path.write_text(json.dumps(scenarios), encoding="utf-8")
    (kit / "metadata" / "field_catalog.csv").write_text(
        "dataset,table,column,privacy_role,data_kind,subtype\n"
        "health,ed_visits,visit_id,record_key,identifier,id\n"
        "health,lab_results,lab_id,record_key,identifier,id\n"
        "health,clinical_notes,note_id,record_key,identifier,id\n"
        "health,published_weekly_stats,stat_id,record_key,identifier,id\n"
        "health,ed_visits,patient_name,direct_identifier,text,name\n"
        "health,ed_visits,municipality,quasi_identifier,categorical,location\n",
        encoding="utf-8")
    benchmark = {"baselines": {f"{name}_health": {
        "privacy": 0.5, "worst_reid": 0.5, "residual_identifiers": 0.0,
        "utility_by_scenario": {"HEALTH-S1": 1.0},
        "utility_tasks": {task: 1.0 for task in scenarios[0]["utility_requirements"]},
    } for name in ("B0", "B2", "B2K")}}
    (kit / "results").mkdir()
    (kit / "results" / "benchmark.json").write_text(json.dumps(benchmark), encoding="utf-8")


def test_measured_mode_matches_wire_bytes_and_shows_privacy(tmp_path):
    """HTTP + CLI seam: opt-in measurement runs the real offline measurer and both verify tiers."""
    with running(tmp_path, measured_kit=True, launch_extra=("--measured",)) as (_, url, kit, out):
        assert request(url, "/api/run", data={"scenario": "HEALTH-S1"})[0] == 202
        report = result(url)
        assert report["status"] == "RELEASED", report
        assert report["steps"] == [{"name": "measure.wire", "exit": 0},
                                   {"name": "verify (limited)", "exit": 0},
                                   {"name": "verify --full", "exit": 0}]
        assert report["measured"]["privacy"]["status"] == "measured"
        privacy = next(c for c in report["measured"]["privacy"]["components"] if c["component"] == "privacy")
        page = request(url, "/demo/measurements")[1]
        assert f'<tr><td>privacy</td><td>{privacy["before"]}</td><td>{privacy["after"]}</td></tr>' in page
        reference = tmp_path / "reference"
        proc = subprocess.run([sys.executable, "-m", "pets_release.measure.wire", "--scenario", "HEALTH-S1",
                               "--kit", str(kit), "--out", str(reference), "--created", CREATED],
                              env=server_env(), cwd=ROOT, capture_output=True, timeout=240, check=False)
        assert proc.returncode == 0, "reference measured CLI failed"
        assert {p.name: p.read_bytes() for p in (out / "run-1").iterdir()} == {
            p.name: p.read_bytes() for p in reference.iterdir()}


def test_explicit_hand_plan_matches_cli_bytes(tmp_path):
    """HTTP/CLI seam: the optional server hand plan is forwarded explicitly and remains usable."""
    with running(tmp_path, record_commands=True, launch_extra=("--plan", "hand")) as (_, url, kit, out):
        assert request(url, "/api/run", data={"scenario": "HEALTH-S1"})[0] == 202
        assert result(url)["status"] == "RELEASED"
        commands = [json.loads(line) for line in (tmp_path / "commands.jsonl").read_text().splitlines()]
        run = next(command for command in commands if command[3] == "run")
        assert run[-2:] == ["--plan", "hand"]
        reference = tmp_path / "reference"
        assert cli(*run_args(kit, reference)).returncode == 0
        assert {p.name: p.read_bytes() for p in (out / "run-1").iterdir()} == {
            p.name: p.read_bytes() for p in reference.iterdir()}


def test_client_plan_overrides_are_refused_without_starting_a_job(tmp_path):
    """HTTP/CLI seam: untrusted plan values never reach the production CLI."""
    with running(tmp_path, record_commands=True) as (_, url, _, out):
        for value in ("measured", "unknown", "hand", None, {"plan": "hand"}):
            assert request(url, "/api/run", data={"scenario": "HEALTH-S1", "plan": value})[0] == 400
        assert json.loads(request(url, "/api/result")[1])["status"] == "IDLE"
        assert not (tmp_path / "commands.jsonl").exists()
        assert not list(out.iterdir())


def test_duplicate_key_run_request_is_refused_without_starting_a_job(tmp_path):
    """#131 (HTTP seam): the run request parses strictly; a duplicate "scenario" whose first value is not a
    scenario (last value valid) is 400 and starts nothing (was: last value kept, job started)."""
    with running(tmp_path, record_commands=True) as (_, url, _, out):
        parts = urlsplit(url)
        req = Request(f"{parts.scheme}://{parts.netloc}/api/run?{parts.query}", method="POST",
                      data=b'{"scenario": "NOT-A-SCENARIO", "scenario": "HEALTH-S1"}',
                      headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=60) as response:
            assert response.status == 400
        assert json.loads(request(url, "/api/result")[1])["status"] == "IDLE"
        assert not (tmp_path / "commands.jsonl").exists()
        assert not list(out.iterdir())


def test_unsupported_server_plan_is_refused_at_startup(tmp_path):
    """CLI seam: no advertised server plan can forward the unsupported measured value."""
    kit = build_kit(tmp_path / "kit", coarse_qis)
    for plan in ("measured", "unknown"):
        proc = subprocess.run(launch_args(kit, tmp_path / "out", "--plan", plan), env=server_env(),
                              cwd=ROOT, capture_output=True, text=True, timeout=20, check=False)
        assert proc.returncode == 2
        assert "invalid choice" in proc.stderr
        assert not (tmp_path / "out").exists()


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


def test_http_client_survives_guarded_pytest_worker():
    """HTTP seam: prior in-process CLI calls cannot disable the synthetic browser client."""
    code = (
        "from pets_release.offline import install; install(); import pytest\n"
        "result = pytest.main(['-q', '-p', 'no:cacheprovider', "
        "'tests/ui/test_http.py::test_server_and_children_are_offline_while_loopback_http_works'])\n"
        "import socket\n"
        "try: socket.socket()\n"
        "except OSError: pass\n"
        "else: raise AssertionError('pytest worker guard was weakened')\n"
        "raise SystemExit(result)\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], env=server_env(), cwd=ROOT,
                          capture_output=True, text=True, timeout=60, check=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_only_aggregate_routes_and_scanned_dashboard_are_served(tmp_path):
    """Rule: no filesystem routes, even planted files; dashboard uses current scanned manifest."""
    with running(tmp_path) as (_, url, _kit, out):
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
        manifest["residualRisks"][0]["description"] = "planted.person@example.test"
        manifest_path.write_bytes(canonical_bytes(manifest))
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
        frame = pd.read_csv(path, dtype=str, keep_default_na=False, na_filter=False)
        frame.loc[0, "disposition"] = "4111 1111 1111 1111"
        frame.to_csv(path, index=False, lineterminator="\n")

    # Keep the planted field in this deliberate gate-refusal demonstration;
    # the default search correctly withholds this unnecessary field.
    with running(tmp_path, edit=plant, launch_extra=("--plan", "hand")) as (_, url, _, _):
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


def test_unsupported_methods_and_non_ascii_tokens_still_fail_closed(tmp_path):
    """Rule: every verb authenticates; malformed credentials never produce reflected default errors."""
    with running(tmp_path) as (_, url, _, _):
        for verb in ("HEAD", "OPTIONS", "PUT", "DELETE", "TRACE", "BREW"):
            assert request(url, "/api/run", auth=False, method=verb)[0] == 403
            assert request(url, "/api/run", method=verb)[0] == 405
        assert request(url, "/?token=%C3%A4", auth=False)[0] == 403
        assert request(url, "/?" + urlsplit(url).query + "&token=", auth=False)[0] == 403


def test_planted_server_key_in_manifest_cannot_reach_browser(tmp_path):
    """Rule: even an identifier-shape-free key planted into an otherwise valid artefact is refused."""
    with running(tmp_path) as (_, url, _, out):
        assert request(url, "/api/run", data={"scenario": "HEALTH-S1"})[0] == 202
        assert result(url)["status"] == "RELEASED"
        path = out / "run-1" / "privacy_manifest.json"
        manifest = json.loads(path.read_text())
        manifest["residualRisks"][0]["description"] = TEST_KEY
        assert identifier_shape_counts(TEST_KEY) == {}
        path.write_bytes(canonical_bytes(manifest))
        from pets_release.manifest import validate_manifest_file
        assert validate_manifest_file(path.parent) == []
        # Read directly so the precise regression is the response, not the helper's key assertion.
        target = url.replace("/?", "/dashboard?")
        try:
            response = urlopen(target, timeout=30)
        except HTTPError as exc:
            response = exc
        with response:
            assert response.status == 422, "planted environment key reached an HTTP artefact"
            body = response.read().decode()
            assert TEST_KEY not in body and identifier_shape_counts(body) == {}


def test_cs_attempt_reports_the_production_cli_failure_without_a_release(tmp_path):
    """Coverage for the fenced upstream limitation: CS policy is selectable, not falsely RELEASED."""
    with running(tmp_path) as (_, url, kit, out):
        reference = cli("run", "--scenario", "CS-S1", "--kit", str(kit), "--out", str(tmp_path / "reference"),
                        "--created", CREATED)
        assert reference.returncode == 2  # this mini-kit has only health tables, even after CS support lands
        assert request(url, "/api/run", data={"scenario": "CS-S1"})[0] == 202
        report = result(url)
        assert report["status"] == "FAILED"
        assert report["steps"] == [{"name": "run", "exit": reference.returncode}]
        assert not (out / "run-1").exists()
        assert "FAILED" in request(url, "/result")[1]
        assert "Not yet supported by this build" in request(url, "/result")[1]
        assert "Not yet supported by this build" in request(url)[1]


def test_refusal_without_report_is_explicit(tmp_path):
    """HTTP + real CLI seam: unavailable scoring storage -> explicit missing-report notice."""
    with running(tmp_path) as (_, url, _, out):
        (out / "run-1.scoring").write_text("synthetic storage obstacle")
        assert request(url, "/api/run", data={"scenario": "HEALTH-S1"})[0] == 202
        assert result(url)["status"] == "FAILED"
        status, page = request(url, "/result")
        assert status == 200
        assert "No refusal report available" in page


def test_failed_full_verification_is_not_pending(tmp_path):
    """HTTP + CLI seam: source disappears after run -> real full verify fails visibly."""
    with running(tmp_path) as (_, url, kit, _):
        assert request(url, "/api/run", data={"scenario": "HEALTH-S1"})[0] == 202
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            state = json.loads(request(url, "/api/result")[1])
            if len(state["steps"]) >= 2:
                break
            time.sleep(0.02)
        else:
            raise AssertionError("limited verification never started")
        (kit / "data" / "health" / "ed_visits.csv").unlink()
        report = result(url)
        assert report["status"] == "FAILED"
        assert report["steps"][2]["exit"] != 0
        # A release that failed a verify tier publishes no proof: no gate, assertions, scores or met targets.
        for field in ("gate", "exportAssertions", "assertionEvidence", "measured", "personK", "sacrifices"):
            assert field not in report, field
        assert all(t["status"] == "not measured" for t in report["targets"])
        page = request(url, "/result")[1]
        assert 'Controller verification</div><div class="value">Failed</div>' in page
        assert "Export assertions" not in page and "checks passed" not in page
        assert "Export assertions" not in request(url, "/demo/measurements")[1]
        assert "Gate " not in request(url, "/demo/limitations")[1]


def test_concurrent_run_is_refused_with_a_busy_message(tmp_path):
    """HTTP + CLI seam: a second start cannot replace the active release."""
    with running(tmp_path) as (_, url, _, out):
        assert request(url, "/api/run", data={"scenario": "HEALTH-S1"})[0] == 202
        status, body = request(url, "/api/run", data={"scenario": "HEALTH-S1"})
        assert status == 409
        assert json.loads(body) == {"started": False, "message": "Busy, run in progress"}
        assert result(url)["status"] == "RELEASED"
        assert not (out / "run-2").exists()


@pytest.mark.parametrize("case", ["first-rows", "extra", "rowmap", "truth", "raw", "escape", "tampered", "missing", "bad-contract"])
def test_protected_rows_require_current_verification_and_manifest_membership(tmp_path, case):
    """HTTP + real CLI seam: only exact, verified protected bytes can reach the rows view."""
    import pandas as pd

    with running(tmp_path) as (_, url, kit, out):
        assert request(url, "/api/run", data={"scenario": "HEALTH-S1"})[0] == 202
        assert result(url)["status"] == "RELEASED"
        release = out / "run-1"
        path = "/api/rows?file=ed_visits.csv&limit=2"
        if case == "first-rows":
            status, body = request(url, path)
            assert status == 200
            table = json.loads(body)["tables"][0]
            expected = pd.read_csv(release / "ed_visits.csv", dtype=str, keep_default_na=False, na_filter=False)
            assert table == {"file": "ed_visits.csv", "columns": list(expected.columns),
                             "rows": expected.head(2).values.tolist()}
            page = request(url, "/rows")[1]
            assert "Protected release rows" in page
            assert "Synthetic kit data © Since AI ry, CC BY 4.0. In a real deployment only the recipient sees this view." in page
            assert len(json.loads(request(url, "/api/rows?limit=25")[1])["tables"][0]["rows"]) <= 25
            assert request(url, "/api/rows?limit=26")[0] == 422
            return
        if case in {"extra", "rowmap", "truth"}:
            name = {"extra": "extra.csv", "rowmap": "rowmap_ed_visits.csv", "truth": "truth/hidden.csv"}[case]
            planted = release / name
            planted.parent.mkdir(exist_ok=True)
            planted.write_text("never_serve\nsynthetic-canary\n")
            path = "/api/rows?file=" + name
        elif case == "raw":
            path = "/api/rows?file=" + str(kit / "data" / "health" / "ed_visits.csv").replace("\\", "/")
        elif case == "escape":
            path = "/api/rows?file=../run-1.scoring/rowmap_ed_visits.csv"
        elif case == "tampered":
            with (release / "ed_visits.csv").open("a") as handle:
                handle.write("synthetic-canary\n")
        elif case == "missing":
            (release / "privacy_manifest.json").unlink()
        elif case == "bad-contract":
            import hashlib
            table = pd.read_csv(release / "ed_visits.csv", dtype=str, keep_default_na=False, na_filter=False)
            table["uncontracted"] = "synthetic-canary"
            table.to_csv(release / "ed_visits.csv", index=False, lineterminator="\n")
            manifest_path = release / "privacy_manifest.json"
            manifest = json.loads(manifest_path.read_bytes())
            manifest["bindings"]["files"]["ed_visits.csv"] = hashlib.sha256((release / "ed_visits.csv").read_bytes()).hexdigest()
            manifest_path.write_bytes(canonical_bytes(manifest))
            # Digests match: only the fresh production checks can catch the extra column.
            from pets_release.manifest import validate_manifest_file
            assert validate_manifest_file(release) == []
        status, body = request(url, path)
        assert status == 422
        assert "synthetic-canary" not in body
        # A fresh display must fail too, even though the original run verified successfully.
        if case in {"tampered", "missing", "extra", "rowmap", "truth", "bad-contract"}:
            assert request(url, "/rows")[0] == 422
            # A changed, missing or extra entry withdraws the run-time proof as well.
            state = json.loads(request(url, "/api/result")[1])
            assert state["status"] == "CHANGED"
            # A prior verify pass is never rendered as current once the bytes changed.
            assert not any(s["name"].startswith("verify") and s["exit"] == 0 for s in state["steps"])
            page = request(url, "/result")[1]
            assert "verify --full · passed" not in page and "Controller verification" not in page
            assert "passed (full)" not in request(url, "/demo/limitations")[1]


def test_targets_show_measured_values_and_never_assume_missing_results_pass(tmp_path):
    """HTTP + CLI seam: policy floors/strict utility thresholds retain numbers and unknowns."""
    with running(tmp_path) as (_, url, _, _):
        assert request(url, "/api/run", data={"scenario": "HEALTH-S1"})[0] == 202
        report = result(url)
        assert report["status"] == "RELEASED"
        targets = {t["name"]: t for t in report["targets"]}
        assert targets["qi-k"]["threshold"] == ">= 5"
        # Plain run: no measured minimum k in the signed manifest; the verified producer.person-k
        # record (0 persons below the contract k) is the evidence shown.
        assert targets["qi-k"]["measured"] == "0 persons below k=5"
        assert targets["qi-k"]["status"] == "met"
        assert targets["H-U2"]["threshold"] == ">= 0.9"
        assert targets["H-U2"]["measured"] >= 0.9
        assert targets["ed_visits.patient_name"]["measured"] == "withheld"
        assert targets["ed_visits.patient_name"]["status"] == "met"
        assert targets["H-U4 sacrifice floor"]["threshold"] == ">= 0.6"
        # The signed manifest records these sacrifices as adopted: a floor is an accepted sacrifice,
        # never "met" as if it were the original target.
        assert {s["check"] for s in report["sacrifices"]} >= {"H-U4", "H-U6", "H-U8"}
        for check in ("H-U4", "H-U6", "H-U8"):
            assert targets[check + " sacrifice floor"]["status"] == "accepted sacrifice"
        assert "accepted sacrifice" in request(url, "/demo/measurements")[1]
        assert "Targets met / not met" in request(url, "/result")[1]
        assert request(url, "/api/run", data={"scenario": "CS-S1"})[0] == 202
        failed = result(url)
        assert failed["status"] == "FAILED"
        assert failed["targets"]
        assert all(t["status"] == "not measured" and t["measured"] is None for t in failed["targets"])
        assert "not measured" in request(url, "/result")[1]


def test_five_demonstration_views_project_production_inventory_and_manifest(tmp_path):
    """HTTP + CLI seam: five distinct jury views expose only real metadata and measured aggregates."""
    with running(tmp_path) as (_, url, _, _):
        assert request(url, "/api/run", data={"scenario": "HEALTH-S1"})[0] == 202
        report = result(url)
        assert report["status"] == "RELEASED"
        for route, title in (("risks", "Data types and privacy risks found"), ("pets", "PETs chosen and why"),
                             ("protected", "The protected output"), ("measurements", "Measured privacy and utility"),
                             ("limitations", "Scenario and limitations")):
            status, page = request(url, "/demo/" + route)
            assert status == 200
            assert title in page
            assert "not measured" in page or route in {"pets", "protected", "limitations"}
        risks = request(url, "/demo/risks")[1]
        assert "Production detector" in risks and "direct_identifier" in risks and "patient_name" in risks
        assert "Baseline" in risks and "Attacker" in risks
        pets = request(url, "/demo/pets")[1]
        assert "keyed_pseudonym" in pets and "H-U7" in pets
        protected = request(url, "/demo/protected")[1]
        assert "Before (field level only)" in protected and "age.band10" in protected
        measurements = request(url, "/demo/measurements")[1]
        assert all(word in measurements for word in ("privacy", "utility", "composite", "Targets met / not met"))
        limitations = request(url, "/demo/limitations")[1]
        assert all(word in limitations for word in ("Recipient", "Trust", "Not-fit-for", "Residual risks", "Sacrifices"))


def test_optional_demo_banner_is_visible_and_escaped(tmp_path):
    """HTTP seam: an operator banner is optional, shared across views and HTML-escaped."""
    with running(tmp_path / "plain") as (_, url, _, _):
        assert 'role="status"' not in request(url)[1]
    with running(tmp_path / "demo", extra_env={"PETS_UI_DEMO_BANNER": "Demo <synthetic> only"}) as (_, url, _, _):
        for route in ("/", "/result", "/demo/risks"):
            status, page = request(url, route)
            assert status == 200
            assert 'role="status"' in page
            assert "Demo &lt;synthetic&gt; only" in page and "<synthetic>" not in page


def test_unavailable_display_verifier_never_serves_rows(tmp_path):
    """HTTP + external-process seam: execution failure must not reuse the run's successful verify."""
    with running(tmp_path, verifier_unavailable=True) as (_, url, _, _):
        assert request(url, "/api/run", data={"scenario": "HEALTH-S1"})[0] == 202
        assert result(url)["status"] == "RELEASED"
        assert request(url, "/api/rows?limit=1")[0] == 200
        (tmp_path / "verifier-unavailable").touch()
        assert request(url, "/api/rows?limit=1")[0] == 422
        assert request(url, "/rows")[0] == 422


def test_planted_release_junction_outside_root_is_refused(tmp_path):
    """HTTP + filesystem seam: a planted alias to a valid release elsewhere cannot grant row access."""
    with running(tmp_path) as (_, url, _, out):
        assert request(url, "/api/run", data={"scenario": "HEALTH-S1"})[0] == 202
        assert result(url)["status"] == "RELEASED"
        assert request(url, "/api/rows?limit=1")[0] == 200
        release = out / "run-1"
        elsewhere = tmp_path / "elsewhere"
        release.rename(elsewhere)
        if os.name == "nt":
            proc = subprocess.run(["cmd", "/c", "mklink", "/J", str(release), str(elsewhere)],
                                  capture_output=True, check=False)
            assert proc.returncode == 0
        else:
            release.symlink_to(elsewhere, target_is_directory=True)
        assert request(url, "/api/rows?limit=1")[0] == 422


def swap_cells_and_rebind_digest(release, kit):
    """Plant a contract-valid cell swap, re-bind its digest and leave the signature stale.

    Preconditions use the real CLI so the fixture is not inert: the recipient tier still
    passes (digests and release checks agree), only the signature-checking tier refuses.
    """
    import hashlib
    import re

    import pandas as pd

    path = release / "ed_visits.csv"
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, na_filter=False)
    column = next(c for c in frame.columns
                  if all(re.fullmatch(r"[0-9a-f]{64}", v) for v in frame[c]) and frame.at[0, c] != frame.at[1, c])
    frame.loc[[0, 1], column] = [frame.at[1, column], frame.at[0, column]]
    frame.to_csv(path, index=False, lineterminator="\n")
    manifest_path = release / "privacy_manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["bindings"]["files"]["ed_visits.csv"] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest_path.write_bytes(canonical_bytes(manifest))
    assert cli("verify", str(release)).returncode == 0, "fixture must pass the limited tier"
    assert cli("verify", "--full", "--kit", str(kit), str(release)).returncode == 1, "stale signature must fail full"


def test_digest_consistent_cell_swap_with_stale_signature_is_never_served(tmp_path):
    """HTTP + real CLI seam: rows and dashboard need the signature-checking tier at display time."""
    with running(tmp_path) as (_, url, kit, out):
        assert request(url, "/api/run", data={"scenario": "HEALTH-S1"})[0] == 202
        assert result(url)["status"] == "RELEASED"
        assert request(url, "/api/rows?limit=2")[0] == 200
        assert request(url, "/dashboard")[0] == 200
        page = request(url, "/result")[1]
        assert "Verified (limited + full) at" in page and "checks passed" in page
        swap_cells_and_rebind_digest(out / "run-1", kit)
        for path in ("/api/rows?limit=2", "/api/rows?file=ed_visits.csv", "/rows", "/dashboard"):
            assert request(url, path)[0] == 422, path
        # Proof pages never re-run full verify, so they must not reuse the run-time pass for
        # bytes that changed since: no RELEASED, gate, assertions, person-k or met targets.
        state = json.loads(request(url, "/api/result")[1])
        assert state["status"] == "CHANGED"
        for field in ("gate", "exportAssertions", "assertionEvidence", "personK", "targets", "measured"):
            assert field not in state, field
        assert not any(s["name"].startswith("verify") and s["exit"] == 0 for s in state["steps"])
        page = request(url, "/result")[1]
        assert "changed since verification" in page
        for text in ("The gate passed", "checks passed", "Export assertions", "below k", ">met<",
                     "verify --full · passed", "verify (limited) · passed", "Controller verification"):
            assert text not in page, text
        for item in ("risks", "pets", "protected", "measurements", "limitations"):
            demo = request(url, "/demo/" + item)[1]
            for text in ("Gate ", ">met<", "accepted sacrifice", "keyed_pseudonym", "age.band10",
                         "passed (full)", "passed (limited)"):
                assert text not in demo, (item, text)


def test_planted_schema_valid_manifest_claim_is_not_rendered_as_dashboard(tmp_path):
    """HTTP + real CLI seam: a re-written manifest with a stale signature is not the signed release."""
    with running(tmp_path) as (_, url, kit, out):
        assert request(url, "/api/run", data={"scenario": "HEALTH-S1"})[0] == 202
        assert result(url)["status"] == "RELEASED"
        release = out / "run-1"
        manifest = json.loads((release / "privacy_manifest.json").read_bytes())
        manifest["residualRisks"][0]["description"] = "Synthetic planted claim"
        (release / "privacy_manifest.json").write_bytes(canonical_bytes(manifest))
        from pets_release.manifest import validate_manifest_file
        assert validate_manifest_file(release) == []
        assert cli("verify", str(release)).returncode == 0, "fixture must pass the limited tier"
        status, body = request(url, "/dashboard")
        assert status == 422
        assert "Synthetic planted claim" not in body


def test_manifest_swapped_back_only_while_verifiers_run_publishes_no_proof(tmp_path):
    """HTTP + real CLI seam: A->B->A writer. The live folder holds an unsigned manifest B except
    while a verifier subprocess runs (then the signed A). Proof must come only from the bytes
    that both tiers verified, so B's claims are never published as RELEASED."""
    with running(tmp_path, swap_during_verify=True) as (_, url, _, out):
        assert request(url, "/api/run", data={"scenario": "HEALTH-S1"})[0] == 202
        report = result(url)
        live = (out / "run-1" / "privacy_manifest.json").read_bytes()
        assert b"Synthetic planted claim" in live, "fixture must leave B in the live folder"
        from pets_release.manifest import validate_manifest_file
        assert validate_manifest_file(out / "run-1") == [], "B must be schema-valid: only the signature differs"
        assert report["status"] != "RELEASED"
        assert "gate" not in report and "residualRisks" not in report
        assert "Synthetic planted claim" not in request(url, "/api/result")[1]
        assert "Synthetic planted claim" not in request(url, "/demo/limitations")[1]


def test_gate_fraction_counts_only_pass_and_shows_not_applicable_separately(tmp_path):
    """HTTP + real CLI seam: not_applicable is never folded into the gate pass count."""
    with running(tmp_path) as (_, url, _, out):
        assert request(url, "/api/run", data={"scenario": "HEALTH-S1"})[0] == 202
        report = result(url)
        assert report["status"] == "RELEASED"
        statuses = [c["status"] for c in
                    json.loads((out / "run-1" / "privacy_manifest.json").read_bytes())["gate"]["checks"]]
        # The mini-kit contract declares text-form columns, so no record here is not_applicable;
        # tests/ui/test_projection.py covers that state at the projection seam.
        assert report["gate"] == {"passed": statuses.count("pass"),
                                  "notApplicable": statuses.count("not_applicable"),
                                  "total": len(statuses)}
        page = request(url, "/result")[1]
        fraction = f'{report["gate"]["passed"]}/{report["gate"]["total"]}'
        assert fraction in page and f'{report["gate"]["notApplicable"]} not applicable' in page
        limitations = request(url, "/demo/limitations")[1]
        assert f'Gate {fraction} passed' in limitations
        assert f'{report["gate"]["notApplicable"]} not applicable' in limitations


def test_refused_cli_with_removed_report_keeps_the_explicit_unknown(tmp_path):
    """HTTP + filesystem fault: a real exit-1 refusal whose report disappears remains refused, not empty."""
    with running(tmp_path, edit=None, remove_refusal_report=True) as (_, url, _, _):
        assert request(url, "/api/run", data={"scenario": "HEALTH-S1"})[0] == 202
        report = result(url)
        assert report["status"] == "REFUSED" and report["steps"][-1]["exit"] == 1
        assert "No refusal report available" in request(url, "/result")[1]
        assert request(url, "/api/rows")[0] == 422
