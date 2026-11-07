"""Tests for the redaction measurement harness. Fixtures are small hand-made synthetic rows."""
from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

import pytest

from pets_release.redaction_eval import (
    CS_S1_TARGET_LABELS,
    HELD_OUT_FRACTION,
    build_frame,
    check_precision_floor,
    export_spot_check,
    person_twice,
    score_frame,
    skeleton,
    split_by_skeleton,
    whole_turn_predictor,
)
from pets_release.redaction_eval.frame import Frame
from pets_release.redaction_eval.harness import evaluate_frames
from pets_release.redaction_eval.predictors import regex_predictor
from pets_release.redaction_eval.scoring import exact_scores


def sp(start, end, label):
    return {"start": start, "end": end, "label": label}


def make_frame():
    # 3 conversations; c3 is eval and must be excluded from the frame.
    turns = [
        {"turn_id": "T1", "conversation_id": "C1", "text": "Hello Anna Test call 0401234567"},
        {"turn_id": "T2", "conversation_id": "C1", "text": "Thanks bye"},
        {"turn_id": "T3", "conversation_id": "C2", "text": "mail me at a@b.fi"},
        {"turn_id": "T4", "conversation_id": "C3", "text": "eval turn"},
    ]
    convs = [
        {"conversation_id": "C1", "split": "train"},
        {"conversation_id": "C2", "split": "train"},
        {"conversation_id": "C3", "split": "eval"},
    ]
    gold = {
        "T1": [sp(6, 15, "PERSON"), sp(21, 31, "PHONE")],
        "T3": [sp(11, 17, "EMAIL")],
    }
    return build_frame(turns, convs, gold)


def test_frame_is_all_train_turns_gold_absent_empty():
    fr = make_frame()
    assert sorted(fr.texts) == ["T1", "T2", "T3"]
    assert fr.gold["T2"] == []
    assert fr.conversation_of["T3"] == "C2"


def test_perfect_prediction_scores_one_and_has_support():
    fr = make_frame()
    r = score_frame(fr.gold, fr.gold)
    assert r["micro_f2_all"]["f2"] == 1.0
    assert r["micro_f2_all"]["support"] == {"EMAIL": 1, "PERSON": 1, "PHONE": 1}
    assert r["identifying_micro"]["precision"] == 1.0
    assert r["identifying_micro"]["support"]["PERSON"] == 1


def test_exact_mode_is_pinned_not_overlap():
    gold = {"A": [sp(0, 10, "PERSON")]}
    near = {"A": [sp(0, 9, "PERSON")]}
    assert exact_scores(gold, near)["micro"]["tp"] == 0  # overlap would count it
    assert exact_scores(gold, {"A": [sp(0, 10, "ORG")]})["micro"]["tp"] == 0  # label equality


def test_predictions_on_gold_absent_turns_are_false_positives():
    fr = make_frame()
    pred = {k: list(v) for k, v in fr.gold.items()}
    pred["T2"] = [sp(0, 6, "PERSON")]
    r = score_frame(fr.gold, pred)
    assert r["micro_f2_all"]["precision"] < 1.0


def test_cs_s1_target_recall_and_health_hits():
    gold = {
        "A": [sp(0, 5, "IBAN"), sp(6, 9, "SECRET"), sp(10, 12, "HEALTH"), sp(13, 15, "HEALTH")],
    }
    pred = {"A": [sp(0, 5, "IBAN"), sp(10, 12, "HEALTH")]}
    r = score_frame(gold, pred)
    t = r["cs_s1_target"]
    assert set(CS_S1_TARGET_LABELS) == {"NATIONAL_ID", "PAYMENT_CARD", "IBAN", "SECRET"}
    assert t["recall"] == 0.5
    assert t["support"] == {"IBAN": 1, "SECRET": 1, "NATIONAL_ID": 0, "PAYMENT_CARD": 0}
    assert t["health_hits"] == 1
    assert t["health_support"] == 2


def test_whole_turn_predictor_scores_near_zero_precision():
    fr = make_frame()
    pred = {tid: whole_turn_predictor(text) for tid, text in fr.texts.items()}
    r = score_frame(fr.gold, pred)
    assert r["micro_f2_all"]["precision"] == 0.0
    assert r["micro_f2_all"]["recall"] == 0.0


def test_skeleton_replaces_spans_digits_case_whitespace():
    text = "Hello  Anna Test call 0401234567 at 12 pm"
    gold = [sp(7, 16, "PERSON"), sp(22, 32, "PHONE")]
    assert skeleton(text, gold) == "hello <person> call <phone> at # pm"


def _template_frame(n_templates=100, per=4):
    turns, convs, gold = [], [], {}
    for t in range(n_templates):
        word = chr(97 + t % 26) + chr(97 + t // 26)
        for i in range(per):
            cid = f"C{t}_{i}"
            convs.append({"conversation_id": cid, "split": "train"})
            for j in range(1):
                tid = f"T{t}_{i}_{j}"
                text = f"template {word} name Anna{i}"
                turns.append({"turn_id": tid, "conversation_id": cid, "text": text})
                s = text.index("Anna")
                gold[tid] = [sp(s, len(text), "PERSON")]
    return build_frame(turns, convs, gold)


def test_split_has_zero_skeleton_overlap_and_is_deterministic():
    fr = _template_frame()
    a = split_by_skeleton(fr)
    b = split_by_skeleton(fr)
    assert a == b
    assert a.held_out_conversations and a.dev_conversations
    assert not (set(a.held_out_conversations) & set(a.dev_conversations))
    assert not (a.held_out_skeletons & a.dev_skeletons)
    assert a.unseen_skeleton_share == 1.0 and a.unseen_span_skeleton_share == 1.0
    assert 0 < a.held_out_turn_share < 0.6
    assert HELD_OUT_FRACTION == 0.2


def test_split_conversation_held_out_only_if_all_turns_held_out():
    # A conversation mixing a common (dev) skeleton with a rare one must stay in dev.
    turns = [{"turn_id": f"T{i}", "conversation_id": f"C{i}", "text": "common"} for i in range(30)]
    convs = [{"conversation_id": f"C{i}", "split": "train"} for i in range(30)]
    turns.append({"turn_id": "TX", "conversation_id": "C0", "text": "rare thing"})
    gold = {t["turn_id"]: [sp(0, 1, "PERSON")] for t in turns}
    fr = build_frame(turns, convs, gold)
    s = split_by_skeleton(fr)
    for sk in s.held_out_skeletons:
        assert sk not in s.dev_skeletons
    assert "C0" not in s.held_out_conversations or "common" not in s.dev_skeletons


def test_split_assertion_fires_on_planted_overlap():
    from pets_release.redaction_eval.split import assert_zero_overlap

    with pytest.raises(ValueError):
        assert_zero_overlap({"a", "b"}, {"b"})


def test_person_reported_twice():
    gold = {"A": [sp(0, 4, "PERSON")], "B": [sp(0, 4, "PERSON")]}
    gaz = {"A": [sp(0, 4, "PERSON")], "B": [sp(0, 4, "PERSON")]}
    dev = {"A": [sp(0, 4, "PERSON")]}
    r = person_twice(gold, gaz, dev, ["A", "B"])
    assert r["controller_gazetteer"]["recall"] == 1.0
    assert r["dev_lexicon"]["recall"] == 0.5
    assert r["controller_gazetteer"]["support"] == 2


def test_precision_floor():
    ok = {"micro_f2_all": {"precision": 0.5}}
    assert check_precision_floor(ok, 0.3) is True
    assert check_precision_floor({"micro_f2_all": {"precision": 0.1}}, 0.3) is False
    assert check_precision_floor({}, 0.3) is False  # missing = fail closed


def test_spot_check_sheet_written_outside_repo(tmp_path):
    fr = make_frame()
    pred = {tid: [] for tid in fr.texts}
    out = tmp_path / "sheet.csv"
    assert export_spot_check(fr, pred, out, n=2, repo_root=Path(__file__).resolve().parents[2]) == 2
    with open(out, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert {"turn_id", "original", "redacted"} <= set(rows[0])


def test_spot_check_refuses_path_inside_repo():
    repo = Path(__file__).resolve().parents[2]
    fr = make_frame()
    with pytest.raises(ValueError):
        export_spot_check(fr, {}, repo / "src" / "sheet.csv", n=2, repo_root=repo)


def test_turn_mode_split_zero_overlap_on_shared_templates():
    # Every conversation shares the common skeleton, so the strict rule holds out nothing;
    # turn mode must still produce a non-empty held-out set with zero overlap.
    turns, convs, gold = [], [], {}
    for i in range(300):
        cid = f"C{i}"
        convs.append({"conversation_id": cid, "split": "train"})
        for j, w in enumerate(("hello", "name", "x" + chr(97 + i % 26) + chr(97 + i // 26))):
            tid = f"T{i}_{j}"
            turns.append({"turn_id": tid, "conversation_id": cid, "text": f"{w} Anna"})
            gold[tid] = [sp(len(w) + 1, len(w) + 5, "PERSON")]
    fr = build_frame(turns, convs, gold)
    assert not split_by_skeleton(fr).held_out_turns
    s = split_by_skeleton(fr, mode="turn")
    assert s.held_out_turns and s.dev_turns
    assert not (s.held_out_skeletons & s.dev_skeletons)
    assert not (set(s.held_out_turns) & set(s.dev_turns))


# ---------- review round 1 ----------

def _git_repo(path):
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


def test_spot_check_autodetects_repo_when_root_omitted(tmp_path, monkeypatch):
    repo = _git_repo(tmp_path / "repo")
    (repo / "sub").mkdir()
    fr = make_frame()
    with pytest.raises(ValueError):
        export_spot_check(fr, {}, repo / "sub" / "sheet.csv", n=1)  # repo_root omitted
    # a WRONG explicit root must not switch the check off
    other = tmp_path / "elsewhere"
    other.mkdir()
    with pytest.raises(ValueError):
        export_spot_check(fr, {}, repo / "sub" / "sheet.csv", n=1, repo_root=other)
    # cwd inside a repo, target outside any repo: allowed
    monkeypatch.chdir(repo)
    outside = tmp_path / "out" / "sheet.csv"
    assert export_spot_check(fr, {}, outside, n=1) == 1
    assert outside.exists()
    # git-ignored folder inside repo: allowed
    (repo / ".gitignore").write_text("private/\n")
    assert export_spot_check(fr, {}, repo / "private" / "s.csv", n=1) == 1


def test_spot_check_fails_closed_without_git(tmp_path, monkeypatch):
    repo = _git_repo(tmp_path / "repo")
    monkeypatch.setenv("PATH", str(tmp_path))  # git not runnable
    with pytest.raises(ValueError):
        export_spot_check(make_frame(), {}, repo / "s.csv", n=1)


def _tmpl_frames():
    fr = _template_frame()
    notes = Frame(texts={"N1": "x a@b.fi"}, gold={"N1": [sp(2, 8, "EMAIL")]}, conversation_of={"N1": "N1"})
    return fr, notes


def test_predictor_factory_never_sees_held_out_turns():
    fr, notes = _tmpl_frames()
    seen = []

    def factory(dev):
        seen.append(set(dev.texts))
        return regex_predictor

    rep = evaluate_frames(fr, notes, factory)
    held = set(split_by_skeleton(fr).held_out_turns)
    turn_held = set(split_by_skeleton(fr, mode="turn").held_out_turns)
    assert held and turn_held and len(seen) == 2
    assert not (seen[0] & held) and not (seen[1] & turn_held)
    assert rep["split_mode"] == "conversation"
    assert rep["split"]["conversations_in_both_partitions"] == 0
    assert isinstance(rep["turn_held_out"]["conversations_in_both_partitions"], int)


def test_person_twice_not_measured_when_variant_missing():
    fr, notes = _tmpl_frames()
    rep = evaluate_frames(fr, notes, lambda d: regex_predictor)
    assert rep["person_twice_held_out"]["status"] == "not_measured"
    assert rep["person_twice_held_out"]["reason"]
    one = evaluate_frames(fr, notes, lambda d: regex_predictor,
                          person_variants={"controller_gazetteer": lambda d: regex_predictor})
    assert one["person_twice_held_out"]["status"] == "not_measured"


def test_person_twice_records_named_variants():
    fr, notes = _tmpl_frames()
    rep = evaluate_frames(fr, notes, lambda d: regex_predictor,
                          person_variants={"controller_gazetteer": lambda d: regex_predictor,
                                           "dev_lexicon": lambda d: (lambda t: [])})
    p = rep["person_twice_held_out"]
    assert p["status"] == "measured"
    assert p["variants"] == ["controller_gazetteer", "dev_lexicon"]
    assert p["controller_gazetteer"]["support"] == p["dev_lexicon"]["support"] > 0


def test_precision_floor_not_set_pass_and_fail():
    fr, notes = _tmpl_frames()
    unset = evaluate_frames(fr, notes, lambda d: regex_predictor)
    assert unset["precision_floor"] == {"status": "not_set"}
    assert unset["passed"] is None  # unknown is not a pass
    bad = evaluate_frames(fr, notes, lambda d: (lambda t: [sp(0, len(t), "PERSON")]), precision_floor=0.5)
    assert bad["precision_floor"]["status"] == "fail" and bad["passed"] is False
    good = evaluate_frames(fr, notes, lambda d: (lambda t: (
        [sp(t.index("Anna"), len(t), "PERSON")] if "Anna" in t else [])), precision_floor=0.5)
    assert good["precision_floor"]["status"] == "pass" and good["passed"] is True


def test_cli_exit_code_nonzero_below_floor(monkeypatch):
    import pets_release.redaction_eval.__main__ as m

    fr, notes = _tmpl_frames()
    monkeypatch.setattr(m, "load_frames", lambda kit: (fr, notes))
    base = ["--kit", "x", "--predictor", "regex-baseline"]
    assert m.main(base + ["--precision-floor", "0.5"]) == 1  # regex finds nothing -> precision 0
    assert m.main(base) == 2  # floor unset = unknown, never 0
    assert m.main(base + ["--report-only"]) == 0  # explicit opt-in, claims no pass


# ---------- follow-up #40 ----------
def _run(tmp_path, name):
    fr, notes = _tmpl_frames()
    d = tmp_path / name
    rep = evaluate_frames(fr, notes, lambda d_: regex_predictor, out_dir=d, sheet_n=5, precision_floor=0.0)
    return rep, d


def test_report_is_aggregate_only_and_deterministic(tmp_path):
    fr, _ = _tmpl_frames()
    a, da = _run(tmp_path, "a")
    _, db = _run(tmp_path, "b")
    assert (da / "report.json").read_bytes() == (db / "report.json").read_bytes()
    assert (da / "spot_check.csv").read_bytes() == (db / "spot_check.csv").read_bytes()
    blob = (da / "report.json").read_text(encoding="utf-8")
    json.loads(blob)
    for tid, text in fr.texts.items():  # no turn id or text fragment leaks into the report
        assert tid not in blob
        assert text not in blob
    assert a["spot_check_rows"] == 5


def test_spot_check_rows_is_written_count(tmp_path):
    fr = make_frame()
    assert export_spot_check(fr, {}, tmp_path / "s.csv", n=99) == 3


def test_dropped_gold_for_unknown_notes_is_reported():
    import pets_release.redaction_eval.frame as fm

    assert fm.count_dropped_gold({"N1": [sp(0, 1, "EMAIL")], "X": [sp(0, 1, "EMAIL"), sp(2, 3, "EMAIL")]},
                                 {"N1": "t"}) == {"ids": 1, "spans": 2}
    fr, notes = _tmpl_frames()
    notes.gold_dropped = {"ids": 1, "spans": 2}
    rep = evaluate_frames(fr, notes, lambda d: regex_predictor)
    assert rep["zero_shot_frame"]["gold_dropped"] == {"ids": 1, "spans": 2}
