"""Run-command test bed: a kit folder built from ticket 03's synthetic minikit (synthetic rows only)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MINIKIT = ROOT / "tests" / "fixtures" / "minikit" / "health"
TEST_KEY = "run-test-only-master-key-not-a-secret-0000000000"  # published test constant
CREATED = "2026-11-07T00:00:00Z"
SCENARIOS = [
    {"id": "HEALTH-S1", "dataset": "health", "title": "synthetic", "utility_requirements": ["H-U2"]},
    {"id": "CS-S1", "dataset": "customer_service", "title": "synthetic", "utility_requirements": []},
]


def build_kit(root: Path, edit=None) -> Path:
    (root / "metadata").mkdir(parents=True)
    (root / "data" / "health").mkdir(parents=True)
    (root / "metadata" / "scenarios.json").write_text(json.dumps(SCENARIOS), encoding="utf-8")
    for p in sorted(MINIKIT.glob("*.csv")):
        shutil.copyfile(p, root / "data" / "health" / p.name)
    if edit:
        edit(root / "data" / "health")
    return root


def env(extra=None) -> dict:
    keep = ("PATH", "SYSTEMROOT", "PATHEXT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
            "HOMEDRIVE", "HOMEPATH", "COMSPEC", "VIRTUAL_ENV")
    e = {k: os.environ[k] for k in keep if k in os.environ}
    e.update({"PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1", "TZ": "UTC", "PYTHONIOENCODING": "utf-8",
              "PYTHONPATH": str(ROOT / "src"), "PETS_HMAC_KEY": TEST_KEY})
    e.update(extra or {})
    return e


def cli(*args, extra=None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "pets_release", *args], cwd=ROOT, env=env(extra),
                          capture_output=True, text=True, encoding="utf-8", check=False)


def run_args(kit: Path, out: Path) -> list[str]:
    return ["run", "--scenario", "HEALTH-S1", "--plan", "hand", "--kit", str(kit), "--out", str(out),
            "--created", CREATED]


@pytest.fixture(scope="session")
def released(tmp_path_factory):
    """One real-CLI fixture release shared by the read-only tests."""
    base = tmp_path_factory.mktemp("run")
    kit = build_kit(base / "kit")
    out = base / "out" / "rel"
    proc = cli(*run_args(kit, out))
    return kit, out, proc
