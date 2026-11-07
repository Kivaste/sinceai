"""`pets-release draft-policy` through the real CLI, against a fake loopback chat-completions server."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from fake_provider import FakeProvider

GOOD = {
    "recipient": "University research group",
    "trustLevel": "controlled_research",
    "purposeChecks": [{"id": "H-U2", "reason": "length of stay"}],
    "fieldsNeeded": [{"table": "ed_visits", "column": "when", "detail": "generalised", "reason": "time"}],
}
REQUEST = "Researchers want length of stay and revisits for ED visits."
ARGS = ["draft-policy", "--request", REQUEST, "--dataset", "health"]


@pytest.fixture
def server(tmp_path):
    p = FakeProvider(tmp_path / "provider", api_key="sekret-key-123", reply=GOOD)
    yield p
    p.close()


@pytest.fixture
def kit(make_kit):
    return make_kit()


def _env(server, **extra):
    return {"PETS_LLM_ENDPOINT": server["url"], "PETS_LLM_MODEL": "local-model",
            "PETS_LLM_API_KEY": "sekret-key-123", **extra}


def test_refuses_without_allow_network_and_sends_nothing(cli, server, kit):
    r = cli(*ARGS, "--kit", str(kit), env=_env(server))
    assert r.returncode == 2
    assert "--allow-network" in r.stderr
    assert server["bodies"] == []


def test_draft_is_written_for_approval_and_wire_carries_no_cell_values(cli, server, kit, tmp_path):
    out = tmp_path / "draft.json"
    r = cli(*ARGS, "--kit", str(kit), "--allow-network", "--out", str(out), env=_env(server))
    assert r.returncode == 0, r.stderr
    draft = json.loads(out.read_text(encoding="utf-8"))
    assert draft["status"] == "draft" and draft["dataset"] == "health"
    (body,) = server["bodies"]
    wire = body.decode("utf-8")
    assert REQUEST in wire and "ed_visits" in wire  # request and dictionary go out
    for cell in ("00123", "7.11.2026", "010"):  # values of the fixture CSV rows never do
        assert cell not in wire
    assert server["headers"][0][0] == "/v1/chat/completions"
    assert server["headers"][0][1].get("Authorization") == "Bearer sekret-key-123"
    assert "sekret-key-123" not in r.stdout + r.stderr
    assert not (tmp_path / "draft.json.tmp").exists()


def test_draft_goes_to_stdout_without_out(cli, server, kit):
    r = cli(*ARGS, "--kit", str(kit), "--allow-network", env=_env(server))
    assert r.returncode == 0
    assert json.loads(r.stdout)["status"] == "draft"


def test_invalid_model_output_is_refused_and_nothing_is_written(cli, server, kit, tmp_path):
    server["reply"] = dict(GOOD, purposeChecks=[{"id": "H-U99", "reason": "x"}])
    out = tmp_path / "draft.json"
    r = cli(*ARGS, "--kit", str(kit), "--allow-network", "--out", str(out), env=_env(server))
    assert r.returncode == 1
    assert not out.exists()
    assert "H-U99" not in r.stdout + r.stderr


def test_unreachable_provider_is_exit_2(cli, kit):
    env = {"PETS_LLM_ENDPOINT": "http://127.0.0.1:9/v1", "PETS_LLM_MODEL": "m"}
    r = cli(*ARGS, "--kit", str(kit), "--allow-network", env=env)
    assert r.returncode == 2


@pytest.mark.parametrize("drop", ["PETS_LLM_ENDPOINT", "PETS_LLM_MODEL"])
def test_missing_provider_config_is_exit_2(cli, server, kit, drop):
    env = _env(server)
    env.pop(drop)
    r = cli(*ARGS, "--kit", str(kit), "--allow-network", env=env)
    assert r.returncode == 2 and server["bodies"] == []


def test_value_shaped_request_is_refused_before_any_call(cli, server, kit):
    r = cli("draft-policy", "--request", "send 010170-123A records", "--dataset", "health",
                "--kit", str(kit), "--allow-network", env=_env(server))
    assert r.returncode == 2 and server["bodies"] == []


def test_unknown_dataset_is_exit_2(cli, server, kit):
    r = cli("draft-policy", "--request", "x", "--dataset", "nope", "--kit", str(kit),
                "--allow-network", env=_env(server))
    assert r.returncode == 2 and server["bodies"] == []


def test_sender_environment_drops_the_offline_block_only_for_the_sender():
    from pets_release.llm.transport import sender_env
    from pets_release.offline import HOOK_DIR, child_env

    base = child_env({"PATH": "p", "SYSTEMROOT": "system", "TEMP": "temp", "PYTHONPATH": "src"})
    assert base["PETS_OFFLINE"] == "1"
    env = sender_env(base)
    assert "PETS_OFFLINE" not in env
    assert str(HOOK_DIR) not in env["PYTHONPATH"].split(";") + env["PYTHONPATH"].split(":")
    assert env["PYTHONPATH"] == str(Path(__file__).resolve().parents[2] / "src")
    assert base["PETS_OFFLINE"] == "1"  # the caller's environment is untouched


def test_parent_process_stays_offline_even_with_allow_network(make_kit, tmp_path):
    """Only the sender child is exempt: inside draft-policy's own process, sockets are still blocked."""
    import subprocess

    kit = make_kit()
    code = (
        "import socket, sys\n"
        "import pets_release.llm.cli as c\n"
        "import pets_release.cli as top\n"
        "seen = []\n"
        "def probe(url, body, key, timeout):\n"
        "    try:\n"
        "        socket.socket()\n"
        "        seen.append('open')\n"
        "    except OSError:\n"
        "        seen.append('blocked')\n"
        "    raise OSError('stop')\n"
        "orig = c.main\n"
        "c.main = lambda argv: orig(argv, transport=probe)\n"
        f"rc = top.main(['draft-policy','--request','x people','--dataset','health','--kit',{str(kit)!r},"
        "'--allow-network','--endpoint','http://127.0.0.1:9/v1','--model','m'])\n"
        "print(rc, seen)\n"
    )
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src"), "PYTHONUTF8": "1"}
    env.pop("PETS_OFFLINE", None)
    r = subprocess.run([sys.executable, "-c", code], check=False, env=env, capture_output=True, text=True, encoding="utf-8")
    assert r.stdout.strip() == "2 ['blocked']", (r.stdout, r.stderr)
