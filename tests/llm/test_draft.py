"""Strict validation of model output: closed schema, then the dictionary and the fixed vocabulary."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from llm_helpers import DICT_MD

from pets_release.llm.dictionary import parse_dictionary
from pets_release.llm.draft import DraftRejected, build_draft, parse_model_output
from pets_release.llm.vocabulary import ANALYSIS_TYPES
from pets_release.policy import get_policy

GOOD = {
    "recipient": "University research group",
    "trustLevel": "controlled_research",
    "purposeChecks": [{"id": "H-U2", "reason": "length of stay"}],
    "fieldsNeeded": [
        {"table": "ed_visits", "column": "los_minutes", "detail": "exact", "reason": "outcome"},
        {"table": "lab_results", "column": "lab_id", "detail": "pseudonymised", "reason": "join"},
    ],
}


def _dict():
    return parse_dictionary(DICT_MD, "health")


def _draft(obj):
    return build_draft(parse_model_output(json.dumps(obj)), _dict(), request="r", model="m")


def test_vocabulary_is_pinned_to_the_packaged_policies():
    policy_ids = {c for s in ("HEALTH-S1", "CS-S1") for c in get_policy(s).purpose_checks}
    assert {a.id for a in ANALYSIS_TYPES} == policy_ids


def test_good_output_becomes_a_draft_marked_as_draft():
    d = _draft(GOOD)
    assert d["status"] == "draft"
    assert d["dataset"] == "health"
    assert d["model"] == "m"
    assert len(d["requestSha256"]) == 64
    assert [c["id"] for c in d["purposeChecks"]] == ["H-U2"]


def test_output_may_arrive_in_a_code_fence():
    text = "```json\n" + json.dumps(GOOD) + "\n```"
    assert parse_model_output(text)["recipient"] == GOOD["recipient"]


def _mut(fn):
    obj = copy.deepcopy(GOOD)
    fn(obj)
    return obj


BAD = {
    "unknown_top_key": _mut(lambda o: o.update(extra=1)),
    "unknown_field_key": _mut(lambda o: o["fieldsNeeded"][0].update(extra=1)),
    "missing_key": _mut(lambda o: o.pop("recipient")),
    "bad_trust": _mut(lambda o: o.update(trustLevel="friends")),
    "bad_detail": _mut(lambda o: o["fieldsNeeded"][0].update(detail="whatever")),
    "empty_checks": _mut(lambda o: o.update(purposeChecks=[])),
    "unknown_analysis": _mut(lambda o: o["purposeChecks"][0].update(id="X-U99")),
    "other_dataset_analysis": _mut(lambda o: o["purposeChecks"][0].update(id="CS-U1")),
    "duplicate_analysis": _mut(lambda o: o["purposeChecks"].append(dict(GOOD["purposeChecks"][0]))),
    "unknown_table": _mut(lambda o: o["fieldsNeeded"][0].update(table="secret_table")),
    "unknown_column": _mut(lambda o: o["fieldsNeeded"][0].update(column="secret_col")),
    "duplicate_field": _mut(lambda o: o["fieldsNeeded"].append(dict(GOOD["fieldsNeeded"][0]))),
    "wrong_type": _mut(lambda o: o.update(recipient=5)),
    "oversized_reason": _mut(lambda o: o["fieldsNeeded"][0].update(reason="x" * 5000)),
}


@pytest.mark.parametrize("name", sorted(BAD))
def test_bad_output_fails_closed_with_a_content_free_error(name):
    with pytest.raises(DraftRejected) as e:
        _draft(BAD[name])
    msg = str(e.value)
    for needle in ("secret_table", "secret_col", "X-U99", "friends", "whatever"):
        assert needle not in msg


@pytest.mark.parametrize("text", ["", "not json", "[]", "{", '{"a": 1} trailing', '{"a": NaN}'])
def test_unparseable_output_is_rejected(text):
    with pytest.raises(DraftRejected):
        parse_model_output(text)
