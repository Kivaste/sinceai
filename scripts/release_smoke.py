"""Opt-in release smoke (CLI execution scaffold)."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--kit", type=Path, required=True)
    parser.add_argument("--out-root", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sha = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    expectations = json.loads(subprocess.check_output(
        ["git", "-C", str(root), "show", f"{sha}:tests/smoke/expectations.json"], text=True))
    evidence = args.out_root / sha
    evidence.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix="attempt-", dir=evidence))
    env = dict(os.environ, PYTHONPATH=str(root / "src"), PETS_HMAC_KEY=secrets.token_hex(32))
    start = time.monotonic()
    proc = subprocess.run([sys.executable, "-m", "pets_release", "run", "--scenario", "HEALTH-S1",
                           "--kit", str(args.kit), "--out", str(folder / "HEALTH-S1"),
                           "--created", "2026-11-07T00:00:00Z"], cwd=root, env=env, capture_output=True)
    gate_path = folder / ("HEALTH-S1.scoring/gate_report.json" if proc.returncode == 0
                          else "HEALTH-S1.scoring/refusal_report.json")
    report = json.loads(gate_path.read_text(encoding="utf-8")) if gate_path.is_file() else {}
    gate = report.get("gate", report)
    failures = {r["check"]: r["hits"] for r in gate.get("records", [])
                if r["status"] not in ("pass", "not_applicable")}
    expected = expectations["HEALTH-S1"]
    passed = (proc.returncode == 0 if expected == "released" else
              proc.returncode == 1 and not (folder / "HEALTH-S1").exists() and bool(failures))
    health = {"steps": {"run": {"exitCode": proc.returncode,
              "elapsedSeconds": round(time.monotonic() - start, 3)}}, "failures": failures, "pass": passed}
    record = {"sha": sha, "pass": passed, "scenarios": {"HEALTH-S1": health}}
    (evidence / "smoke.json").write_text(json.dumps(record), encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
