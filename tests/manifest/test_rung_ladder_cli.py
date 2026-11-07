"""#109 round 2, through the real CLIs (`python -m pets_release.manifest validate`, `pets-release verify`).

The shared manifest validator runs in the writer and in both verify tiers, so these seams see what every consumer
sees. Synthetic manifests built from the committed fixture; no kit rows.

Rule R1: a contract rung is on the ladder if it is on the source column's default policy family OR it is the
policy-enumerated alternative floor for that column (``policy.alt_floors``); anything else still refuses.
  F1 CS-S1 manifest releasing turns.turn_id as the release-scope pseudonym (spec #1: the fallback when
     turn-id-synthetic fails) -> `rung-not-on-ladder`, so the supported fallback is refused
                                                    -> test_turn_id_pseudonym_fallback_is_on_the_ladder
  F2 turns.turn_id at a rung that is neither on its default family nor its alt floor -> must still refuse
                                                    -> test_turn_id_rung_off_both_ladders_refuses

Rule R2: validator diagnostics are content-free: interpolated table/column names go through the module's
safe-name masking, so an identifier-shaped name never reaches the output.
  F3 a released justification whose source column name is card-shaped -> the name appears verbatim in the
     `rung-not-on-ladder` diagnostic of the validator CLI and of `pets-release verify`
                                                    -> test_identifier_shaped_column_name_never_in_output
"""
from __future__ import annotations

import copy
import os
import subprocess
import sys
from pathlib import Path

import pytest

from pets_release.manifest import MANIFEST_FILENAME, canonical_bytes, canonical_digest
from pets_release.manifest.validate import release_scope_id

ROOT = Path(__file__).resolve().parents[2]
CARD_SHAPED = "4000056655665556"  # synthetic test-card-shaped column name (Luhn-valid digits, no real data)


def _env():
    return dict(os.environ, PYTHONPATH=str(ROOT / "src"), PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1", TZ="UTC")


def validate_cli(path):
    return subprocess.run([sys.executable, "-m", "pets_release.manifest", "validate", str(path)], env=_env(),
                          capture_output=True, text=True, encoding="utf-8", check=False)


def verify_cli(path):
    return subprocess.run([sys.executable, "-m", "pets_release", "verify", str(path)], cwd=ROOT, env=_env(),
                          capture_output=True, text=True, encoding="utf-8", check=False)


def _cs_manifest(m, *, turn_id_rung="id.pseudonym", turn_id_form="hex64"):
    """A CS-S1 manifest built from the HEALTH-S1 fixture: conversations.intent kept, and turns.turn_id released
    at ``turn_id_rung`` (default: the spec's release-scope pseudonym fallback, ``cs_s1.turn_id_fallback_plan``)."""
    m = copy.deepcopy(m)
    m["release"]["scenario"] = "CS-S1"
    m["fitFor"] = [{"scenario": "CS-S1", "reason": "test variant"}]
    m["notFitFor"] = [{"scenario": "HEALTH-S1", "reason": "test variant"}]
    del m["exportAssertions"]["quasiIdentifiersBelowK"]
    old = m["assertionEvidence"].pop("quasiIdentifiersBelowK")["check"]
    ev = {"check": "text.health", "version": "1.0.0", "scope": "release", "status": "pass",
          "denominator": {"unit": "turns", "n": 40}, "hits": 0}
    m["exportAssertions"]["healthInText"] = False
    m["assertionEvidence"]["healthInText"] = ev
    m["gate"]["checks"] = sorted([c for c in m["gate"]["checks"] if c["check"] != old] + [dict(ev)],
                                 key=lambda c: c["check"])
    m["bindings"]["checkVersions"] = {c["check"]: c["version"] for c in m["gate"]["checks"]}
    m["bindings"]["lexiconDigests"] = {"health-lexicon": "a" * 64}
    rel, b = m["release"], m["bindings"]
    rel["releaseScopeId"] = release_scope_id(scenario=rel["scenario"], recipient=rel["recipient"],
                                             inputs=b["inputs"], tool_revision=b["toolRevision"])
    tokens = [{"table": "turns", "column": "turn_id", "scope": "release"}] if turn_id_rung == "id.pseudonym" else []
    m["contract"] = {
        "files": {
            "conversations.csv": {"columns": {"intent": {"form": "^[a-z_]{1,32}$", "params": {"rung": "keep"}}},
                                  "required": ["intent"]},
            "turns.csv": {"columns": {"turn_id": {"form": turn_id_form,
                                                  "params": {"nullable": True, "rung": turn_id_rung}}},
                          "required": ["turn_id"]},
        },
        "qi": [], "tokens": tokens}
    m["fieldJustifications"] = [
        {"table": "conversations", "column": "intent", "outputColumn": "intent", "decision": "released",
         "rung": "keep", "floor": "keep", "reason": "CS-U1", "source": "hand"},
        {"table": "turns", "column": "turn_id", "outputColumn": "turn_id", "decision": "released",
         "rung": turn_id_rung, "floor": "id.pseudonym", "reason": "turn-id-synthetic failed", "source": "hand"},
    ]
    m["bindings"]["files"] = {"conversations.csv": "a" * 64, "turns.csv": "b" * 64}
    m["bindings"]["contractDigest"] = canonical_digest(m["contract"])
    return m


def _write(tmp_path, m):
    folder = tmp_path / "rel"
    folder.mkdir()
    (folder / MANIFEST_FILENAME).write_bytes(canonical_bytes(m))
    return folder


def test_turn_id_pseudonym_fallback_is_on_the_ladder(m, tmp_path):
    folder = _write(tmp_path, _cs_manifest(m))
    r = validate_cli(folder / MANIFEST_FILENAME)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip() == "VALID"
    v = verify_cli(folder)  # the manifest stage passes; only the (absent) files can fail later
    assert "manifest:" not in v.stdout, v.stdout + v.stderr


@pytest.mark.parametrize("rung,form", [("ts.hour", r"^\d{4}-\d{2}-\d{2}T\d{2}:00$"), ("text.redacted", "text")])
def test_turn_id_rung_off_both_ladders_refuses(m, tmp_path, rung, form):
    folder = _write(tmp_path, _cs_manifest(m, turn_id_rung=rung, turn_id_form=form))
    r = validate_cli(folder / MANIFEST_FILENAME)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "$.fieldJustifications: turns.turn_id: rung-not-on-ladder" in r.stdout


def test_identifier_shaped_column_name_never_in_output(m, tmp_path):
    cs = _cs_manifest(m)
    fj = next(f for f in cs["fieldJustifications"] if f["table"] == "conversations")
    fj["column"] = CARD_SHAPED  # not a CS-S1 policy column, so it is off every ladder
    cs["fieldJustifications"].sort(key=lambda f: (f["table"], f["column"]))
    folder = _write(tmp_path, cs)
    r = validate_cli(folder / MANIFEST_FILENAME)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "rung-not-on-ladder" in r.stdout
    v = verify_cli(folder)
    assert v.returncode == 1, v.stdout + v.stderr
    assert "rung-not-on-ladder" in v.stdout
    for out in (r.stdout + r.stderr, v.stdout + v.stderr):
        assert CARD_SHAPED not in out
