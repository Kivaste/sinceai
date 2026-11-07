"""Tests for the redaction measurement harness. Fixtures are small hand-made synthetic rows."""
from __future__ import annotations

import csv
import re
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

    with pytest.raises(AssertionError):
        assert_zero_overlap({"a", "b"}, {"b"})


def test_person_reported_twice():
    gold = {"A": [sp(0, 4, "PERSON")], "B": [sp(0, 4, "PERSON")]}
    gaz = {"A": [sp(0, 4, "PERSON")], "B": [sp(0, 4, "PERSON")]}
    dev = {"A": [sp(0, 4, "PERSON")]}
    r = person_twice(gold, gaz, dev, ["A", "B"])
    assert r["controller_gazetteer"]["recall"] == 1.0
    assert r["dev_only_lexicon"]["recall"] == 0.5
    assert r["controller_gazetteer"]["support"] == 2


def test_precision_floor():
    ok = {"micro_f2_all": {"precision": 0.5}}
    assert check_precision_floor(ok, 0.3) is True
    assert check_precision_floor({"micro_f2_all": {"precision": 0.1}}, 0.3) is False
    assert check_precision_floor({}, 0.3) is False  # missing = fail closed


def test_spot_check_sheet_written_outside_repo(tmp_path):
    fr = make_frame()
    pred = {tid: [] for tid in fr.texts}
    out = export_spot_check(fr, pred, tmp_path / "sheet.csv", n=2, repo_root=Path(__file__).resolve().parents[2])
    rows = list(csv.DictReader(open(out, encoding="utf-8-sig", newline="")))
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
