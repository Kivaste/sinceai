"""Run-command test helpers: a kit folder built from ticket 03's synthetic minikit (synthetic rows only)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

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


QI_COLUMNS = ("date_of_birth", "municipality", "arrival_ts")
UNIQUE_TAIL = 4  # last visits keep their own QI values: below k, so local suppression has work to do


def coarse_qis(folder: Path) -> None:
    """Edit the synthetic copy: every visit but the last UNIQUE_TAIL copies row 0's QI cells (format-preserving),
    so the hand plan reaches k on the small minikit."""
    import pandas as pd

    p = folder / "ed_visits.csv"
    df = pd.read_csv(p, dtype=str, keep_default_na=False, na_filter=False)
    head = len(df) - UNIQUE_TAIL
    for c in QI_COLUMNS:
        df.loc[: head - 1, c] = df.at[0, c]
    df.to_csv(p, index=False, encoding="utf-8", lineterminator="\n")


def env(extra=None) -> dict:
    keep = ("PATH", "SYSTEMROOT", "PATHEXT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
            "HOMEDRIVE", "HOMEPATH", "COMSPEC", "VIRTUAL_ENV")
    e = {k: os.environ[k] for k in keep if k in os.environ}
    e.update({"PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1", "TZ": "UTC", "PYTHONIOENCODING": "utf-8",
              "PYTHONPATH": str(ROOT / "src"), "PETS_HMAC_KEY": TEST_KEY})
    e.update(extra or {})
    from pets_release.offline import child_env

    return child_env(e)


def cli(*args, extra=None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "pets_release", *args], cwd=ROOT, env=env(extra),
                          capture_output=True, text=True, encoding="utf-8", check=False)


def run_args(kit: Path, out: Path) -> list[str]:
    return ["run", "--scenario", "HEALTH-S1", "--plan", "hand", "--kit", str(kit), "--out", str(out),
            "--created", CREATED]
