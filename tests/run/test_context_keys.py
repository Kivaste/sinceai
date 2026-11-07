"""#84: the producer context's key material, as ``producer.key-material`` scans it.

Rule: ``producer_context`` hands the key-material check every key the release could leak (master,
manifest-signing key, and the derived recipient key whenever the recipient is not the default), as opaque
``SecretKey`` objects; raw key bytes (``._k``) are read only inside ``pets_release.pseudonym.keys``.

Failure rows (trigger -> result):
  recipient key (hex) planted in a released cell, non-default recipient -> producer.key-material hit
  same, base64 form                                                     -> hit
  master / signing key planted (default recipient)                      -> hit (unchanged coverage)
  ``._k`` read anywhere in src outside pseudonym/keys.py                -> test fails (source rule)
  context ``keys`` holds raw bytes/str instead of key objects            -> test fails
Synthetic rows and a published test-only key; key forms are never printed.
"""
from __future__ import annotations

import base64
import re
from pathlib import Path

import pandas as pd
import pytest

from pets_release.checks import all_checks
from pets_release.policy import get_policy
from pets_release.pseudonym import MasterKey
from pets_release.pseudonym.keys import SecretKey, hkdf_sha256
from pets_release.run.context import producer_context

ROOT = Path(__file__).resolve().parents[2]
KEY_TEXT = "context-keys-test-only-master-key-not-a-secret-0000"  # published test constant
RECIPIENT = "synthetic-recipient"


def _source():
    return {"ed_visits": pd.DataFrame({"visit_id": ["v1", "v2"], "patient_hetu": ["p1", "p2"],
                                       "patient_name": ["Synthetic A", "Synthetic B"]}, dtype=str)}


def _ctx(recipient):
    return producer_context(scenario_id="HEALTH-S1", policy=get_policy("HEALTH-S1"), source=_source(),
                            master=MasterKey.from_text(KEY_TEXT), scope_id="0" * 16, recipient=recipient,
                            contract={"files": {"t.csv": {"columns": {"c": {"form": "text", "params": {}}},
                                                          "required": []}}, "qi": [], "tokens": []},
                            released=None)


def _key_check():
    return next(c for c in all_checks() if c.name == "producer.key-material")


def _release_with(tmp_path, cell):
    i = 0
    while (tmp_path / f"rel{i}").exists():
        i += 1
    rel = tmp_path / f"rel{i}"
    rel.mkdir()
    (rel / "t.csv").write_text(f"c\nplain\n{cell}\n", encoding="utf-8")
    return rel


def _hits(tmp_path, recipient, cell):
    ctx = _ctx(recipient)
    contract = {"files": {"t.csv": {"columns": {"c": {"form": "text", "params": {}}}, "required": []}},
                "qi": [], "tokens": []}
    out = _key_check().run(_release_with(tmp_path, cell), contract, ctx)
    return sum(v.count for v in out.violations)


def _recipient_bytes():
    return hkdf_sha256(KEY_TEXT.encode("utf-8"), RECIPIENT.encode("utf-8"))


def test_recipient_key_hex_in_cell_is_a_hit(tmp_path):
    assert _hits(tmp_path, RECIPIENT, _recipient_bytes().hex()) == 1


def test_recipient_key_base64_in_cell_is_a_hit(tmp_path):
    assert _hits(tmp_path, RECIPIENT, "k=" + base64.b64encode(_recipient_bytes()).decode()) == 1


def test_master_and_signing_key_still_hits(tmp_path):
    signing = hkdf_sha256(KEY_TEXT.encode("utf-8"), b"manifest-signature")
    assert _hits(tmp_path, "default", KEY_TEXT) == 1
    assert _hits(tmp_path, "default", signing.hex().upper()) == 1


def test_clean_cell_no_hit(tmp_path):
    assert _hits(tmp_path, RECIPIENT, "nothing here") == 0


@pytest.mark.parametrize("recipient", ["default", RECIPIENT])
def test_context_keys_are_opaque_key_objects(recipient):
    keys = _ctx(recipient)["keys"]
    assert keys and all(isinstance(k, SecretKey) for k in keys)
    assert len(keys) == (3 if recipient != "default" else 2)


def test_no_raw_key_bytes_read_outside_keys_module():
    offenders = []
    for p in sorted((ROOT / "src").rglob("*.py")):
        if p.as_posix().endswith("pets_release/pseudonym/keys.py"):
            continue
        if re.search(r"\._k\b", p.read_text(encoding="utf-8")):
            offenders.append(p.relative_to(ROOT).as_posix())
    assert offenders == []
