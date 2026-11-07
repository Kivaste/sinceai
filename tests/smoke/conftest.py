"""Isolated Git identities and synthetic kits for the smoke's real CLI seam."""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("smoke_run_helpers", ROOT / "tests/run/run_helpers.py")
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)


@pytest.fixture
def smoke_checkout(tmp_path):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    shutil.copytree(ROOT / "src", checkout / "src")
    (checkout / "scripts").mkdir()
    for path in (ROOT / "scripts").glob("release_smoke*"):
        shutil.copyfile(path, checkout / "scripts" / path.name)
    expectations = checkout / "tests/smoke/expectations.json"
    expectations.parent.mkdir(parents=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(PYTHONUTF8="1", TZ="UTC", PYTHONPATH=str(checkout / "src"))

    class Checkout:
        def git(self, *args):
            return subprocess.check_output(["git", "-C", str(checkout), *args], env=env,
                                           text=True, encoding="utf-8", stderr=subprocess.PIPE).strip()

        def commit(self, health="released", cs="refused"):
            expectations.write_text(json.dumps({"HEALTH-S1": health, "CS-S1": cs}), encoding="utf-8")
            self.git("add", ".")
            self.git("-c", "user.name=Smoke Test", "-c", "user.email=smoke@example.invalid",
                     "commit", "--allow-empty", "-m", "synthetic smoke revision")
            return self.git("rev-parse", "HEAD")

        def kit(self, *, card=False):
            def edit(folder):
                helpers.coarse_qis(folder)
                if card:
                    self.plant_card_in(folder / "ed_visits.csv")
            kit = helpers.build_kit(tmp_path / "kit", edit)
            shutil.copytree(ROOT / "tests/fixtures/minikit/customer_service", kit / "data/customer_service")
            (kit / "results").mkdir()
            (kit / "results/benchmark.json").write_text("{}", encoding="utf-8")
            return kit

        def plant_card(self, kit):
            self.plant_card_in(kit / "data/health/ed_visits.csv")

        def plant_card_in(self, path):
            import pandas as pd
            frame = pd.read_csv(path, dtype=str, keep_default_na=False, na_filter=False)
            # H-U4 requires municipality; search may withhold an unused disposition.
            # A shared synthetic category also survives per-person k suppression.
            frame.loc[:, "municipality"] = "4111 1111 1111 1111"
            frame.to_csv(path, index=False, lineterminator="\n")

        def run(self, kit, *extra, fault=None):
            launcher = [sys.executable]
            if fault:
                launcher.extend([str(ROOT / "tests/smoke/fault_cli.py"), fault])
            return subprocess.run([*launcher, str(checkout / "scripts/release_smoke.py"),
                                   "--kit", str(kit), "--out-root", str(tmp_path / "evidence"), *extra],
                                  cwd=checkout, env=env, capture_output=True, text=True, encoding="utf-8",
                                   timeout=180, check=False)

        def cs_cli(self, kit):
            return subprocess.run([sys.executable, "-m", "pets_release", "run", "--scenario", "CS-S1",
                                   "--kit", str(kit), "--out", str(tmp_path / "cs-cli-probe"),
                                   "--created", "2026-11-07T00:00:00Z"], cwd=checkout,
                                  env=dict(env, PETS_HMAC_KEY=helpers.TEST_KEY), capture_output=True,
                                  text=True, encoding="utf-8", timeout=30, check=False)

        def record(self, sha):
            return json.loads((tmp_path / "evidence" / sha / "smoke.json").read_text(encoding="utf-8"))

        def observation(self):
            path = tmp_path / "fault-observation.json"
            return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

        def validate(self, record):
            path = tmp_path / "record.json"
            path.write_text(json.dumps(record, sort_keys=True, separators=(",", ":")), encoding="utf-8")
            return subprocess.run([sys.executable, str(checkout / "scripts/release_smoke.py"),
                                   "--validate-record", str(path)], cwd=checkout, env=env,
                                  capture_output=True, check=False).returncode

        path = checkout
        output = tmp_path / "evidence"

    result = Checkout()
    result.git("init")
    return result
