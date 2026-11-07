"""End-to-end determinism and offline tests through the real CLI (subprocess).

Tests marked xfail(strict=True) need ticket 21 (`pets-release run`). They are NOT passing evidence:
they count as "not run" until 21 lands and the marker is removed. strict=True makes the suite fail
the moment they start passing, so the marker cannot be forgotten.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from conftest import write_minikit
from e2e_harness import (
    CREATED,
    PYTHON,
    ROOT,
    SRC,
    diff_trees,
    pinned_env,
    run_cli,
    run_python,
    run_release,
    tree_digest,
)

needs_21 = pytest.mark.xfail(
    strict=True, raises=AssertionError, reason="needs ticket 21 (`pets-release run`); not run until it lands"
)


@pytest.fixture
def kit(tmp_path):
    return write_minikit(tmp_path / "kit")


# ---- determinism through a command that exists today ---------------------------------------------

def test_kit_info_is_byte_identical_across_runs_and_hash_seeds(kit):
    outs = []
    for seed in ("0", "1", "12345"):
        r = run_cli(["kit-info", "--dataset", "health", "--kit", str(kit)], hashseed=seed)
        assert r.returncode == 0, r.stderr
        outs.append(r.stdout)
    assert outs[0].strip() and len(set(outs)) == 1


def test_kit_info_independent_of_cwd(kit, tmp_path):
    other = tmp_path / "elsewhere"
    other.mkdir()
    a = run_cli(["kit-info", "--dataset", "health", "--kit", str(kit)])
    b = run_cli(["kit-info", "--dataset", "health", "--kit", str(kit)], cwd=other)
    assert a.returncode == b.returncode == 0 and a.stdout == b.stdout


# ---- offline guard: planted network calls must fail the run --------------------------------------

PLUG_DISPATCH = (
    "import sys\n"
    "from pets_release import cli\n"
    "cli.COMMAND_PACKAGES['verify'] = 'e2e_plug'\n"
    "raise SystemExit(cli.main(['verify']))\n"
)


def plant(tmp_path: Path, body: str) -> dict[str, str]:
    pkg = tmp_path / "plug" / "e2e_plug"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "cli.py").write_text(body)
    return {"PYTHONPATH": f"{SRC};{tmp_path / 'plug'}"}


def dispatch_plug(tmp_path, body):
    return run_python(PLUG_DISPATCH, env=plant(tmp_path, body))


def test_negative_control_plant_works_without_the_guard():
    r = run_python("import socket; socket.socket().close(); print('ok')")
    assert r.returncode == 0 and "ok" in r.stdout  # a socket can be created when no guard is installed


@pytest.mark.parametrize(
    "call",
    [
        "socket.socket()",
        "socket.create_connection(('127.0.0.1', 9), timeout=1)",
        "socket.getaddrinfo('example.invalid', 80)",
        "socket.gethostbyname('example.invalid')",
    ],
)
def test_planted_network_call_in_command_fails_the_run(tmp_path, call):
    body = f"import socket\ndef main(argv):\n    {call}\n    print('SURVIVED')\n    return 0\n"
    r = dispatch_plug(tmp_path, body)
    assert r.returncode != 0
    assert "SURVIVED" not in r.stdout
    assert "offline guard" in r.stderr


def test_planted_network_call_in_python_child_fails(tmp_path):
    """The block is inherited by plain `python` children (e.g. the scorecard subprocess)."""
    body = (
        "import subprocess, sys\n"
        "def main(argv):\n"
        "    r = subprocess.run([sys.executable, '-c', 'import socket; socket.socket()'])\n"
        "    return r.returncode\n"
    )
    r = dispatch_plug(tmp_path, body)
    assert r.returncode != 0
    assert "offline guard" in r.stderr


def test_planted_call_swallowed_by_handler_is_still_visible_to_the_test(tmp_path):
    """A handler that catches the OSError and returns 0 would hide the plant; the harness must see it."""
    body = (
        "import socket\n"
        "def main(argv):\n"
        "    try:\n"
        "        socket.socket()\n"
        "    except OSError as e:\n"
        "        print('CAUGHT', e)\n"
        "        return 0\n"
        "    return 0\n"
    )
    r = dispatch_plug(tmp_path, body)
    # exit 0 here is the handler's own choice; the guard message proves the plant was attempted and blocked
    assert "CAUGHT" in r.stdout and "offline guard" in r.stdout


# ---- the whole pipeline: needs ticket 21 ---------------------------------------------------------

@needs_21
def test_two_cli_runs_are_byte_identical(kit, tmp_path):
    a, b = tmp_path / "out_a", tmp_path / "out_b"
    ra = run_release(kit, a, hashseed="0")
    rb = run_release(kit, b, hashseed="777")
    assert ra.returncode == 0, ra.stderr
    assert rb.returncode == 0, rb.stderr
    assert (a / "privacy_manifest.json").is_file()
    assert len(tree_digest(a)) > 1
    assert diff_trees(a, b) == []


@needs_21
def test_run_is_independent_of_cwd_and_output_path(kit, tmp_path):
    a = tmp_path / "x" / "out"
    b = tmp_path / "a-much-longer" / "nested" / "name"
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    assert run_release(kit, a).returncode == 0
    assert run_release(kit, b, cwd=cwd).returncode == 0
    assert diff_trees(a, b) == []


@needs_21
def test_different_key_changes_the_release(kit, tmp_path):
    """Guards against a run that ignores the key (a determinism test that passes vacuously)."""
    a, b = tmp_path / "ka", tmp_path / "kb"
    assert run_release(kit, a).returncode == 0
    assert run_release(kit, b, key="other-" + "z" * 40).returncode == 0
    assert diff_trees(a, b) != []


@needs_21
def test_planted_network_call_inside_run_fails_the_run(kit, tmp_path):
    """Plant a socket call in the kit loader the real `run` uses; the run must fail, not swallow it."""
    marker = tmp_path / "planted.marker"
    wrapper = (
        "import sys\n"
        "from pathlib import Path\n"
        "from pets_release import cli, kit as kitmod\n"
        "orig = kitmod.Kit.load_dataset\n"
        "def planted(self, *a, **k):\n"
        "    Path(sys.argv[1]).write_text('reached')\n"
        "    import socket\n"
        "    socket.create_connection(('127.0.0.1', 9), timeout=1)\n"
        "    return orig(self, *a, **k)\n"
        "kitmod.Kit.load_dataset = planted\n"
        "raise SystemExit(cli.main(sys.argv[2:]))\n"
    )
    out = tmp_path / "planted_out"
    args = ["run", "--scenario", "HEALTH-S1", "--kit", str(kit), "--out", str(out), "--created", CREATED]
    r = run_python(wrapper, str(marker), *args)
    assert marker.is_file(), "the planted call was never reached by `run`"
    assert r.returncode != 0
    assert "offline guard" in r.stderr
    assert not (out / "privacy_manifest.json").exists()


@needs_21
def test_run_child_processes_inherit_the_block(kit, tmp_path):
    """A plain python child launched from inside the run path (as the scorecard is) cannot open a socket."""
    marker = tmp_path / "child.marker"
    wrapper = (
        "import subprocess, sys\n"
        "from pathlib import Path\n"
        "from pets_release import cli, kit as kitmod\n"
        "orig = kitmod.Kit.load_dataset\n"
        "def planted(self, *a, **k):\n"
        "    c = subprocess.run([sys.executable, '-c', 'import socket; socket.socket()'], capture_output=True, text=True)\n"
        "    Path(sys.argv[1]).write_text(str(c.returncode) + '|' + str('offline guard' in c.stderr))\n"
        "    return orig(self, *a, **k)\n"
        "kitmod.Kit.load_dataset = planted\n"
        "raise SystemExit(cli.main(sys.argv[2:]))\n"
    )
    out = tmp_path / "o"
    args = ["run", "--scenario", "HEALTH-S1", "--kit", str(kit), "--out", str(out), "--created", CREATED]
    r = run_python(wrapper, str(marker), *args)
    assert r.returncode == 0, r.stderr
    assert marker.is_file(), "the run never reached the planted child launch"
    rc, guard = marker.read_text().split("|")
    assert rc != "0" and guard == "True"
