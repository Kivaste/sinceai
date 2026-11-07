"""Extract every command block from README.md and run the ones that can run today.

Each ```powershell block must be preceded by exactly one marker comment:
  <!-- docs-test: run -->                    run it (lines: `pets-release ...` or `$env:X = "v"`)
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
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
SUBCOMMANDS = ("run", "verify", "detect", "dashboard", "submission")
MARKER = re.compile(r"<!--\s*docs-test:\s*(run|skip|pending)\b([^>]*?)-->")
BLOCK = re.compile(r"(?:^(<!--.*?-->)[ \t]*\r?\n)?^```powershell[ \t]*\r?\n(.*?)^```", re.S | re.M)


def _load_conftest():
    spec = importlib.util.spec_from_file_location("_tests_conftest", ROOT / "tests" / "conftest.py")
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


def test_every_block_has_a_marker_with_named_reason():
    for b in BLOCKS:
        where = f"README block #{b['n']} (line {b['line']})"
        assert b["kind"], f"{where}: missing <!-- docs-test: ... --> marker"
        if b["kind"] == "skip":
            assert re.fullmatch(r"reason=[a-z0-9-]+", b["arg"]), f"{where}: skip needs reason=<name>"
        if b["kind"] == "pending":
            assert re.fullmatch(r"ticket=\d+", b["arg"]), f"{where}: pending needs ticket=NN"


@pytest.mark.parametrize("block", BLOCKS, ids=lambda b: f"block{b['n']}-{b['kind']}")
def test_block(block, tmp_path):
    conf = _load_conftest()
    first = block["body"].strip().splitlines()[0]
    if block["kind"] == "skip":
        _transcript(f"SKIP block {block['n']} ({block['arg']}): {first}")
        pytest.skip(f"named reason: {block['arg']}")
    if block["kind"] == "pending":
        sub = next((s for s in SUBCOMMANDS if re.search(rf"\bpets-release\s+{s}\b", block["body"])), None)
        assert sub, f"block {block['n']}: pending block names no known subcommand"
        note = " (subcommand now exists: promote to run)" if _subcommand_exists(sub) else ""
        _transcript(f"SKIP block {block['n']} (available after {block['arg']}, {sub}){note}: {first}")
        pytest.skip(f"not built yet: pets-release {sub} is available after {block['arg']}{note}")

    assert block["kind"] == "run", f"block {block['n']} has no marker"
    kit = conf.write_minikit(tmp_path / "kit")
    env = conf.cli_env({"PETS_KIT": str(kit)})
    for stmt in _statements(block["body"]):
        m = re.fullmatch(r'\$env:(\w+)\s*=\s*"(.*)"', stmt)
        if m:
            env[m.group(1)] = m.group(2)
            continue
        assert stmt.startswith("pets-release"), f"block {block['n']}: unrunnable statement {stmt!r}"
        args = [a.strip('"') for a in shlex.split(_expand(stmt, env), posix=False)][1:]
        for s in SUBCOMMANDS:
            if args and args[0] == s:
                assert _subcommand_exists(s), f"run block uses unbuilt subcommand {s}"
        proc = conf.run_cli(*args, env=env)
        _transcript(f"$ {stmt}\nexit={proc.returncode}\n{proc.stdout[:600]}{proc.stderr[:300]}")
        assert proc.returncode == 0, f"{stmt!r} exited {proc.returncode}: {proc.stderr[:300]}"
