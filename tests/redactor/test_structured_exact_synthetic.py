"""Synthetic counterpart of the kit floor test: StructuredPass scored through span_scores(mode="exact").

Runs without the kit. Hand-made synthetic turns only.
"""
from __future__ import annotations

from pets_eval.text import span_scores

from pets_release.redactor import STRUCTURED_LABELS, StructuredPass, Turn, redact_conversation

TEXT = "mail me at jane.doe@example.com please, from 203.0.113.7 now"
EMAIL = "jane.doe@example.com"
IPA = "203.0.113.7"


def _gold(text):
    e, u = text.index(EMAIL), text.index(IPA)
    return {"t1": [{"start": e, "end": e + len(EMAIL), "label": "EMAIL"},
                   {"start": u, "end": u + len(IPA), "label": "IP_ADDRESS"}],
            "t2": []}


def _pred(texts):
    pred = {k: [] for k in texts}
    turns = [Turn(k, v, "customer", str(i)) for i, (k, v) in enumerate(sorted(texts.items()))]
    for s in redact_conversation("c1", turns, passes=[StructuredPass()]).spans:
        pred[s["record_id"]].append({"start": s["start"], "end": s["end"], "label": s["label"]})
    return pred


def test_structured_pass_scores_exactly_on_synthetic_turns():
    texts = {"t1": TEXT, "t2": "nothing sensitive in this turn"}
    sc = span_scores(_gold(TEXT), _pred(texts), mode="exact", labels=STRUCTURED_LABELS)
    assert sc["mode"] == "exact"
    assert sc["per_label"]["EMAIL"]["tp"] == 1 and sc["per_label"]["EMAIL"]["fn"] == 0
    assert sc["per_label"]["IP_ADDRESS"]["tp"] == 1 and sc["per_label"]["IP_ADDRESS"]["fn"] == 0
    assert sc["micro"]["precision"] == 1.0 and sc["micro"]["recall"] == 1.0


def test_exact_scoring_notices_a_missed_span():
    # same gold, but the pass sees a turn with the email removed: recall must drop (the score is not vacuous)
    texts = {"t1": TEXT.replace(EMAIL, "someone"), "t2": "nothing sensitive in this turn"}
    sc = span_scores(_gold(TEXT), _pred(texts), mode="exact", labels=STRUCTURED_LABELS)
    assert sc["per_label"]["EMAIL"]["fn"] == 1
    assert sc["micro"]["recall"] < 1.0
