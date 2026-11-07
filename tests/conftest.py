"""Shared fixtures for the scaffold ticket. Synthetic rows only."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
PYTHON = sys.executable

VISITS_CSV = "id,when,code\n00123,7.11.2026,010\n000,1.1.2024,00\n"
LABS_CSV = "lab_id\nL1\n"
VISITS_SHA256 = "2a83f33a95c1b48e2a33dcb78d7698d1cc4adbf43f8ca2426b5b49f129e66842"
LABS_SHA256 = "de4ded3552e7ee8fbe4b626adf1eceea23ae55c68bbd10276056f4b519219b88"

DICTIONARY = """# Data dictionary

## health

### health / ed_visits

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `id` | record_key | RECORD_ID |  | Visit identifier |
| `when` | quasi_identifier | DATE |  | Date of visit |
| `code` | technical_identifier | RECORD_ID |  | Code |

### health / lab_results

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `lab_id` | record_key | RECORD_ID | yes | Lab result identifier |
"""


def write_minikit(root: Path, scenarios=None, tables=None, dictionary: str | None = DICTIONARY) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "metadata").mkdir(exist_ok=True)
    (root / "data" / "health").mkdir(parents=True, exist_ok=True)
    (root / "docs").mkdir(exist_ok=True)
    if scenarios is None:
        scenarios = [
            {
                "id": "HEALTH-S1",
                "dataset": "health",
                "title": "synthetic",
                "utility_requirements": ["H-U2"],
            }
        ]
    (root / "metadata" / "scenarios.json").write_text(
        json.dumps(scenarios), encoding="utf-8"
    )
    if tables is None:
        tables = {"ed_visits": VISITS_CSV, "lab_results": LABS_CSV}
    for name, text in tables.items():
        (root / "data" / "health" / f"{name}.csv").write_bytes(text.encode("utf-8"))
    if dictionary is not None:
        (root / "docs" / "DATA_DICTIONARY.md").write_bytes(dictionary.encode("utf-8"))
    return root


def cli_env(extra: dict | None = None) -> dict[str, str]:
    """Minimal env. Does not inherit PETS_KIT, PETS_HMAC_KEY or SOURCE_DATE_EPOCH."""
    keep = (
        "PATH",
        "SYSTEMROOT",
        "PATHEXT",
        "WINDIR",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "HOMEDRIVE",
        "HOMEPATH",
        "COMSPEC",
        "VIRTUAL_ENV",
    )
    env = {key: os.environ[key] for key in keep if key in os.environ}
    env["PYTHONUTF8"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["TZ"] = "UTC"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = str(SRC)
    if extra:
        env.update(extra)
    return env


def run_cli(*args: str, env: dict | None = None, module: str = "pets_release") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [PYTHON, "-m", module, *args],
        cwd=ROOT,
        env=cli_env(env),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


PINNED_KIT = Path(r"C:\Users\kivas\AI\sinceai-hackaton\Briefs\TRUSTED_PETS_PROVING_GROUND_2026 (1)"
                  r"\TRUSTED_PETS_PROVING_GROUND_2026")


def find_kit() -> Path | None:
    """The kit root: PETS_KIT if set, else the pinned path. None when it is not a kit (no results/benchmark.json)."""
    kit = Path(os.environ.get("PETS_KIT") or PINNED_KIT)
    return kit if (kit / "results" / "benchmark.json").is_file() else None


@pytest.fixture
def kit_root(request) -> Path:
    """The kit root for tests marked ``kit``. A missing kit FAILS (never skips: skipped = not run = unknown = fail).
    Kit-less runs deselect them explicitly with ``-m "not kit"``."""
    kit = find_kit()
    if kit is None:
        pytest.fail("kit required but not found: set PETS_KIT or place the kit at the pinned path "
                    '(run with -m "not kit" to exclude kit tests explicitly)', pytrace=False)
    return kit


@pytest.fixture(autouse=True)
def _kit_marked_tests_need_the_kit(request):
    if request.node.get_closest_marker("kit") is not None:
        request.getfixturevalue("kit_root")


@pytest.fixture
def make_kit(tmp_path: Path):
    def _make(**kwargs) -> Path:
        return write_minikit(tmp_path / "kit", **kwargs)

    return _make


@pytest.fixture
def cli():
    return run_cli


# Test tiers: collection only, never skip or change the default full-suite run.
SLOW_TESTS_PATH = Path(__file__).resolve().with_name("slow_tests.txt")
FAST_CLI_SMOKE = frozenset({
    "tests/run/test_run.py::test_planted_card_number_refuses_via_cli",
    "tests/run/test_run.py::test_release_passes_gate_and_both_verify_tiers",
    "tests/run/test_run.py::test_two_runs_byte_identical",
})


def requires_real_kit(item) -> bool:
    """Fixture names include the transitive closure; synthetic `kit` is not real.

    `kit` is the repo's real-kit marker, including inherited module/class marks.
    New real-kit fixtures must depend on kit_root (or tests must carry that mark).
    """
    return item.get_closest_marker("kit") is not None or "kit_root" in item.fixturenames


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items):
    """Add marks before pytest's own -m deselection, using the canonical list."""
    try:
        measured = {
            line.strip() for line in SLOW_TESTS_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
    except OSError as exc:
        raise pytest.UsageError("cannot read canonical tests/slow_tests.txt") from exc
    for item in items:
        if requires_real_kit(item):
            item.add_marker(pytest.mark.slow(reason="real-kit"))
        elif item.nodeid in measured and item.nodeid not in FAST_CLI_SMOKE:
            item.add_marker(pytest.mark.slow(reason="profile"))
