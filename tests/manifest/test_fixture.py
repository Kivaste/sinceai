"""The committed fixture release is coherent: regenerable, digest-bound, signed, contract-conformant, k >= 5."""

import hashlib
import hmac
import json
import re
from pathlib import Path

import pandas as pd
import pytest
from jsonschema import Draft202012Validator

from pets_release.manifest import (
    ALL_ASSERTIONS,
    MANIFEST_FILENAME,
    MANIFEST_SCHEMA,
    compute_signature,
    signing_bytes,
    validate_manifest_file,
)

RELEASE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "manifest" / "release"


# Written-out copy of ticket 04's ASSERTION_CHECKS (src/pets_release/checks/registry.py at origin/ticket/04-gate
# 87bc8c8). Once 04 merges, test_matches_ticket_04_registry_when_merged compares against the real constant.
TICKET_04_ASSERTION_CHECKS = {
    "accountNumbers": "rescan.account-numbers",
    "deviceIds": "rescan.device-ids",
    "emails": "rescan.emails",
    "healthInText": "text.health",
    "ibans": "rescan.ibans",
    "ipAddresses": "rescan.ip-addresses",
    "keyMaterial": "producer.key-material",
    "nationalIds": "rescan.national-ids",
    "paymentCards": "rescan.payment-cards",
    "phones": "rescan.phones",
    "plates": "rescan.plates",
    "propertyIds": "rescan.property-ids",
    "quasiIdentifiersBelowK": "producer.person-k",
    "rawTimestamps": "rescan.raw-timestamps",
    "reversibleHashes": "producer.unkeyed-hashes",
    "rowMaps": "release.row-maps",
    "secrets": "rescan.secrets",
    "urlsWithTokens": "rescan.urls-with-tokens",
    "usernames": "rescan.usernames",
}


def test_fixture_evidence_uses_ticket_04_check_names_and_versions():
    m = manifest()
    names = {a: ev["check"] for a, ev in m["assertionEvidence"].items()}
    assert names == {a: TICKET_04_ASSERTION_CHECKS[a] for a in m["exportAssertions"]}
    assert {ev["version"] for ev in m["assertionEvidence"].values()} == {"1.0.0"}
    assert set(TICKET_04_ASSERTION_CHECKS) == set(ALL_ASSERTIONS)


def test_matches_ticket_04_registry_when_merged():
    checks = pytest.importorskip("pets_release.checks", reason="ticket 04 not merged: not run, not a pass")
    ASSERTION_CHECKS = checks.ASSERTION_CHECKS

    assert ASSERTION_CHECKS == TICKET_04_ASSERTION_CHECKS


def test_schema_is_a_valid_2020_12_schema():
    Draft202012Validator.check_schema(MANIFEST_SCHEMA)


def manifest():
    return json.loads((RELEASE_DIR / MANIFEST_FILENAME).read_bytes())


def test_committed_fixture_validates():
    assert validate_manifest_file(RELEASE_DIR) == []


def test_committed_fixture_is_byte_identical_to_builder_output(builder, tmp_path):
    builder.build(tmp_path)
    committed = sorted(p.name for p in RELEASE_DIR.iterdir())
    assert committed == sorted(p.name for p in tmp_path.iterdir())
    for name in committed:
        assert (RELEASE_DIR / name).read_bytes() == (tmp_path / name).read_bytes(), name


def test_release_folder_holds_only_bound_tables_and_manifest():
    m = manifest()
    names = sorted(p.name for p in RELEASE_DIR.iterdir())
    assert names == sorted([*m["bindings"]["files"], MANIFEST_FILENAME])
    for name, digest in m["bindings"]["files"].items():
        assert hashlib.sha256((RELEASE_DIR / name).read_bytes()).hexdigest() == digest


def test_signature_matches_fixture_signing_key(builder):
    m = manifest()
    assert m["signature"]["value"] == compute_signature(m, builder.signing_key())
    wrong = hmac.new(b"other-key", signing_bytes(m), hashlib.sha256).hexdigest()
    assert m["signature"]["value"] != wrong


def test_every_cell_matches_its_contract_form_and_required_columns_exist():
    m = manifest()
    for name, spec in m["contract"]["files"].items():
        df = pd.read_csv(RELEASE_DIR / name, dtype=str, keep_default_na=False)
        assert set(df.columns) <= set(spec["columns"]) and set(spec["required"]) <= set(df.columns)
        assert len(df) > 0
        for col in df.columns:
            form = re.compile(spec["columns"][col]["form"])
            assert all(form.fullmatch(v) for v in df[col]), (name, col)


def test_per_row_k_at_least_5_on_released_qis():
    m = manifest()
    by_table = {}
    for q in m["contract"]["qi"]:
        by_table.setdefault(q["table"], []).append(q["column"])
    for table, cols in by_table.items():
        df = pd.read_csv(RELEASE_DIR / f"{table}.csv", dtype=str, keep_default_na=False)
        assert df.groupby(cols).size().min() >= 5


def test_manifest_strings_are_names_digests_or_short_text():
    # Content-free heuristic: no long digit runs outside 64/40/16-hex digests.
    raw = (RELEASE_DIR / MANIFEST_FILENAME).read_text(encoding="utf-8")
    stripped = re.sub(r"\b[0-9a-f]{64}\b|\b[0-9a-f]{40}\b|\b[0-9a-f]{16}\b", "", raw)
    assert not re.search(r"[0-9]{5,}", stripped)
