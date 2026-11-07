"""Alignment self-check: drafted purpose checks vs. the official required tasks of a packaged scenario."""
from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from pets_release.llm.alignment import AlignmentError, align, required_tasks

DRAFT = {"purposeChecks": [{"id": "H-U2", "reason": "a"}, {"id": "H-U4", "reason": "b"}, {"id": "H-U8", "reason": "c"}]}


def test_recovered_missing_and_extra_are_counted():
    r = align(DRAFT, ["H-U2", "H-U4", "H-U6", "H-U7", "H-U8"])
    assert (r["recovered"], r["required"]) == (3, 5)
    assert r["missing"] == ["H-U6", "H-U7"] and r["extra"] == []
    assert r["summary"] == "recovered 3 of 5 required analyses (0 extra)"


def test_extra_analyses_are_reported():
    r = align({"purposeChecks": [{"id": "H-U2", "reason": "a"}, {"id": "H-U1", "reason": "b"}]}, ["H-U2"])
    assert r["extra"] == ["H-U1"] and r["recovered"] == 1


def test_required_tasks_come_from_the_scenario_and_only_packaged_scenarios_qualify():
    scen = {"id": "HEALTH-S1", "utility_requirements": ["H-U8", "H-U2"]}
    assert required_tasks(scen) == ["H-U2", "H-U8"]
    with pytest.raises(AlignmentError):
        required_tasks({"id": "MOB-S1", "utility_requirements": ["M-U1"]})
    with pytest.raises(AlignmentError):
        required_tasks({"id": "HEALTH-S1", "utility_requirements": []})


def test_cli_self_check_reports_recovered_n_of_m(cli, make_kit):
    reply = {
        "recipient": "University research group",
        "trustLevel": "controlled_research",
        "purposeChecks": [{"id": "H-U2", "reason": "x"}],
        "fieldsNeeded": [{"table": "ed_visits", "column": "when", "detail": "exact", "reason": "x"}],
    }

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            p = json.dumps({"choices": [{"message": {"content": json.dumps(reply)}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(p)))
            self.end_headers()
            self.wfile.write(p)

        def log_message(self, *a):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        kit = make_kit(scenarios=[{
            "id": "HEALTH-S1", "dataset": "health", "recipient": "A research group", "purpose": "Analyse stays",
            "utility_requirements": ["H-U2", "H-U4"],
        }])
        env = {"PETS_LLM_ENDPOINT": f"http://127.0.0.1:{httpd.server_address[1]}/v1", "PETS_LLM_MODEL": "m"}
        r = cli("draft-policy", "--align-with", "HEALTH-S1", "--kit", str(kit), "--allow-network", env=env)
    finally:
        httpd.shutdown()
        httpd.server_close()
    assert r.returncode == 0, r.stderr
    assert "recovered 1 of 2 required analyses" in r.stderr
    assert json.loads(r.stdout)["status"] == "draft"
