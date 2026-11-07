"""The CS eval exports go through the production text checks (D37), through the real CLI.

Rule: before publication the packager runs the gate's ``text.*`` checks on the exact bytes of
``customer_service_eval_redacted.csv`` (stitched per conversation) and ``customer_service_eval_spans.jsonl``.
A turn with a high-severity hit is masked whole (``[REDACTED]``), keeping the format: same rows, and that turn's
spans become whole-turn spans, one per label. The masked-turn count goes into ``bundle_index.json``. A successful
redactor run is not proof. A hit the packager cannot mask (in the spans file) or a check that cannot run refuses.

Failure rows (trigger -> result):
  planted miss: an eval turn the redactor leaves but text.ip-addresses flags -> that turn masked whole, counted 1
  no miss                                                                   -> maskedTurns 0, texts unchanged
  an identifier in an exported turn id (spans file flagged)                 -> exit 1 cs_eval_spans_flagged
  a text check missing from the registry                                    -> refused cs_eval_checks_unavailable
  a text check that errors                                                  -> refused cs_eval_check_error
"""
from __future__ import annotations

import csv
import io
import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest
from sub_helpers import TEST_KEY, submission

from pets_release.kit import Kit
from pets_release.pseudonym import MasterKey
from pets_release.submission import SubmissionRefused, build_submission

# The redactor misses this spaced-out public IP; the gate's ip-addresses check finds it (synthetic).
MISS = "ip 8 . 8 . 8 . 8 is down again"


def _kit_with_turn(world, tmp_path, turn_id, text):
    kit, rel = world
    k2 = tmp_path / "kit"
    shutil.copytree(kit, k2)
    p = k2 / "data" / "customer_service" / "turns.csv"
    with p.open("a", encoding="utf-8", newline="") as fh:
        csv.writer(fh, lineterminator="\n").writerow([turn_id, "c2", "3", "customer", "2025-01-02T10:02:00Z", text])
    return k2, rel


def _bundle(kit, rel, out):
    p = submission("--out", str(out), "--release", str(rel), "--kit", str(kit), "--partial")
    assert p.returncode == 0, p.stdout + p.stderr
    texts = {r["turn_id"]: r["text"] for r in
             csv.DictReader(io.StringIO((out / "customer_service_eval_redacted.csv").read_text("utf-8"), newline=""))}
    spans = {r["record_id"]: r["spans"] for r in
             map(json.loads, (out / "customer_service_eval_spans.jsonl").read_text("utf-8").splitlines())}
    idx = json.loads((out / "bundle_index.json").read_text("utf-8"))
    return p, texts, spans, idx


def test_a_planted_miss_is_masked_whole_and_counted(world, tmp_path):
    kit, rel = _kit_with_turn(world, tmp_path, "t6", MISS)
    p, texts, spans, idx = _bundle(kit, rel, tmp_path / "pets_submission")
    assert texts["t6"] == "[REDACTED]"
    assert spans["t6"] == [{"start": 0, "end": len(MISS), "label": "IP_ADDRESS"}]
    assert idx["customerServiceEval"]["maskedTurns"] == 1
    assert sorted(texts) == ["t1", "t2", "t3", "t4", "t6"]  # same rows
    assert texts["t2"] == "Thanks for contacting us"  # other turns untouched
    assert "masked turns=1" in p.stdout


def test_without_a_miss_nothing_is_masked(world, tmp_path):
    kit, rel = world
    _p, texts, _spans, idx = _bundle(kit, rel, tmp_path / "pets_submission")
    assert idx["customerServiceEval"]["maskedTurns"] == 0
    assert "[REDACTED]" not in texts.values()


def test_an_identifier_in_an_exported_turn_id_refuses(world, tmp_path):
    kit, rel = _kit_with_turn(world, tmp_path, "t-8 . 8 . 8 . 8", "fine thanks")
    out = tmp_path / "pets_submission"
    p = submission("--out", str(out), "--release", str(rel), "--kit", str(kit), "--partial")
    assert p.returncode == 1 and "cs_eval_spans_flagged" in p.stdout
    assert not out.exists()


# ---------- the checks must actually run (build seam: the registry is the boundary) ----------

def _refused(world, tmp_path, monkeypatch, checks):
    import pets_release.checks.registry as reg

    monkeypatch.setattr(reg, "all_checks", lambda scope=None: checks)
    kit, rel = world
    out = tmp_path / "s"
    with pytest.raises(SubmissionRefused) as e:
        build_submission(kit=Kit(kit), releases=[rel], out=out, master=MasterKey.from_text(TEST_KEY), partial=True,
                         scorecard=lambda *a, **k: pytest.fail("must refuse before scoring"))
    assert not out.exists() and not Path(str(out) + ".scoring").exists()
    return e.value.code


def test_a_text_check_missing_from_the_registry_refuses(world, tmp_path, monkeypatch):
    from pets_release.checks.registry import all_checks

    kept = tuple(c for c in all_checks() if c.name != "text.ip-addresses")
    assert _refused(world, tmp_path, monkeypatch, kept) == "cs_eval_checks_unavailable"


def test_a_text_check_that_errors_refuses(world, tmp_path, monkeypatch):
    from pets_release.checks.registry import all_checks

    def boom(*a, **k):
        raise RuntimeError("check crashed")

    broken = tuple(replace(c, run=boom) if c.name == "text.emails" else c for c in all_checks())
    assert _refused(world, tmp_path, monkeypatch, broken) == "cs_eval_check_error"
