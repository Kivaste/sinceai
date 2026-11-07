"""Opt-in, content-free product smoke. Never reuses a release or an earlier verdict."""
from __future__ import annotations

import argparse
import hashlib
import math
import os
import re
import secrets
import stat
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pets_release.kit import Kit
from pets_release.manifest import canonical_bytes, loads_strict
from pets_release.policy import get_policy

SCENARIOS = ("HEALTH-S1", "CS-S1")
PINNED_KIT = Path(r"C:\Users\kivas\AI\sinceai-hackaton\Briefs\TRUSTED_PETS_PROVING_GROUND_2026 (1)"
                  r"\TRUSTED_PETS_PROVING_GROUND_2026")
DEFAULT_OUTPUT = Path(r"C:\Users\kivas\AI\sinceai-out\smoke")


def exact(record, keys):
    if not isinstance(record, dict) or set(record) != set(keys.split()):
        raise ValueError("closed record keys differ")


def number(value, *, integer=False):
    if type(value) not in ((int,) if integer else (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError("invalid aggregate")


def validate_record(record):
    """Closed record validation, including dynamic maps of schema/check names (no value-bearing text)."""
    exact(record, "sha toolRevision metadataDigest inputs scenarios delivery pass")
    if not re.fullmatch(r"[0-9a-f]{40}", record["sha"]) or record["toolRevision"] != record["sha"]:
        raise ValueError("invalid revision")
    if record["metadataDigest"] is not None and not re.fullmatch(r"[0-9a-f]{64}", record["metadataDigest"]):
        raise ValueError("invalid metadata digest")
    exact(record["inputs"], "HEALTH-S1 CS-S1")
    exact(record["scenarios"], "HEALTH-S1 CS-S1")
    exact(record["delivery"], "HEALTH-S1")
    for inputs in record["inputs"].values():
        for name, digest in inputs.items():
            if not re.fullmatch(r"[a-z][a-z0-9_]*", name) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError("invalid input digest")
    results = [*record["scenarios"].values(), *record["delivery"].values()]
    for scenario in results:
        exact(scenario, "expected steps gate failures personK purpose dashboardWritten pass error")
        if scenario["expected"] not in (None, "released", "refused"):
            raise ValueError("invalid expectation")
        if scenario["error"] not in (None, "run-unknown", "unexpected-refusal", "missing-or-invalid-step",
                                     "not-run", "dirty-checkout", "kit-unavailable", "revision-mismatch",
                                     "configuration-invalid", "identity-changed"):
            raise ValueError("invalid error code")
        if type(scenario["pass"]) is not bool or type(scenario["dashboardWritten"]) is not bool:
            raise ValueError("invalid verdict")
        for name, step in scenario["steps"].items():
            if name not in ("run", "verify-limited", "verify-full", "dashboard"):
                raise ValueError("unknown step")
            exact(step, "exitCode elapsedSeconds status")
            if step["status"] not in ("completed", "timeout", "error", "not-run"):
                raise ValueError("invalid step status")
            if ((step["status"] == "completed" and type(step["exitCode"]) is not int)
                    or (step["status"] != "completed" and step["exitCode"] is not None)):
                raise ValueError("invalid exit code")
            number(step["elapsedSeconds"])
        if scenario["gate"] is not None:
            exact(scenario["gate"], "passed failed notApplicable unknown")
            for count in scenario["gate"].values():
                number(count, integer=True)
        if scenario["personK"] is not None:
            exact(scenario["personK"], "requiredK minK persons belowK")
            for count in scenario["personK"].values():
                number(count, integer=True)
        for name, count in scenario["failures"].items():
            if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", name):
                raise ValueError("invalid check name")
            number(count, integer=True)
        for name, task in scenario["purpose"].items():
            if not re.fullmatch(r"(?:H|CS)-U[0-9]+", name):
                raise ValueError("invalid task name")
            exact(task, "score threshold pass")
            if task["score"] is not None:
                number(task["score"])
            number(task["threshold"])
            if type(task["pass"]) is not bool:
                raise ValueError("invalid task verdict")
    if type(record["pass"]) is not bool or record["pass"] != all(s["pass"] for s in results):
        raise ValueError("invalid overall verdict")


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True, encoding="utf-8",
                                   stderr=subprocess.PIPE, timeout=30,
                                   env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")}).strip()


def read_json(path):
    return loads_strict(path.read_bytes())


def cli(args, env, deadline, *, module="pets_release"):
    start = time.monotonic()
    step = {"exitCode": None, "elapsedSeconds": 0, "status": "timeout"}
    if start >= deadline:
        return step, ""
    try:
        flags = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {
            "start_new_session": True}
        proc = subprocess.Popen([sys.executable, "-m", module, *args], cwd=ROOT, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                encoding="utf-8", errors="replace", **flags)
        try:
            stdout, _ = proc.communicate(timeout=max(0.001, deadline - time.monotonic()))
            step.update(exitCode=proc.returncode, status="completed")
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True,
                               timeout=10, check=False)
            else:
                import signal
                os.killpg(proc.pid, signal.SIGKILL)
            proc.kill()
            proc.communicate(timeout=10)
            stdout = ""
    except Exception:  # noqa: BLE001 - process errors are unknown; exception text may contain values.
        step["status"] = "error"
        stdout = ""
    step["elapsedSeconds"] = round(time.monotonic() - start, 3)
    return step, stdout


def gate_aggregates(gate):
    records = gate["records"]
    if not records or len({r["check"] for r in records}) != len(records):
        raise ValueError("gate records missing or duplicated")
    counts = {"passed": 0, "failed": 0, "notApplicable": 0, "unknown": 0}
    failures = {}
    for r in records:
        status = r["status"]
        key = {"pass": "passed", "fail": "failed", "not_applicable": "notApplicable"}.get(status, "unknown")
        counts[key] += 1
        if status not in ("pass", "not_applicable"):
            failures[r["check"]] = r["hits"]
    return counts, failures


def new_result(expected):
    names = ("run", "verify-limited", "verify-full", "dashboard") if expected == "released" else ("run",)
    return {"expected": expected,
            "steps": {name: {"exitCode": None, "elapsedSeconds": 0, "status": "not-run"} for name in names},
            "gate": None, "failures": {}, "personK": None, "purpose": {},
            "dashboardWritten": False, "pass": False, "error": "not-run"}


def scenario_smoke(scenario, expected, kit, folder, sha, inputs, env, deadline, *, measured=False):
    out = folder / scenario
    scoring = folder / f"{scenario}.scoring"
    result = new_result(expected)
    result["error"] = None
    try:
        args = ["--scenario", scenario, "--kit", str(kit.root), "--out", str(out),
                "--created", "2026-11-07T00:00:00Z"]
        step, _ = cli(args if measured else ["run", *args], env, deadline,
                      module="pets_release.measure.wire" if measured else "pets_release")
        result["steps"]["run"] = step
        code = step["exitCode"]
        if code not in (0, 1):
            result["error"] = "run-unknown"
            return result
        report = read_json(scoring / ("gate_report.json" if code == 0 else "refusal_report.json"))
        gate = report if code == 0 else report["gate"]
        result["gate"], result["failures"] = gate_aggregates(gate)
        if expected == "refused":
            result["pass"] = (code == 1 and not out.exists() and report["status"] == "refused"
                              and gate["refused"] is True and result["gate"]["unknown"] == 0
                              and bool(result["failures"]) and all(n > 0 for n in result["failures"].values()))
            return result
        if code != 0:
            result["error"] = "unexpected-refusal"
            return result
        manifest = read_json(out / "privacy_manifest.json")
        if (manifest["bindings"]["toolRevision"] != sha or manifest["bindings"]["inputs"] != inputs
                or manifest["release"]["scenario"] != scenario):
            raise ValueError("release identity mismatch")
        policy = get_policy(scenario)
        targets = [t["k"] for t in policy.privacy_targets if t["kind"] == "k_anonymity"]
        k_ok = True
        if targets:
            k = read_json(scoring / "person_k_report.json")
            result["personK"] = {"requiredK": max(targets), "minK": k["minK"],
                                 "persons": k["persons"], "belowK": k["belowK"]}
            k_ok = k["persons"] > 0 and k["minK"] >= max(targets) and k["belowK"] == 0
        utility = manifest["measured"]["utility"]
        floors = {s["check"]: s["floor_score"] for s in policy.sacrifices}
        for task in utility["tasks"]:
            threshold = floors.get(task["task"], 0.9)
            score = task["after"]
            passed = task["status"] == "ok" and type(score) in (int, float) and score >= threshold
            result["purpose"][task["task"]] = {"score": score, "threshold": threshold, "pass": passed}
        required = set(policy.purpose_checks) | set(kit.scenario(scenario)["utility_requirements"])
        utility_ok = (utility["status"] == "measured" and required <= set(result["purpose"])
                      and bool(result["purpose"]) and all(t["pass"] for t in result["purpose"].values()))
        limited, text = cli(["verify", str(out)], env, deadline)
        result["steps"]["verify-limited"] = limited
        limited_ok = limited["exitCode"] == 0 and text.startswith("VERIFIED (limited):")
        full, text = cli(["verify", "--full", "--kit", str(kit.root), str(out)], env, deadline)
        result["steps"]["verify-full"] = full
        full_ok = full["exitCode"] == 0 and text.startswith("VERIFIED (full):")
        dashboard = folder / f"{scenario}.html"
        step, _ = cli(["dashboard", str(out), "--out", str(dashboard)], env, deadline)
        result["steps"]["dashboard"] = step
        result["dashboardWritten"] = dashboard.is_file() and dashboard.stat().st_size > 0
        counts = result["gate"]
        result["pass"] = (gate["refused"] is False and counts["passed"] > 0 and counts["failed"] == 0
                          and counts["unknown"] == 0 and k_ok and utility_ok and limited_ok and full_ok
                          and step["exitCode"] == 0 and result["dashboardWritten"])
    except Exception:  # noqa: BLE001 - exception text or CLI output can contain values.
        result["error"] = "missing-or-invalid-step"
    return result


def input_bindings(kit):
    # Kit access validates the catalogue and table paths before their bytes are hashed.
    kit.scenarios()
    metadata = hashlib.sha256((kit.root / "metadata/scenarios.json").read_bytes()).hexdigest()
    inputs = {scenario: kit.input_digests(kit.scenario(scenario)["dataset"]) for scenario in SCENARIOS}
    if not all(inputs.values()):
        raise ValueError("no inputs")
    return metadata, inputs


def write_record(path, record):
    validate_record(record)
    # Replace any earlier verdict immediately, and again at completion. A crash cannot leave an old green.
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as stream:
        stream.write(canonical_bytes(record))
        temp = Path(stream.name)
    os.replace(temp, path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kit", type=Path, default=None)
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=720, help="total CLI time budget in seconds")
    parser.add_argument("--sha", help="require this exact full Git HEAD")
    parser.add_argument("--validate-record", type=Path, help="check record format only; never reruns the smoke")
    args = parser.parse_args()
    if args.validate_record:
        try:
            raw = args.validate_record.read_bytes()
            record = loads_strict(raw)
            validate_record(record)
            if raw != canonical_bytes(record):
                return 1
        except Exception:  # noqa: BLE001 - malformed records fail without echoing their contents.
            return 1
        print("record format valid (not a fresh smoke)")
        return 0
    sha = git("rev-parse", "HEAD")
    output = args.out_root.resolve()
    if output == ROOT or ROOT in output.parents:
        print("smoke: FAIL output must be outside the checkout")
        return 1
    evidence = output / sha
    if evidence.is_symlink() or (os.name == "nt" and os.path.lexists(evidence)
                                 and evidence.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT):
        print("smoke: FAIL evidence directory is a link")
        return 1
    evidence.mkdir(parents=True, exist_ok=True)
    record = {"sha": sha, "toolRevision": sha, "metadataDigest": None,
              "inputs": {s: {} for s in SCENARIOS}, "scenarios": {s: new_result(None) for s in SCENARIOS},
              "delivery": {"HEALTH-S1": new_result("released")},
              "pass": False}
    path = evidence / "smoke.json"
    write_record(path, record)
    # Deliberately do not inherit caller keys, kit selectors, Python/Git overrides or time settings.
    keep = ("PATH", "SYSTEMROOT", "PATHEXT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "APPDATA",
            "LOCALAPPDATA", "HOMEDRIVE", "HOMEPATH", "COMSPEC", "VIRTUAL_ENV", "PYTHONPYCACHEPREFIX")
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env.update(PYTHONPATH=str(ROOT / "src"), PYTHONUTF8="1", TZ="UTC", PETS_HMAC_KEY=secrets.token_hex(32))
    error = "configuration-invalid"
    try:
        expectations = loads_strict(git("show", f"{sha}:tests/smoke/expectations.json").encode("utf-8"))
        if (set(expectations) != set(SCENARIOS)
                or any(v not in ("released", "refused") for v in expectations.values())
                or not math.isfinite(args.timeout) or args.timeout <= 0):
            raise ValueError("configuration invalid")
        record["scenarios"] = {s: new_result(expectations[s]) for s in SCENARIOS}
        if args.sha is not None and args.sha != sha:
            error = "revision-mismatch"
            raise ValueError("revision mismatch")
        if git("status", "--porcelain=v1", "--untracked-files=all"):
            error = "dirty-checkout"
            raise ValueError("dirty checkout")
        error = "kit-unavailable"
        kit = Kit(args.kit or os.environ.get("PETS_KIT") or PINNED_KIT)
        # Same fail-closed resolution as #73: an explicit wrong PETS_KIT never falls back to the pinned kit.
        if not (kit.root / "results/benchmark.json").is_file():
            raise ValueError("kit missing benchmark")
        record["metadataDigest"], record["inputs"] = input_bindings(kit)
        folder = Path(tempfile.mkdtemp(prefix="attempt-", dir=evidence))
        deadline = time.monotonic() + args.timeout
        # Delivery and plain release are independent CLI lanes. Both are mandatory; neither can hide the other.
        with ThreadPoolExecutor(max_workers=2) as pool:
            measured = pool.submit(scenario_smoke, "HEALTH-S1", "released", kit, folder / "measured", sha,
                                   record["inputs"]["HEALTH-S1"], env, deadline, measured=True)
            for scenario in SCENARIOS:
                record["scenarios"][scenario] = scenario_smoke(scenario, expectations[scenario], kit, folder,
                                                             sha, record["inputs"][scenario], env, deadline)
            record["delivery"]["HEALTH-S1"] = measured.result()
        error = "identity-changed"
        if (git("rev-parse", "HEAD") != sha or git("status", "--porcelain=v1", "--untracked-files=all")
                or input_bindings(kit) != (record["metadataDigest"], record["inputs"])):
            raise ValueError("identity changed")
        error = None
    except Exception:  # noqa: BLE001 - even a path/catalogue error may contain source values.
        for scenario in [*record["scenarios"].values(), *record["delivery"].values()]:
            scenario.update({"pass": False, "error": error})
    record["pass"] = error is None and all(s["pass"] for s in [*record["scenarios"].values(),
                                                              *record["delivery"].values()])
    try:
        write_record(path, record)
    except Exception:  # noqa: BLE001 - retain the initial failed record, never echo contents.
        # The initial failed record remains in place if final validation/writing cannot complete.
        print(f"smoke: FAIL record-write sha={sha}")
        return 1
    print(f"smoke: {'PASS' if record['pass'] else 'FAIL'} sha={sha}")
    return 0 if record["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
