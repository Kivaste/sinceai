"""Planted original identifiers, their unkeyed hashes and key material are refused.

All values are synthetic and hand-made.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

import pytest

from pets_release.checks.producer import CHECKS

BY_NAME = {c.name: c for c in CHECKS}
ORIGINALS = BY_NAME["original_values"]
HASHES = BY_NAME["reversible_hashes"]
KEYS = BY_NAME["key_material"]

HETUS = ["121285-987X", "010203A123B", "300377-111C"]
NAMES = ["Testi Henkilo", "Mallin Ihminen", "Kuvitteel Lainen"]
KEY = "synthetic-test-key-0123456789-abcdefghij"


@pytest.fixture
def ctx(h):
    return {
        "source": {
            "ed_visits": h.frame(
                {"visit_id": ["V1", "V2", "V3"], "patient_hetu": HETUS, "patient_name": NAMES}
            )
        },
        "identifiers": [
            {"table": "ed_visits", "column": "patient_hetu"},
            {"table": "ed_visits", "column": "patient_name"},
        ],
        "keys": [KEY],
    }


def _token(v):
    return hmac.new(KEY.encode(), v.encode(), hashlib.sha256).hexdigest()


def _clean(h):
    return h.release(
        {
            "ed_visits": {
                "visit_tok": [_token(v) for v in ("V1", "V2", "V3")],
                "patient_tok": [_token(v) for v in HETUS],
                "sex": ["F", "M", "F"],
                "note": ["ok", "vointi hyva", ""],
            }
        }
    )


def _with_cell(h, column, row, value):
    cols = {
        "visit_tok": [_token(v) for v in ("V1", "V2", "V3")],
        "sex": ["F", "M", "F"],
        "note": ["ok", "vointi hyva", ""],
    }
    cols.setdefault(column, ["x", "y", "z"])
    cols[column][row] = value
    return h.release({"ed_visits": cols})


@pytest.mark.parametrize("check", [ORIGINALS, HASHES, KEYS])
def test_clean_release_with_keyed_tokens_passes(h, ctx, check):
    rec = check.run(_clean(h), {}, ctx)
    assert rec["status"] == "pass", rec
    assert rec["hits"] == 0
    assert rec["denominator"]["n"] > 0
    assert rec["scope"] == "producer"


@pytest.mark.parametrize(
    "value",
    [HETUS[0], f"soitti, hetu {HETUS[1]} tarkistettu", HETUS[2].replace("-", ""), NAMES[0].upper()],
)
def test_original_identifier_in_a_cell_is_refused(h, ctx, value):
    rec = ORIGINALS.run(_with_cell(h, "note", 1, value), {}, ctx)
    assert rec["status"] == "fail"
    assert rec["hits"] == 1
    (v,) = rec["violations"]
    assert (v["file"], v["column"], v["locations"], v["severity"]) == ("ed_visits.csv", "note", [1], "high")
    assert value not in json.dumps(rec)


@pytest.mark.parametrize(
    "digest",
    [
        hashlib.sha256(HETUS[0].encode()).hexdigest(),
        hashlib.sha256(HETUS[0].encode()).hexdigest().upper(),
        hashlib.sha1(HETUS[1].encode()).hexdigest(),
        hashlib.md5(NAMES[2].encode()).hexdigest(),
        hashlib.sha256(HETUS[2].replace("-", "").encode()).hexdigest(),
    ],
)
def test_unkeyed_hash_of_original_value_is_refused(h, ctx, digest):
    rec = HASHES.run(_with_cell(h, "patient_tok", 2, digest), {}, ctx)
    assert rec["status"] == "fail"
    assert rec["hits"] == 1
    (v,) = rec["violations"]
    assert (v["column"], v["locations"]) == ("patient_tok", [2])
    assert digest.lower() not in json.dumps(rec).lower()


@pytest.mark.parametrize(
    "form",
    [
        base64.b64encode(KEY.encode()).decode(),
        base64.urlsafe_b64encode(KEY.encode()).decode().rstrip("="),
        KEY.encode().hex(),
        KEY.encode().hex().upper(),
        KEY,
        f"prefix {base64.b64encode(KEY.encode()).decode()} suffix",
    ],
)
def test_key_material_in_a_cell_is_refused(h, ctx, form):
    rec = KEYS.run(_with_cell(h, "note", 0, form), {}, ctx)
    assert rec["status"] == "fail"
    assert rec["hits"] == 1
    (v,) = rec["violations"]
    assert (v["file"], v["column"], v["locations"]) == ("ed_visits.csv", "note", [0])
    assert KEY not in json.dumps(rec)


def test_key_material_in_the_manifest_is_refused(h, ctx):
    rel = _clean(h)
    (rel / "privacy_manifest.json").write_text(
        json.dumps({"x": base64.b64encode(KEY.encode()).decode()}), encoding="utf-8"
    )
    rec = KEYS.run(rel, {}, ctx)
    assert rec["status"] == "fail"
    assert rec["violations"][0]["file"] == "privacy_manifest.json"


def test_original_value_in_the_manifest_is_refused(h, ctx):
    rel = _clean(h)
    (rel / "privacy_manifest.json").write_text(json.dumps({"note": NAMES[1]}), encoding="utf-8")
    rec = ORIGINALS.run(rel, {}, ctx)
    assert rec["status"] == "fail"
    assert rec["violations"][0]["file"] == "privacy_manifest.json"


@pytest.mark.parametrize("check,missing", [(ORIGINALS, "source"), (ORIGINALS, "identifiers"),
                                           (HASHES, "source"), (HASHES, "identifiers"),
                                           (KEYS, "keys")])
def test_not_run_when_source_or_key_unavailable(h, ctx, check, missing):
    rel = _with_cell(h, "note", 0, HETUS[0])
    rec = check.run(rel, {}, {k: v for k, v in ctx.items() if k != missing})
    assert rec["status"] == "not_run"
    assert check.run(rel, {}, None)["status"] == "not_run"
    assert check.run(rel, {}, dict(ctx, **{missing: []}))["status"] == "not_run"


@pytest.mark.parametrize("check", [ORIGINALS, HASHES, KEYS])
def test_missing_release_folder_is_an_error(h, ctx, check):
    assert check.run(h.release({}).parent / "absent", {}, ctx)["status"] == "error"


@pytest.mark.parametrize("check", [ORIGINALS, HASHES, KEYS])
def test_empty_release_folder_is_an_error_not_a_pass(h, ctx, check):
    assert check.run(h.release({}), {}, ctx)["status"] == "error"
