"""The masking effect on the redaction metrics goes into ``submission_index.json`` (#30, D37, D40), via the real CLI.

Rule: ``customerServiceEval.maskingEffect`` is always present. Where the kit has labelled customer_service spans
and the conversation-level held-out split is non-empty, the packager replays its own pipeline (redactor, then the
D37 whole-turn masking) on those held-out conversations and records exact-match precision, recall and F2 before
and after masking (aggregates only). Otherwise it is ``{"status": "not_measured", "reason": ...}``. Never omitted,
never assumed.

Failure rows (trigger -> result):
  no labelled spans file in the kit                     -> not_measured, reason names the missing labels
  labelled spans, but the held-out split is empty       -> not_measured, reason names the empty held-out frame
  labelled held-out turn: the redactor finds the email
    exactly but misses the IP; the gate masks it whole  -> measured, masked 1: P/R/F2 1.0/0.5/0.5556 before,
                                                           0/0/0 after (whole-turn spans match no gold span exactly)
  the scorer returns a null metric (undefined)          -> not_measured, reason names the undefined metric
"""
from __future__ import annotations

import csv
import json
import shutil

from sub_helpers import submission

GOLD = "customer_service__turns__text.jsonl"
# Train turns the redactor misses and the gate's ip-addresses check flags (synthetic). Distinct skeletons, so the
# conversation-level split can hold out exactly one of the six single-turn conversations.
EMAIL = "anna.testi@example.com"
IP = "8 . 8 . 8 . 8"
TRAIN = tuple(f"mail {EMAIL} and ip {IP} {w}" for w in
              ("is down again", "is down today", "is slow again", "was down again", "is down now", "went down again"))


def _kit(world, tmp_path, *, train=(), gold=None):
    kit, rel = world
    k2 = tmp_path / "kit"
    shutil.copytree(kit, k2)
    cs = k2 / "data" / "customer_service"
    with (cs / "turns.csv").open("a", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        for i, text in enumerate(train):
            w.writerow([f"tr{i}", f"cr{i}", "1", "customer", "2025-01-04T10:00:00Z", text])
    with (cs / "conversations.csv").open("a", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        for i in range(len(train)):
            w.writerow([f"cr{i}", "u3", "a1", "Agent", "chat", "en", "2025-01-04T10:00:00Z", "refund", "neutral",
                        "4", "1", "100", "1", "train", ""])
    if gold is not None:
        d = k2 / "metadata" / "pii_spans"
        d.mkdir(parents=True, exist_ok=True)
        (d / GOLD).write_text("".join(json.dumps({"record_id": k, "spans": v}) + "\n" for k, v in gold.items()),
                              encoding="utf-8", newline="")
    return k2, rel


def _effect(kit, rel, tmp_path):
    out = tmp_path / "pets_submission"
    p = submission("--out", str(out), "--release", str(rel), "--kit", str(kit))
    assert p.returncode == 0, p.stdout + p.stderr
    idx = json.loads((out / "submission_index.json").read_text("utf-8"))
    return p, idx["customerServiceEval"]["maskingEffect"]


def test_no_labelled_spans_is_recorded_as_not_measured(world, tmp_path):
    kit, rel = world
    p, eff = _effect(kit, rel, tmp_path)
    assert eff["status"] == "not_measured"
    assert "labelled" in eff["reason"]
    assert "masking effect: not measured" in p.stdout


def test_an_empty_held_out_frame_is_recorded_as_not_measured(world, tmp_path):
    kit, rel = _kit(world, tmp_path, gold={"t5": []})  # one train turn: the split holds nothing out
    _p, eff = _effect(kit, rel, tmp_path)
    assert eff["status"] == "not_measured"
    assert "held-out" in eff["reason"]


def test_the_masking_effect_on_held_out_metrics_is_measured(world, tmp_path):
    gold = {f"tr{i}": [{"start": t.index(EMAIL), "end": t.index(EMAIL) + len(EMAIL), "label": "EMAIL"},
                       {"start": t.index(IP), "end": t.index(IP) + len(IP), "label": "IP_ADDRESS"}]
            for i, t in enumerate(TRAIN)}
    gold["t5"] = []
    kit, rel = _kit(world, tmp_path, train=TRAIN, gold=gold)
    p, eff = _effect(kit, rel, tmp_path)
    assert eff["status"] == "measured", eff
    assert eff["turns"] == 1 and eff["maskedTurns"] == 1
    assert eff["before"] == {"precision": 1.0, "recall": 0.5, "f2": 0.5556}
    assert eff["after"] == {"precision": 0.0, "recall": 0.0, "f2": 0.0}
    assert "masking effect: measured" in p.stdout


# ---------- #148 round 2 (Gemini 3.3, D29 "count, plus the effect on turn-level tasks") ----------
# Same held-out frame. Each metric carries its denominator; one that cannot be computed is not_measured + reason.

IDENTIFYING = ["ACCOUNT_NUMBER", "ADDRESS", "DEVICE_ID", "EMAIL", "IBAN", "IP_ADDRESS", "LICENSE_PLATE",
               "NATIONAL_ID", "PAYMENT_CARD", "PERSON", "PHONE", "PROPERTY_ID", "SECRET", "URL", "USERNAME"]
CU1_REASON = ("CS-U1 trains its intent classifier on a whole protected train split and tests on original eval text; "
              "the eval exports carry no train-split text, and the held-out labelled subset is not that training "
              "frame")


def _gold(texts, *values):
    return {f"tr{i}": [{"start": t.index(v), "end": t.index(v) + len(v), "label": lab} for v, lab in values]
            for i, t in enumerate(texts)}


def test_identifying_micro_and_turn_level_impact_are_recorded(world, tmp_path):
    gold = _gold(TRAIN, (EMAIL, "EMAIL"), (IP, "IP_ADDRESS"))
    gold["t5"] = []
    kit, rel = _kit(world, tmp_path, train=TRAIN, gold=gold)
    _p, eff = _effect(kit, rel, tmp_path)
    assert eff["status"] == "measured", eff
    # before: the email found exactly, the IP missed; after: one whole-turn IP_ADDRESS span matching nothing
    assert eff["identifying"] == {
        "labels": IDENTIFYING,
        "before": {"precision": 1.0, "recall": 0.5, "f2": 0.5556, "tp": 1, "fp": 0, "fn": 1, "goldSpans": 2},
        "after": {"precision": 0.0, "recall": 0.0, "f2": 0.0, "tp": 0, "fp": 1, "fn": 2, "goldSpans": 2}}
    assert eff["turnLevel"]["heldOutTurns"] == 1
    assert eff["turnLevel"]["maskedTurns"] == 1
    assert eff["turnLevel"]["maskedShare"] == 1.0
    assert eff["turnLevel"]["tasks"]["CS-U1"] == {"status": "not_measured", "reason": CU1_REASON}
    u5 = eff["turnLevel"]["tasks"]["CS-U5"]  # one held-out turn has no vocabulary common to >= 25 conversations
    assert u5["status"] == "not_measured" and "common vocabulary" in u5["reason"]
    for lab in ("NATIONAL_ID", "PAYMENT_CARD", "IBAN", "SECRET"):  # none in the held-out gold
        assert eff["csS1TargetRecall"][lab] == {"status": "not_measured",
                                                "reason": f"no gold {lab} spans in the held-out frame"}


IBAN = "FI2112345600000785"  # the published Finnish example IBAN (synthetic)
TRAIN_IBAN = tuple(f"iban {IBAN} and ip {IP} {w}" for w in
                   ("is down again", "is down today", "is slow again", "was down again", "is down now",
                    "went down again"))


def test_the_cs_s1_target_recall_is_recorded_per_label(world, tmp_path):
    gold = _gold(TRAIN_IBAN, (IBAN, "IBAN"), (IP, "IP_ADDRESS"))
    gold["t5"] = []
    kit, rel = _kit(world, tmp_path, train=TRAIN_IBAN, gold=gold)
    _p, eff = _effect(kit, rel, tmp_path)
    assert eff["status"] == "measured", eff
    assert eff["csS1TargetRecall"]["IBAN"] == {"gold": 1, "before": {"found": 1, "recall": 1.0},
                                               "after": {"found": 0, "recall": 0.0}}
    assert eff["csS1TargetRecall"]["SECRET"]["status"] == "not_measured"


def test_an_undefined_metric_is_recorded_as_not_measured(world, tmp_path, monkeypatch):
    """`measured` needs every metric to be a number. The pinned scorer gives 0.0 for 0/0 on the kit data, so a null
    cannot be produced through the CLI; the scorer is patched to return one and the production
    cs_eval_outputs is called."""
    from pets_release.kit import Kit
    from pets_release.redaction_eval import scoring
    from pets_release.submission.cs_eval import cs_eval_outputs

    gold = {f"tr{i}": [{"start": t.index(EMAIL), "end": t.index(EMAIL) + len(EMAIL), "label": "EMAIL"}]
            for i, t in enumerate(TRAIN)}
    gold["t5"] = []
    kit, _rel = _kit(world, tmp_path, train=TRAIN, gold=gold)
    monkeypatch.setattr(scoring, "score_frame",
                        lambda g, p: {"micro_f2_all": {"precision": 1.0, "recall": None, "f2": None}})
    _r, _s, counts = cs_eval_outputs(Kit(kit))
    eff = counts["maskingEffect"]
    assert eff["status"] == "not_measured", eff
    assert "undefined" in eff["reason"]
