"""Scaffold: CLI dispatcher, kit access, offline guard. Synthetic rows only."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from conftest import (
    LABS_CSV,
    LABS_SHA256,
    PYTHON,
    ROOT,
    VISITS_CSV,
    VISITS_SHA256,
    cli_env,
    write_minikit,
)

KEY = "k" * 32
CREATED = "2026-11-07T00:00:00Z"


def run_args(kit, **over):
    a = {"--scenario": "HEALTH-S1", "--out": "out", "--created": CREATED, "--kit": str(kit)}
    a.update(over)
    return ["run"] + [x for kv in a.items() for x in kv if x is not None]


DISPATCH = (
    "import sys, json\n"
    "from pets_release import cli\n"
    "cli.COMMAND_PACKAGES.update(json.loads(sys.argv[1]))\n"
    "raise SystemExit(cli.main(json.loads(sys.argv[2])))\n"
)


def dispatch(argv, overrides, env=None, extra_path=None):
    """Run cli.main in a child with the dispatch table overridden (never relies on real subcommands)."""
    import json

    e = dict(env or {})
    if extra_path:
        e["PYTHONPATH"] = f"{ROOT / 'src'};{extra_path}"
    return subprocess.run(
        [PYTHON, "-c", DISPATCH, json.dumps(overrides), json.dumps(argv)],
        cwd=ROOT, env=cli_env(e), capture_output=True, text=True, check=False,
    )


def make_plug(tmp_path, body="def main(argv):\n    print('PLUGGED')\n    return 0\n", name="pets_release_plug"):
    pkg = tmp_path / "plug" / name
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "cli.py").write_text(body)
    return name, str(tmp_path / "plug")


MISSING = {c: "pets_release_nonexistent_pkg" for c in ("run", "verify", "detect", "dashboard", "submission")}

def test_help_lists_commands(cli):
    r = cli("--help")
    assert r.returncode == 0
    for name in ("run", "verify", "detect", "dashboard", "submission"):
        assert name in r.stdout


@pytest.mark.parametrize("name", ["run", "verify", "detect", "dashboard", "submission"])
def test_unimplemented_exits_2(make_kit, name):
    argv = run_args(make_kit()) if name == "run" else [name]
    r = dispatch(argv, MISSING, {"PETS_HMAC_KEY": KEY})
    assert r.returncode == 2 and "not implemented" in r.stderr.lower()


@pytest.mark.parametrize("ret", ["None", "'0'", "True", "1.0"])
def test_non_int_return_fails_closed(tmp_path, ret):
    name, path = make_plug(tmp_path, f"def main(argv):\n    return {ret}\n")
    r = dispatch(["verify"], {"verify": name}, extra_path=path)
    assert r.returncode == 2


def test_int_return_passes_through(tmp_path):
    name, path = make_plug(tmp_path, "def main(argv):\n    return 7\n")
    assert dispatch(["verify"], {"verify": name}, extra_path=path).returncode == 7


def test_import_error_inside_plugin_is_not_swallowed(tmp_path):
    name, path = make_plug(tmp_path, "import not_a_real_dependency_xyz\ndef main(argv):\n    return 0\n")
    r = dispatch(["verify"], {"verify": name}, extra_path=path)
    assert r.returncode != 0 and "not implemented" not in r.stderr.lower()

def test_no_command_exits_2(cli):
    assert cli().returncode == 2


def test_run_without_created_exits_2(cli, make_kit):
    kit = make_kit()
    args = run_args(kit)
    i = args.index("--created")
    del args[i : i + 2]
    r = cli(*args, env={"PETS_HMAC_KEY": KEY})
    assert r.returncode == 2
    assert "created" in r.stderr.lower()


def test_run_source_date_epoch_accepted_past_preflight(tmp_path, make_kit):
    name, path = make_plug(tmp_path)
    args = run_args(make_kit())
    i = args.index("--created")
    del args[i : i + 2]
    r = dispatch(args, {"run": name}, {"PETS_HMAC_KEY": KEY, "SOURCE_DATE_EPOCH": "0"}, path)
    assert r.returncode == 0 and "PLUGGED" in r.stdout

def test_short_key_exits_2(cli, make_kit):
    r = cli(*run_args(make_kit()), env={"PETS_HMAC_KEY": "k" * 31})
    assert r.returncode == 2 and "PETS_HMAC_KEY" in r.stderr


def test_missing_key_exits_2(cli, make_kit):
    assert cli(*run_args(make_kit())).returncode == 2


def test_unknown_scenario_exits_2(cli, make_kit):
    r = cli(*run_args(make_kit(), **{"--scenario": "health-s1"}), env={"PETS_HMAC_KEY": KEY})
    assert r.returncode == 2 and "scenario" in r.stderr.lower()


def test_missing_kit_exits_2(cli, tmp_path):
    r = cli(*run_args(tmp_path / "nope"), env={"PETS_HMAC_KEY": KEY})
    assert r.returncode == 2


def test_kit_from_env(tmp_path, make_kit):
    name, path = make_plug(tmp_path)
    kit = make_kit()
    args = run_args(kit)
    i = args.index("--kit")
    del args[i : i + 2]
    r = dispatch(args, {"run": name}, {"PETS_HMAC_KEY": KEY, "PETS_KIT": str(kit)}, path)
    assert r.returncode == 0 and "PLUGGED" in r.stdout


def test_valid_run_reaches_plugin(tmp_path, make_kit):
    name, path = make_plug(tmp_path)
    r = dispatch(run_args(make_kit()), {"run": name}, {"PETS_HMAC_KEY": KEY}, path)
    assert r.returncode == 0 and "PLUGGED" in r.stdout

def test_python_dash_m_and_entry(cli):
    assert cli("--help", module="pets_release").returncode == 0


# ---- kit access ----


def test_tables_all_strings_nothing_coerced(make_kit):
    from pets_release.kit import Kit

    kit = Kit(make_kit())
    df = kit.load_table("health", "ed_visits")
    assert list(df.columns) == ["id", "when", "code"]
    assert all(isinstance(v, str) for c in df.columns for v in df[c])
    assert df["id"].tolist() == ["00123", "000"]
    assert df["when"].tolist() == ["7.11.2026", "1.1.2024"]
    assert df["code"].tolist() == ["010", "00"]


def test_empty_cells_stay_empty_strings_not_nan(make_kit):
    from pets_release.kit import Kit

    kit = Kit(make_kit(tables={"t": "a,b\n1,\n,2\n"}))
    df = kit.load_table("health", "t")
    assert df["b"].tolist() == ["", "2"] and df["a"].tolist() == ["1", ""]


def test_digests_are_file_sha256(make_kit):
    from pets_release.kit import Kit

    kit = Kit(make_kit())
    assert VISITS_SHA256 == hashlib.sha256(VISITS_CSV.encode()).hexdigest()
    assert LABS_SHA256 == hashlib.sha256(LABS_CSV.encode()).hexdigest()
    assert kit.input_digests("health") == {"ed_visits": VISITS_SHA256, "lab_results": LABS_SHA256}


def test_scenarios_strict(make_kit):
    from pets_release.kit import Kit, KitError

    kit = Kit(make_kit())
    assert kit.scenario("HEALTH-S1")["dataset"] == "health"
    for bad in ("health-s1", "HEALTH-S1 ", "HEALTH", ""):
        with pytest.raises(KitError):
            kit.scenario(bad)


def test_dataset_and_table_names_cannot_escape(make_kit):
    from pets_release.kit import Kit, KitError

    kit = Kit(make_kit())
    for ds, t in (("..", "x"), ("health", "../x"), ("health", "a/b"), ("truth", "x")):
        with pytest.raises(KitError):
            kit.load_table(ds, t)


def test_dictionary_loaded(make_kit):
    from pets_release.kit import Kit

    assert "ed_visits" in Kit(make_kit()).data_dictionary()


def test_never_opens_truth_or_field_catalog(tmp_path, monkeypatch):
    """Planted files: any open of truth/ or field_catalog.csv fails the test."""
    import builtins
    import io
    import pathlib

    from pets_release.kit import Kit, KitError

    root = write_minikit(tmp_path / "kit")
    (root / "truth").mkdir()
    (root / "truth" / "health.csv").write_text("x\n1\n")
    (root / "metadata" / "field_catalog.csv").write_text("x\n1\n")
    (root / "data" / "health" / "field_catalog.csv").write_text("x\n1\n")
    (root / "data" / "truth").mkdir()
    (root / "data" / "truth" / "t.csv").write_text("x\n1\n")
    opened = []
    real_open, real_io, real_p = builtins.open, io.open, pathlib.Path.open

    def spy(f, *a, **k):
        opened.append(str(f))
        return real_open(f, *a, **k)

    monkeypatch.setattr(builtins, "open", spy)
    monkeypatch.setattr(io, "open", lambda f, *a, **k: (opened.append(str(f)), real_io(f, *a, **k))[1])
    monkeypatch.setattr(pathlib.Path, "open", lambda self, *a, **k: (opened.append(str(self)), real_p(self, *a, **k))[1])
    kit = Kit(root)
    kit.scenarios()
    kit.load_dataset("health")
    kit.input_digests("health")
    kit.data_dictionary()
    for bad in (("truth", "health"), ("health", "field_catalog")):
        with pytest.raises(KitError):
            kit.load_table(*bad)
    with pytest.raises(KitError):
        kit.load_table("truth", "t")
    assert opened, "open spy recorded nothing: the test would pass vacuously"
    assert any(p.endswith(".csv") and "health" in p for p in opened), "legitimate dataset read not recorded"
    assert not [p for p in opened if "truth" in p.replace("\\", "/").split("/") or "field_catalog" in p]


def test_load_dataset_ignores_non_csv_and_lists_sorted(make_kit):
    from pets_release.kit import Kit

    kit = Kit(make_kit())
    assert list(kit.load_dataset("health")) == ["ed_visits", "lab_results"]


# ---- offline guard ----

PROBE = (
    "import socket,sys\n"
    "try:\n"
    "    socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
    "except Exception:\n"
    "    print('BLOCKED'); sys.exit(0)\n"
    "print('OPEN'); sys.exit(1)\n"
)


def _run(code, env=None):
    return subprocess.run(
        [PYTHON, "-c", code], cwd=ROOT, env=cli_env(env), capture_output=True, text=True, check=False
    )


def test_guard_blocks_in_process_and_subprocess():
    code = (
        "from pets_release.offline import install\n"
        "install()\n"
        "import subprocess,sys\n"
        f"p=subprocess.run([sys.executable,'-c',{PROBE!r}],capture_output=True,text=True)\n"
        "print(p.stdout.strip())\n"
        f"exec({PROBE!r})\n"
    )
    r = _run(code)
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == ["BLOCKED", "BLOCKED"]


def test_probe_opens_socket_without_guard():
    # planted-file control: the probe really is able to open a socket.
    assert _run(PROBE).stdout.strip() == "OPEN"


def test_guard_blocks_create_connection_and_dns():
    code = (
        "from pets_release.offline import install\n"
        "install()\n"
        "import socket\n"
        "for f in (lambda: socket.create_connection(('127.0.0.1',9)), lambda: socket.getaddrinfo('localhost',80)):\n"
        "    try: f()\n"
        "    except Exception: continue\n"
        "    raise SystemExit(1)\n"
    )
    assert _run(code).returncode == 0


def test_cli_main_is_offline_and_subprocess_inherits(tmp_path):
    code = (
        "import sys, subprocess\n"
        "from pets_release import cli\n"
        "cli._install_guard()\n"
        f"p=subprocess.run([sys.executable,'-c',{PROBE!r}],capture_output=True,text=True)\n"
        "sys.exit(0 if p.stdout.strip()=='BLOCKED' else 1)\n"
    )
    assert _run(code).returncode == 0


def test_cli_main_guards_plugged_module(tmp_path):
    """Real cli.main() dispatching to a plugged module: it cannot open a socket, nor can its subprocess."""
    plug = tmp_path / "plug" / "pets_release_plug"
    plug.mkdir(parents=True)
    (plug / "__init__.py").write_text("")
    (plug / "cli.py").write_text(
        "import subprocess, sys\n"
        f"PROBE={PROBE!r}\n"
        "def main(argv):\n"
        "    p = subprocess.run([sys.executable, '-c', PROBE], capture_output=True, text=True)\n"
        "    print(p.stdout.strip())\n"
        "    try:\n"
        "        exec(PROBE)\n"
        "    except SystemExit as e:\n"
        "        return e.code\n"
    )
    code = (
        "from pets_release import cli\n"
        "cli.COMMAND_PACKAGES['verify'] = 'pets_release_plug'\n"
        "raise SystemExit(cli.main(['verify']))\n"
    )
    r = _run(code, {"PYTHONPATH": f"{ROOT / 'src'};{plug.parent}"})
    assert r.stdout.split() == ["BLOCKED", "BLOCKED"], r.stderr
    assert r.returncode == 0


def test_guard_blocks_sockettype_and_helpers():
    code = (
        "from pets_release.offline import install\n"
        "install()\n"
        "import socket, _socket\n"
        "fs = [lambda: socket.SocketType(), lambda: _socket.SocketType(), lambda: socket.socketpair(),\n"
        "      lambda: socket.fromfd(0, 2, 1), lambda: _socket.socket(), lambda: socket.create_server(('127.0.0.1', 0))]\n"
        "for f in fs:\n"
        "    try: f()\n"
        "    except Exception: continue\n"
        "    raise SystemExit(1)\n"
    )
    assert _run(code).returncode == 0


def test_plain_python_child_blocked_documented_guarantee():
    """Documented guarantee: plain `python` children are blocked; `python -I` is a documented residual."""
    from pets_release import offline

    assert "-I" in offline.__doc__
    code = (
        "from pets_release.offline import install\ninstall()\n"
        "import subprocess, sys\n"
        f"p = subprocess.run([sys.executable, '-c', {PROBE!r}], capture_output=True, text=True)\n"
        "sys.exit(0 if p.stdout.strip() == 'BLOCKED' else 1)\n"
    )
    assert _run(code).returncode == 0


def _link(link: Path, target: Path) -> None:
    import os

    try:
        os.symlink(target, link, target_is_directory=True)
        return
    except (OSError, NotImplementedError):
        pass
    if sys.platform == "win32":
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, check=False)
        if r.returncode == 0:
            return
    pytest.skip("cannot create symlink or junction here")


def test_junction_into_truth_is_refused(tmp_path):
    import shutil

    from pets_release.kit import Kit, KitError

    root = write_minikit(tmp_path / "kit")
    (root / "truth" / "health").mkdir(parents=True)
    (root / "truth" / "health" / "secret.csv").write_text("x\n1\n")
    shutil.rmtree(root / "data" / "health")
    _link(root / "data" / "health", root / "truth" / "health")
    kit = Kit(root)
    for f in (lambda: kit.load_table("health", "secret"), lambda: kit.load_dataset("health"),
              lambda: kit.input_digests("health"), lambda: kit.table_names("health")):
        with pytest.raises(KitError):
            f()


def test_junction_outside_data_tree_is_refused(tmp_path):
    import shutil

    from pets_release.kit import Kit, KitError

    root = write_minikit(tmp_path / "kit")
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "t.csv").write_text("x\n1\n")
    shutil.rmtree(root / "data" / "health")
    _link(root / "data" / "health", outside)
    with pytest.raises(KitError):
        Kit(root).load_table("health", "t")


def test_data_dir_junction_to_truth_is_refused(tmp_path):
    import shutil

    from pets_release.kit import Kit, KitError

    root = write_minikit(tmp_path / "kit")
    (root / "truth").mkdir()
    shutil.copytree(root / "data" / "health", root / "truth" / "health")
    shutil.rmtree(root / "data")
    _link(root / "data", root / "truth")
    with pytest.raises(KitError):
        Kit(root).load_table("health", "ed_visits")


def test_child_env_keeps_block_with_curated_env():
    """A curated env= built via offline.child_env() keeps the guard."""
    code = (
        "from pets_release.offline import install, child_env\ninstall()\n"
        "import os, subprocess, sys\n"
        "env = child_env({'PATH': os.environ.get('PATH', ''), 'SystemRoot': os.environ.get('SystemRoot', '')})\n"
        "assert env['PETS_OFFLINE'] == '1'\n"
        f"p = subprocess.run([sys.executable, '-c', {PROBE!r}], capture_output=True, text=True, env=env)\n"
        "sys.exit(0 if p.stdout.strip() == 'BLOCKED' else 1)\n"
    )
    assert _run(code).returncode == 0


def test_child_env_pure_idempotent_and_documented():
    import os

    from pets_release import offline

    base = {"PYTHONPATH": "x"}
    env = offline.child_env(base)
    assert base == {"PYTHONPATH": "x"}
    assert env["PYTHONPATH"].split(os.pathsep) == [str(offline.HOOK_DIR), "x"]
    assert env["PETS_OFFLINE"] == "1"
    assert offline.child_env(env) == env
    assert "child_env" in offline.__doc__


def test_package_data_globs_are_recursive_and_cover_nested_data():
    import tomllib

    root = Path(__file__).resolve().parents[2]
    cfg = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    globs = cfg["tool"]["setuptools"]["package-data"]["*"]
    assert "**/*.csv" in globs
    assert "**/*.py" in globs


def test_built_wheel_ships_hook_and_nested_data(tmp_path):
    pytest.importorskip("setuptools")
    pytest.importorskip("wheel")
    import zipfile

    root = Path(__file__).resolve().parents[2]
    cmd = [sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation", "-w", str(tmp_path), str(root)]
    r = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stderr[-500:]
    names = zipfile.ZipFile(next(tmp_path.glob("*.whl"))).namelist()
    assert "pets_release/_offline_hook/sitecustomize.py" in names
    for d in ("checks/text/data", "redactor/lexicon/data"):
        src = root / "src" / "pets_release" / d
        for f in src.glob("*.csv") if src.is_dir() else []:
            assert f"pets_release/{d}/{f.name}" in names