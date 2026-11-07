"""CLI seam: a local sender double reports names only; no socket is opened."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from pets_release.offline import child_env


def _draft_with_local_sender(make_kit, *, missing=None, empty=False):
    kit = make_kit()
    planted = kit / "planted-pythonpath"
    planted.mkdir()
    (planted / "sitecustomize.py").write_text(
        "import os\nos.environ['PLANTED_PATH_EXECUTED'] = 'yes'\n", encoding="utf-8")
    reply = {"choices": [{"message": {"content": json.dumps({
        "recipient": "University research group",
        "trustLevel": "controlled_research",
        "purposeChecks": [{"id": "H-U2", "reason": "length of stay"}],
        "fieldsNeeded": [{"table": "ed_visits", "column": "when",
                          "detail": "generalised", "reason": "time"}],
    })}}]}
    # Replace only the executable target at the OS boundary. Production CLI,
    # request screens, environment builder and subprocess launch all still run.
    fake_sender = (
        "import json, os, sys\n"
        "sys.stdin.buffer.read()\n"
        "print(json.dumps(sorted(os.environ)), file=sys.stderr)\n"
        f"sys.stdout.write({json.dumps(reply)!r})\n"
    )
    code = f"""
import json, os, socket, subprocess, sys
from pets_release.cli import main
original_run = subprocess.run
def local_sender(argv, **kwargs):
    assert argv[1:] == ['-m', 'pets_release.llm.sender']
    assert 'PETS_HMAC_KEY' in os.environ
    try:
        socket.socket()
    except OSError:
        print('parent-offline=yes', file=sys.stderr)
    else:
        raise AssertionError('parent socket guard missing')
    result = original_run([argv[0], '-c', {fake_sender!r}], **kwargs)
    print('sender-names=' + result.stderr.decode('utf-8').strip(), file=sys.stderr)
    return result
subprocess.run = local_sender
missing = {missing!r}
if missing:
    if {empty!r}:
        os.environ[missing] = ''
    else:
        os.environ.pop(missing, None)
raise SystemExit(main(['draft-policy', '--request', 'Researchers need length of stay',
    '--dataset', 'health', '--kit', {str(kit)!r}, '--allow-network',
    '--endpoint', 'http://127.0.0.1:9/v1', '--model', 'local-model']))
"""
    env = child_env({**os.environ,
        "PYTHONPATH": os.pathsep.join([str(Path(__file__).resolve().parents[2] / "src"), str(planted)]),
        "PETS_HMAC_KEY": "synthetic-hmac-not-for-the-sender",
        "UNRELATED_SECRET": "synthetic-other-secret",
        "PETS_LLM_UNUSED_SECRET": "synthetic-unused-secret",
        "PETS_LLM_API_KEY": "synthetic-api-key",
    })
    return subprocess.run([sys.executable, "-c", code], env=env, capture_output=True,
                          text=True, encoding="utf-8", check=False, timeout=30)


def test_cli_sender_receives_only_required_environment_names(make_kit):
    result = _draft_with_local_sender(make_kit)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "draft"
    assert "parent-offline=yes" in result.stderr
    names = json.loads(next(line.removeprefix("sender-names=")
                            for line in result.stderr.splitlines() if line.startswith("sender-names=")))
    assert "PETS_HMAC_KEY" not in names
    assert "UNRELATED_SECRET" not in names
    assert "PETS_LLM_UNUSED_SECRET" not in names
    assert "PETS_OFFLINE" not in names
    assert "PLANTED_PATH_EXECUTED" not in names
    assert {"PETS_LLM_API_KEY", "PETS_LLM_SEND_URL", "PETS_LLM_SEND_TIMEOUT"} <= set(names)
    assert set(names) <= {
        "PATH", "SYSTEMROOT", "TEMP", "TMP", "LC_CTYPE",
        "PYTHONPATH", "PYTHONUTF8", "PYTHONDONTWRITEBYTECODE", "TZ",
        "PETS_LLM_API_KEY", "PETS_LLM_SEND_URL", "PETS_LLM_SEND_TIMEOUT",
    }


@pytest.mark.parametrize("missing", ["PATH"] + (["SYSTEMROOT", "TEMP"] if os.name == "nt" else []))
@pytest.mark.parametrize("empty", [False, True], ids=["missing", "empty"])
def test_cli_refuses_before_sender_when_required_environment_is_missing(make_kit, missing, empty):
    result = _draft_with_local_sender(make_kit, missing=missing, empty=empty)
    assert result.returncode == 2, result.stderr
    assert "the provider request failed" in result.stderr
    assert "sender-names=" not in result.stderr
    assert not result.stdout
