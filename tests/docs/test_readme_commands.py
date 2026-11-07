"""Extract every command block from README.md and run the ones that can run today.

Each ```powershell block must be preceded by exactly one marker comment:
  <!-- docs-test: run -->                    run it (`pets-release ...`, venv-qualified CLI, or `$env:X = "v"`)
  <!-- docs-test: skip reason=<name> -->     not run; the reason is named and listed in the report
  <!-- docs-test: pending ticket=NN -->      subcommand not built yet ("available after ticket NN")
A block without a marker fails. A `pending` block whose subcommand now exists is reported
so it can be promoted to `run`; a `run` block whose subcommand is not built fails.
Set DOCS_TRANSCRIPT=<file> to write a transcript of the run.
Synthetic mini-kit only; no kit values.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shlex
import shutil
import subprocess
import sys
import venv
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
ALLOWED_SKIP_REASONS = (
    "environment-setup",
    "sets-secret-placeholder-only",
    "runs-the-whole-test-suite-recursively",
    # the CS-S1 release needs ticket 23 (turn_id check); guarded below
    "cs-s1-run-needs-ticket-23",
)
SUBCOMMANDS = ("run", "verify", "detect", "dashboard", "submission")
MARKER = re.compile(r"<!--\s*docs-test:\s*(run|skip|pending)\b([^>]*?)-->")
BLOCK = re.compile(r"(?:^(<!--.*?-->)[ \t]*\r?\n)?^```powershell[ \t]*\r?\n(.*?)^```", re.DOTALL | re.MULTILINE)


def _load_conftest():
    spec = importlib.util.spec_from_file_location("_tests_conftest", ROOT / "tests" / "conftest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_run_helpers():
    spec = importlib.util.spec_from_file_location("_run_helpers", ROOT / "tests" / "run" / "run_helpers.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def extract_blocks(text: str) -> list[dict]:
    blocks = []
    for n, m in enumerate(BLOCK.finditer(text), 1):
        marker = MARKER.search(m.group(1) or "")
        blocks.append(
            {
                "n": n,
                "line": text.count("\n", 0, m.start(2)),
                "kind": marker.group(1) if marker else None,
                "arg": marker.group(2).strip() if marker else "",
                "body": m.group(2),
            }
        )
    return blocks


BLOCKS = extract_blocks(README.read_text(encoding="utf-8"))


def _subcommand_exists(name: str) -> bool:
    try:
        return importlib.util.find_spec(f"pets_release.{name}.cli") is not None
    except ModuleNotFoundError:
        return False


def _statements(body: str) -> list[str]:
    out = []
    for raw in body.splitlines():
        for part in raw.split(";"):
            part = part.strip()
            if part:
                out.append(part)
    return out


def _expand(arg: str, env: dict) -> str:
    return re.sub(r"\$env:(\w+)", lambda m: env.get(m.group(1), ""), arg)


def _transcript(line: str) -> None:
    path = os.environ.get("DOCS_TRANSCRIPT")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def test_readme_has_command_blocks():
    assert BLOCKS, "README has no powershell blocks; the docs check would pass vacuously"


def _windows_quick_start() -> str:
    text = README.read_text(encoding="utf-8")
    return text.split("## Quick start (Windows, PowerShell)", 1)[1].split("\n## ", 1)[0]


def test_windows_quick_start_installs_without_activation():
    """README seam: Restricted-policy users must not fall back to system pip."""
    setup = extract_blocks(_windows_quick_start())[0]["body"]
    installs = [line for line in _statements(setup) if "-m pip install" in line]
    assert installs, "Quick start must include its environment-local installation commands"
    assert all(line.startswith(r".\.venv\Scripts\python.exe -m pip install ") for line in installs), (
        "Quick start must target the venv explicitly: Activate.ps1 is blocked by Restricted policy"
    )


def test_windows_quick_start_cli_without_activation():
    """README seam: the install checks also work without an activated PATH."""
    commands = [
        line.strip()
        for block in extract_blocks(_windows_quick_start())
        for line in block["body"].splitlines()
        if re.search(r"\bpets-release(?:\.exe)?\s", line)
    ]
    assert commands, "Quick start must check the installed CLI"
    assert all(line.startswith(r".\.venv\Scripts\pets-release.exe ") for line in commands), (
        "Quick start CLI commands must select the venv executable without activation"
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell execution-policy regression")
def test_windows_quick_start_interpreter_under_restricted_policy(tmp_path):
    """README + real PowerShell seam: the check prints this tree's interpreter."""
    checks = [
        line.strip()
        for block in extract_blocks(_windows_quick_start())
        for line in block["body"].splitlines()
        if "sys.executable" in line
    ]
    assert len(checks) == 1, "Quick start must show one executable interpreter-path check"

    # Minimal venv-like layout: no pip install or real venv creation in this fast test.
    env_root = tmp_path / ".venv"
    scripts = env_root / "Scripts"
    scripts.mkdir(parents=True)
    launchers = Path(venv.__file__).parent / "scripts" / "nt"
    launcher = next(p for p in (launchers / "venvlauncher.exe", launchers / "python.exe") if p.is_file())
    expected = scripts / "python.exe"
    shutil.copyfile(launcher, expected)
    (env_root / "pyvenv.cfg").write_text(
        f"home = {sys.base_prefix}\ninclude-system-site-packages = false\n", encoding="utf-8"
    )
    powershell = shutil.which("powershell")
    assert powershell, "Windows regression requires a real Windows PowerShell process"
    env = os.environ.copy()
    env["PATH"] = sys.base_prefix + os.pathsep + env.get("PATH", "")
    proc = subprocess.run(
        [powershell, "-NoProfile", "-ExecutionPolicy", "Restricted", "-Command",
         "$ErrorActionPreference = 'Stop'\n"
         "if ((Get-ExecutionPolicy) -ne 'Restricted') { throw 'Expected Restricted policy' }\n"
         + checks[0] + "\nexit $LASTEXITCODE"],
        cwd=tmp_path, env=env, capture_output=True, text=True, encoding="utf-8", timeout=30, check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert Path(proc.stdout.strip()).resolve() == expected.resolve(), (
        f"README check selected an interpreter outside the temporary environment: {proc.stdout!r}"
    )


def test_every_block_has_a_marker_with_named_reason():
    for b in BLOCKS:
        where = f"README block #{b['n']} (line {b['line']})"
        assert b["kind"], f"{where}: missing <!-- docs-test: ... --> marker"
        if b["kind"] == "skip":
            assert b["arg"].startswith("reason="), f"{where}: skip needs reason=<name>"
            assert b["arg"][7:] in ALLOWED_SKIP_REASONS, f"{where}: skip reason not in allowlist"
        if b["kind"] == "pending":
            assert re.fullmatch(r"ticket=\d+", b["arg"]), f"{where}: pending needs ticket=NN"


@pytest.mark.parametrize("block", BLOCKS, ids=lambda b: f"block{b['n']}-{b['kind']}")
def test_block(block, tmp_path):
    conf = _load_conftest()
    first = block["body"].strip().splitlines()[0]
    if block["kind"] == "skip":
        if block["arg"] == "reason=cs-s1-run-needs-ticket-23":
            assert not (ROOT / "src" / "pets_release" / "checks" / "turn_id").exists(), (
                "ticket 23 has landed (checks/turn_id): promote the CS-S1 run block to run"
            )
        _transcript(f"SKIP block {block['n']} ({block['arg']}): {first}")
        pytest.skip(f"named reason: {block['arg']}")
    if block["kind"] == "pending":
        sub = next((s for s in SUBCOMMANDS if re.search(rf"\bpets-release\s+{s}\b", block["body"])), None)
        assert sub, f"block {block['n']}: pending block names no known subcommand"
        assert not _subcommand_exists(sub), (
            f"README block #{block['n']}: pets-release {sub} is built; change its marker from pending to run"
        )
        note = ""
        _transcript(f"SKIP block {block['n']} (available after {block['arg']}, {sub}){note}: {first}")
        pytest.skip(f"not built yet: pets-release {sub} is available after {block['arg']}{note}")

    assert block["kind"] == "run", f"block {block['n']} has no marker"
    rh = _load_run_helpers()
    kit = rh.build_kit(tmp_path / "kit", rh.coarse_qis)  # synthetic minikit, QIs coarsened so the hand plan reaches k
    # synthetic stand-in for the unlabelled `unseen` export (one table), copied from the synthetic fixture
    (kit / "data" / "unseen").mkdir()
    shutil.copy(ROOT / "tests" / "fixtures" / "minikit" / "health" / "ed_visits.csv", kit / "data" / "unseen")
    # synthetic customer_service tables for the CS-S1 run block (ticket 23)
    shutil.copytree(ROOT / "tests" / "fixtures" / "minikit" / "customer_service", kit / "data" / "customer_service",
                    ignore=shutil.ignore_patterns(".*"))
    out_root = tmp_path / "out"
    env = rh.env({"PETS_KIT": str(kit)})  # PETS_HMAC_KEY is the published test-only constant
    run_cmd = next(s for b2 in BLOCKS if b2["kind"] == "run" for s in _statements(b2["body"])
                   if s.startswith("pets-release run --scenario HEALTH-S1"))

    def execute(stmt):
        stmt_x = _expand(stmt, env).replace("..\\sinceai-out\\", str(out_root) + os.sep)
        args = [a.strip('"') for a in shlex.split(stmt_x, posix=False)][1:]
        for s in SUBCOMMANDS:
            if args and args[0] == s:
                assert _subcommand_exists(s), f"run block uses unbuilt subcommand {s}"
        proc = subprocess.run([sys.executable, "-m", "pets_release", *args], cwd=ROOT, env=env,
                              capture_output=True, text=True, encoding="utf-8", check=False)
        return args, proc

    if "health-s1" in block["body"] and not block["body"].lstrip().startswith("pets-release run"):
        _, pre = execute(run_cmd)  # earlier README step: the release the later commands act on
        assert pre.returncode == 0, f"prerequisite run failed: {pre.stdout[-300:]}{pre.stderr[-300:]}"

    executed = 0
    for stmt in _statements(block["body"]):
        m = re.fullmatch(r'\$env:(\w+)\s*=\s*"(.*)"', stmt)
        if m:
            env[m.group(1)] = m.group(2)
            continue
        assert stmt.startswith(("pets-release ", r".\.venv\Scripts\pets-release.exe ")), (
            f"block {block['n']}: unrunnable statement {stmt!r}"
        )
        args, proc = execute(stmt)
        executed += 1
        _transcript(f"$ {stmt}\nexit={proc.returncode}\n{proc.stdout[:800]}{proc.stderr[:300]}")
        if args and args[0] == "verify" and "--full" in args:
            assert "VERIFIED (full)" in proc.stdout, f"{stmt!r}: no full-verification line"
        if args and args[0] == "verify" and "--full" not in args:
            assert "VERIFIED (limited)" in proc.stdout, f"{stmt!r}: no limited-verification line"
            assert "VERIFIED (full)" not in proc.stdout
        assert proc.returncode == 0, f"{stmt!r} exited {proc.returncode}: {proc.stdout[-300:]}{proc.stderr[:300]}"
    assert executed, f"block {block['n']} is marked run but executed no command"


@pytest.mark.parametrize(
    "path",
    ["pets_submission/rowmap_x.csv", "rowmap_ed_visits.csv", "a/truth/x.csv", "Briefs/x", ".env"],
)
def test_sensitive_paths_are_gitignored(path):
    r = subprocess.run(["git", "check-ignore", "-q", "--no-index", path], cwd=ROOT, check=False)
    assert r.returncode == 0, f"{path} is not ignored by .gitignore (exit {r.returncode})"
