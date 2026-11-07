"""Planted content-free artefacts tested through the real close-gate CLI."""

import json
import shutil
from pathlib import Path

import pytest

from tests.overnight import test_done_report_encoding as encoding

close_gate = encoding.close_gate
pytestmark = pytest.mark.skipif(encoding.POWERSHELL is None, reason="requires Windows PowerShell 5.1")


@pytest.fixture
def evidence(close_gate):
    run, body = close_gate
    fields = dict(line[2:].split(": ", 1) for line in body.splitlines()
                  if line.startswith("- ") and ": " in line)
    head = fields["Head"]
    folder = Path(fields["Artefacts"]).parent / "evidence"
    release = folder / "release"
    scoring = folder / "release.scoring"
    release.mkdir(parents=True)
    scoring.mkdir()
    check = {"check": "release.synthetic", "version": "1", "status": "pass",
             "scope": "release", "hits": 0, "denominator": {"n": 1, "unit": "files"}}
    manifest = {"bindings": {"toolRevision": head,
                              "checkVersions": {"release.synthetic": "1"}},
                "gate": {"status": "pass", "checks": [check]}}
    gate = {"records": [dict(check, violations=[])], "refused": False, "registryError": None}
    manifest_path = release / "privacy_manifest.json"
    gate_path = scoring / "gate_report.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    gate_path.write_text(json.dumps(gate), encoding="utf-8")
    (folder / "run.log").write_text(
        f"revision={head}\nRELEASED: release (scoring: release.scoring)\n"
        "run exit=0\nverify exit=0\nverify-full exit=0\n", encoding="utf-8")
    body = body.replace(fields["Artefacts"], str(folder)).replace(
        "N/A: test-only encoding fixture", "gate 1/1 pass; verify (limited) exit 0; verify --full exit 0")
    return run, body, folder, manifest_path, gate_path


def test_wrong_manifest_revision_is_a_gap(evidence):
    """Rule: a planted release for another Head cannot prove this report."""
    run, body, _, manifest_path, _ = evidence
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["bindings"]["toolRevision"] = "0" * 40
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    result = run("body-file", body)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "manifest revision" in result.stdout


def test_missing_gate_report_is_a_gap(evidence):
    """Rule: an existing folder and passing prose are not a gate report."""
    run, body, folder, _, gate_path = evidence
    gate_path.unlink()
    # A passing report elsewhere must not replace this release's paired report.
    (folder / "gate_report.json").write_text('{"records": []}', encoding="utf-8")
    result = run("body-file", body)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "gate report" in result.stdout


@pytest.mark.parametrize("defect", [
    "error", "fail", "not_run", "unknown-status", "missing-status", "missing-check",
    "empty-records", "duplicate-check", "wrong-version", "extra-record-key",
    "extra-report-key", "refused", "registry-error", "manifest-disagreement",
    "duplicate-json-key", "non-finite-json",
])
def test_gate_records_must_be_complete_and_successful(evidence, defect):
    """Rule: missing, failing, ambiguous or malformed gate records are gaps."""
    run, body, _, _, gate_path = evidence
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    record = gate["records"][0]
    if defect in {"error", "fail", "not_run"}:
        record["status"] = defect
    elif defect == "unknown-status":
        record["status"] = "unknown"
    elif defect == "missing-status":
        del record["status"]
    elif defect == "missing-check":
        record["check"] = "release.other"
    elif defect == "empty-records":
        gate["records"] = []
    elif defect == "duplicate-check":
        gate["records"].append(record)
    elif defect == "wrong-version":
        record["version"] = "2"
    elif defect == "extra-record-key":
        record["planted"] = True
    elif defect == "extra-report-key":
        gate["planted"] = True
    elif defect == "refused":
        gate["refused"] = True
    elif defect == "registry-error":
        gate["registryError"] = "synthetic error"
    elif defect == "manifest-disagreement":
        record["denominator"]["n"] = 2
    text = json.dumps(gate)
    if defect == "duplicate-json-key":
        text = text.replace('"status": "pass"', '"status": "error", "status": "pass"')
    elif defect == "non-finite-json":
        text = text.replace('"hits": 0', '"hits": NaN')
    gate_path.write_text(text, encoding="utf-8")
    result = run("body-file", body)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "gate report" in result.stdout


def test_correct_synthetic_folder_reports_status_counts(evidence):
    """Rule: accept bound successful records, not just successful report prose."""
    run, body, _, _, _ = evidence
    result = run("body-file", body)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "pass=1 not_applicable=0 fail=0 error=0" in result.stdout


@pytest.mark.parametrize("defect", [
    "missing-limited", "missing-full", "limited-failed", "full-failed",
    "missing-log", "wrong-revision", "missing-revision", "duplicate-exit", "duplicate-revision",
])
def test_claimed_verify_needs_revision_bound_exit_zero(evidence, defect):
    """Rule: each claimed verify tier needs its own unambiguous machine exit."""
    run, body, folder, _, _ = evidence
    log = folder / "run.log"
    text = log.read_text(encoding="utf-8")
    if defect == "missing-limited":
        text = text.replace("verify exit=0\n", "")
    elif defect == "missing-full":
        text = text.replace("verify-full exit=0\n", "")
    elif defect == "limited-failed":
        text = text.replace("verify exit=0", "verify exit=1")
    elif defect == "full-failed":
        text = text.replace("verify-full exit=0", "verify-full exit=2")
    elif defect == "wrong-revision":
        text = "revision=" + "0" * 40 + "\n" + "\n".join(text.splitlines()[1:])
    elif defect == "missing-revision":
        text = "\n".join(text.splitlines()[1:])
    elif defect == "duplicate-exit":
        text += "verify exit=1\n"
    elif defect == "duplicate-revision":
        text += "revision=" + "0" * 40 + "\n"
    log.write_text(text, encoding="utf-8")
    if defect == "missing-log":
        log.unlink()
        (folder / "planted.log").write_text("verify exit=0\nverify-full exit=0\n", encoding="utf-8")
    result = run("body-file", body)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "verify" in result.stdout


@pytest.mark.parametrize("claim", [
    "gate 1/1 pass", "verify (limited) exit 0", "verify --full exit 0",
    "gate passed", "verify: pass", "verify full exit 0", "gate=41/41",
])
def test_na_cannot_hide_gate_or_verify_claims(close_gate, claim):
    """Rule: N/A is an exemption, not a way to assert unchecked passes."""
    run, body = close_gate
    result = run("body-file", body.replace("N/A: test-only encoding fixture",
                                            f"N/A: docs-only; {claim}"))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "N/A must not claim gate/verify outcomes" in result.stdout


def test_embedded_gate_verify_na_is_not_an_explicit_exemption(close_gate):
    """Rule: only an Outcome starting N/A: reason exempts machine records."""
    run, body = close_gate
    result = run("body-file", body.replace("N/A: test-only encoding fixture",
        "Quick start commands exited 0. Gate/verify: N/A, documentation-only scope."))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "release manifest missing" in result.stdout


def test_na_ticket_still_passes(close_gate):
    run, _ = close_gate
    result = run("body-file")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("aggregate", [True, False])
def test_successful_gate_can_have_low_severity_hits(evidence, aggregate):
    """Rule: production aggregate reports omit locations, not violation counts."""
    run, body, _, manifest_path, gate_path = evidence
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    manifest["gate"]["checks"][0]["hits"] = 1
    record = gate["records"][0]
    record["hits"] = 1
    violation = {"check": "release.synthetic", "label": "synthetic-low",
                 "severity": "low", "file": "synthetic.csv", "column": None, "count": 1}
    if not aggregate:
        violation["locations"] = []
    record["violations"] = [violation]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    gate_path.write_text(json.dumps(gate), encoding="utf-8")
    result = run("body-file", body)
    assert result.returncode == 0, result.stdout + result.stderr


def test_regular_file_is_not_an_artefact_folder(evidence):
    """Rule: a planted file cannot bypass folder record validation."""
    run, body, folder, _, _ = evidence
    planted = folder.parent / "planted-file"
    planted.write_text("synthetic", encoding="utf-8")
    result = run("body-file", body.replace(str(folder), str(planted)))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "Artefacts folder" in result.stdout


def test_outcome_without_gate_verify_keywords_still_requires_records(close_gate):
    """Rule: avoiding gate/verify wording cannot bypass machine validation."""
    run, body = close_gate
    result = run("body-file", body.replace("N/A: test-only encoding fixture",
        "Close-gate CLI read-only: issue checks exited 0; evidence gaps=0."))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "release manifest missing" in result.stdout


def test_not_applicable_checks_are_named_and_not_counted_as_passes(evidence):
    run, body, _, manifest_path, gate_path = evidence
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    for record in (manifest["gate"]["checks"][0], gate["records"][0]):
        record["status"] = "not_applicable"
        record["denominator"]["n"] = 0
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    gate_path.write_text(json.dumps(gate), encoding="utf-8")
    result = run("body-file", body)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "pass=0 not_applicable=1 fail=0 error=0" in result.stdout
    assert "Gate not_applicable checks: release.synthetic" in result.stdout


@pytest.mark.parametrize("tier", ["limited", "full"])
def test_limited_always_required_and_full_required_when_claimed_in_utf16_log(evidence, tier):
    run, body, folder, _, _ = evidence
    log = folder / "run.log"
    text = log.read_text(encoding="utf-8")
    if tier == "limited":
        body = body.replace("; verify --full exit 0", "")
        text = text.replace("verify-full exit=0\n", "")
    else:
        body = body.replace("; verify (limited) exit 0", "")
    log.write_text(text, encoding="utf-16")
    result = run("body-file", body)
    assert result.returncode == 0, result.stdout + result.stderr


def test_second_planted_manifest_cannot_replace_wrong_revision(evidence):
    run, body, folder, manifest_path, _ = evidence
    other = folder / "planted" / "privacy_manifest.json"
    other.parent.mkdir()
    other.write_bytes(manifest_path.read_bytes())
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["bindings"]["toolRevision"] = "0" * 40
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    result = run("body-file", body)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "manifest revision" in result.stdout


def test_multi_release_folder_validates_every_manifest(evidence):
    """Seam: CLI; several bound releases are not an ambiguous identity."""
    run, body, folder, manifest_path, gate_path = evidence
    for name in ("measured-default", "measured-acme"):
        (folder / name).mkdir()
        (folder / (name + ".scoring")).mkdir()
        shutil.copyfile(manifest_path, folder / name / manifest_path.name)
        shutil.copyfile(gate_path, folder / (name + ".scoring") / gate_path.name)
        text = (folder / "run.log").read_text(encoding="utf-8").replace(
            "RELEASED: release (", f"RELEASED: {name} (")
        (folder / (name + ".log")).write_text(text, encoding="utf-8")
    body = body.replace("; verify (limited) exit 0; verify --full exit 0", "")
    result = run("body-file", body)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("pass=1 not_applicable=0 fail=0 error=0") == 3


@pytest.fixture
def shared_logs(evidence):
    run, body, folder, manifest_path, gate_path = evidence
    head = json.loads(manifest_path.read_text(encoding="utf-8"))["bindings"]["toolRevision"]
    for name in ("measured-default", "measured-acme"):
        (folder / name).mkdir()
        (folder / (name + ".scoring")).mkdir()
        shutil.copyfile(manifest_path, folder / name / manifest_path.name)
        shutil.copyfile(gate_path, folder / (name + ".scoring") / gate_path.name)
    manifest_path.parent.rename(folder / "release-health-s1")
    gate_path.parent.rename(folder / "release-health-s1.scoring")
    log = folder / "run.log"
    text = log.read_text(encoding="utf-8").replace("RELEASED: release (", "RELEASED: release-health-s1 (")
    log.unlink()
    (folder / "arbitrary-health.log").write_text(text, encoding="utf-16")
    (folder / "measured.log").write_text(
        f"revision={head}\ndirty=False\n"
        "== measured-default\nRELEASED: measured-default (measured)\n"
        "wire exit=0\nverify exit=0\nverify-full exit=0\n"
        "== measured-acme\nRELEASED: measured-acme (measured)\n"
        "wire exit=0\nverify exit=0\nverify-full exit=0\n", encoding="utf-16")
    return run, body, folder


def test_shared_log_binds_each_release_by_identity(shared_logs):
    """Seam: CLI; #120's three releases use two arbitrarily named logs."""
    run, body, _ = shared_logs
    result = run("body-file", body)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("pass=1 not_applicable=0 fail=0 error=0") == 3


def test_planted_extra_manifest_with_wrong_revision_fails(evidence):
    run, body, folder, manifest_path, _ = evidence
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["bindings"]["toolRevision"] = "0" * 40
    other = folder / "planted" / "privacy_manifest.json"
    other.parent.mkdir()
    other.write_text(json.dumps(manifest), encoding="utf-8")
    result = run("body-file", body)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "manifest revision" in result.stdout


def test_no_verify_claim_still_requires_limited_tier_record(shared_logs):
    """Seam: CLI; gate-only prose cannot hide a release's missing tier."""
    run, body, folder = shared_logs
    body = body.replace("; verify (limited) exit 0; verify --full exit 0", "")
    log = folder / "measured.log"
    text = log.read_text(encoding="utf-16")
    # The first release is good; the second must not borrow its tier record.
    text = text.rsplit("verify exit=0\n", 1)
    log.write_text("".join(text), encoding="utf-16")
    result = run("body-file", body)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "verify (limited) exit 0 record missing" in result.stdout
