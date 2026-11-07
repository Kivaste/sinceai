"""Purpose checks are a publication prerequisite and a fresh `verify --full` check (issue #60).

Rule: after local suppression, `run` evaluates every policy purpose check on full data (the kit-eval adapter's
in-process tasks; before = source scored against itself). It publishes only when every check is `ok` and scores
>= 0.9, or below 0.9 only for a policy-enumerated sacrifice at or above its floor; error, not_answerable and
missing are never waived. The manifest carries the actual before/after scores (`measured.utility`, `sacrifices`).
`verify --full` re-runs the same evaluation on the release folder and fails on any failing check or on any
difference from the signed `measured.utility` scores.

Rows (trigger -> result), real CLI, synthetic minikit rows only:
  hand plan, every purpose check passes        -> exit 0; measured.utility measured, before/after per policy check;
                                                  every sacrifice has numeric before/after; both verify tiers 0
  source measures for H-U2 and H-U7 blanked    -> exit 1, no release folder, refusal report names both checks
  released purpose column blanked, re-signed   -> limited verify 0 (recipient cannot run purpose checks);
                                                  full verify 1, names the failing check
  signed measured.utility after score edited   -> full verify 1 (re-run differs from the manifest)
"""
from __future__ import annotations

import json
import shutil

from release_helpers import MANIFEST, resign
from run_helpers import blank_columns, build_kit, cli, coarse_qis, run_args

from pets_release.policy import get_policy

POLICY = get_policy("HEALTH-S1")


def _manifest(rel):
    return json.loads((rel / MANIFEST).read_text(encoding="utf-8"))


def test_published_release_carries_measured_purpose_scores(released):
    _kit, out, proc = released
    assert proc.returncode == 0, proc.stdout + proc.stderr
    m = _manifest(out)
    util = m["measured"]["utility"]
    assert util["status"] == "measured", util
    tasks = {t["task"]: t for t in util["tasks"]}
    assert set(tasks) == set(POLICY.purpose_checks)
    for t in tasks.values():
        assert t["status"] == "ok"
        assert isinstance(t["before"], float) and isinstance(t["after"], float)
        assert t["after"] >= 0.6
    sac = {s["check"]: s for s in m["sacrifices"]}
    assert set(sac) == {s["check"] for s in POLICY.sacrifices}
    for name, s in sac.items():
        assert s["before"] == tasks[name]["before"] and s["after"] == tasks[name]["after"]


def test_failing_purpose_checks_refuse_publication(tmp_path):
    def edit(folder):
        coarse_qis(folder)
        blank_columns(folder, "ed_visits", ["los_minutes", "discharge_ts", "triage"])  # H-U2
        blank_columns(folder, "lab_results", ["value"])  # H-U7

    kit = build_kit(tmp_path / "kit", edit)
    out = tmp_path / "out" / "rel"
    proc = cli(*run_args(kit, out))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert not out.exists()
    report = json.loads((out.parent / "rel.scoring" / "refusal_report.json").read_text(encoding="utf-8"))
    reasons = " ".join(report["reasons"])
    assert "purpose:H-U2" in reasons and "purpose:H-U7" in reasons, reasons


def _copy(released, tmp_path):
    kit, out, proc = released
    assert proc.returncode == 0, proc.stdout + proc.stderr
    rel = tmp_path / "rel"
    shutil.copytree(out, rel)
    return kit, rel


def test_full_verify_reruns_purpose_checks(released, tmp_path):
    kit, rel = _copy(released, tmp_path)
    import csv
    import io

    text = (rel / "ed_visits.csv").read_text(encoding="utf-8")
    rows = list(csv.reader(io.StringIO(text, newline="")))
    col = rows[0].index("triage")
    for r in rows[1:]:
        r[col] = "T9"  # one triage level for every visit: H-U2 length of stay by triage loses its groups
    buf = io.StringIO(newline="")
    csv.writer(buf, lineterminator="\n").writerows(rows)
    (rel / "ed_visits.csv").write_bytes(buf.getvalue().encode("utf-8"))
    resign(rel)

    lim = cli("verify", str(rel))
    assert lim.returncode == 0, lim.stdout
    full = cli("verify", "--full", "--kit", str(kit), str(rel))
    assert full.returncode == 1, full.stdout
    assert "purpose" in full.stdout and "H-U2" in full.stdout, full.stdout


def test_full_verify_fails_when_signed_scores_differ_from_rerun(released, tmp_path):
    kit, rel = _copy(released, tmp_path)
    m = _manifest(rel)
    m["measured"]["utility"]["tasks"][0]["after"] = 0.5
    (rel / MANIFEST).write_text(json.dumps(m), encoding="utf-8")
    resign(rel)
    full = cli("verify", "--full", "--kit", str(kit), str(rel))
    assert full.returncode == 1, full.stdout
    assert "measured.utility" in full.stdout, full.stdout
