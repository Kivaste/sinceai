"""#143: per-person k when the adversary also knows the diagnosis, as the ``person-k-diagnosis-known`` residual
risk of the measured run (``pets_release.measure.wire``, the measure CLI seam), on the synthetic minikit.

Only the measurer's scoring (it needs the challenge kit) and the attacker child are stubbed; both run_release
passes, the production ``person_k_values`` and the writer are real.

Rows (trigger -> result):
  declared-QI k >= 5, diagnosis splits off 3 persons -> measured, persons n = the producer.person-k denominator,
                                                       value = 3 / n, description carries the share
  the same inputs run twice                          -> byte-identical entry
  diagnosis column absent from the released table    -> not_measured, reason names the failed measurement
  diagnosis withheld in the release                  -> not_measured, reason "diagnosis not released"
  never a minted value: no measured rate without the measurement (the first row fails if the call is removed)
"""
from __future__ import annotations

import json

import pytest
from run_helpers import TEST_KEY, build_kit, coarse_qis, run_args

from pets_release.manifest import MANIFEST_FILENAME, loads_strict
from pets_release.measure import wire
from pets_release.run import pipeline
from pets_release.verify import current_tool_revision

RISK = "person-k-diagnosis-known"
SPLIT = 3  # persons given a diagnosis of their own (independent literal: the fixture edit below)
BLOCK = {k: {"status": "not_measured", "reason": "stub"} for k in ("utility", "privacy", "baselines", "search",
                                                                    "redaction")}


def _diagnosis_split(folder):
    """``coarse_qis`` (declared-QI k is reached), then one shared diagnosis for every visit except the visits of
    SPLIT persons whose visits all lie in the shared-arrival head: each of them gets a 3-character code of its
    own, so exactly SPLIT persons fall below k once the diagnosis is known."""
    import pandas as pd

    from run_helpers import UNIQUE_TAIL

    coarse_qis(folder)
    p = folder / "ed_visits.csv"
    df = pd.read_csv(p, dtype=str, keep_default_na=False, na_filter=False)
    head = len(df) - UNIQUE_TAIL
    shared = df.at[0, "icd10_primary"]
    df.loc[:, "icd10_primary"] = shared
    tail_persons = set(df.loc[head:, "patient_hetu"])
    chosen = [h for h in sorted(set(df["patient_hetu"])) if h and h not in tail_persons][:SPLIT]
    for i, h in enumerate(chosen):
        df.loc[df["patient_hetu"] == h, "icd10_primary"] = f"Z{i + 10}" + shared[3:]
    df.to_csv(p, index=False, encoding="utf-8", lineterminator="\n")


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("PETS_HMAC_KEY", TEST_KEY)
    kit = build_kit(tmp_path / "kit", edit=_diagnosis_split)
    monkeypatch.setattr(wire, "measure", lambda *a, **k: dict(BLOCK))
    monkeypatch.setattr(wire, "person_k_components", lambda *a, **k: [])
    monkeypatch.setattr(wire, "_person_k_from_release", lambda **k: None)
    monkeypatch.setattr(wire, "_attack", lambda *a, **k: (None, "attacker stubbed in this test"))
    return kit, tmp_path


def _entry(out):
    m = loads_strict((out / MANIFEST_FILENAME).read_bytes())
    found = [r for r in m["residualRisks"] if r["risk"] == RISK]
    assert len(found) == 1
    return m, found[0]


def test_measured_entry_counts_the_persons_the_diagnosis_splits_off(setup):
    kit, tmp = setup
    out = tmp / "rel"
    assert wire.main(run_args(kit, out)[1:]) == 0
    m, e = _entry(out)
    persons = m["assertionEvidence"]["quasiIdentifiersBelowK"]["denominator"]
    assert persons["unit"] == "persons" and persons["n"] > SPLIT
    # a producer-side k measurement, not an attacker rate: never kind linkage (a measured linkage entry means an
    # attacker ran; #138's tests and the UI's "attacker linkage rates" rely on that)
    assert e["kind"] == "note" and e["label"] is None
    rate = e["rate"]
    assert rate["status"] == "measured"
    assert rate["denominator"] == {"unit": "persons", "n": persons["n"]}
    assert rate["value"] == SPLIT / persons["n"]
    assert f"{SPLIT} of {persons['n']} persons" in e["description"]
    assert "k>=5 holds over the declared quasi-identifiers" in e["description"]


def test_rerun_gives_a_byte_identical_entry(setup):
    kit, tmp = setup
    entries = []
    for name in ("a", "b"):
        assert wire.main(run_args(kit, tmp / name)[1:]) == 0
        entries.append(json.dumps(_entry(tmp / name)[1], sort_keys=True, separators=(",", ":")))
    assert entries[0] == entries[1]


def _drop_diagnosis_after_each_pass(monkeypatch, *, column=False, manifest=False):
    """Wrap run_release: after each pass, drop the released diagnosis column from the table file and/or mark the
    diagnosis withheld in the (unsigned-read) manifest, the same way on both passes so the byte guard holds."""
    import pandas as pd

    real = pipeline.run_release

    def run_release(**kw):
        res = real(**kw)
        if res.status == "released":
            path = res.out / MANIFEST_FILENAME
            m = loads_strict(path.read_bytes())
            fj = next(f for f in m["fieldJustifications"] if f["table"] == "ed_visits"
                      and f["column"] == "icd10_primary")
            if column:
                t = res.out / "ed_visits.csv"
                df = pd.read_csv(t, dtype=str, keep_default_na=False, na_filter=False)
                df.drop(columns=[fj["outputColumn"]]).to_csv(t, index=False, encoding="utf-8", lineterminator="\n")
            if manifest:
                fj.update(decision="withheld", rung="withheld", outputColumn=None)
                path.write_text(json.dumps(m), encoding="utf-8")
        return res

    monkeypatch.setattr(pipeline, "run_release", run_release)


@pytest.mark.parametrize("how,reason", [
    ({"column": True}, "per-person k with the diagnosis known: measurement failed"),
    ({"manifest": True}, "diagnosis not released"),
])
def test_missing_diagnosis_is_not_measured_never_a_value(setup, monkeypatch, how, reason):
    kit, tmp = setup
    _drop_diagnosis_after_each_pass(monkeypatch, **how)
    out = tmp / "rel"
    assert wire.main(run_args(kit, out)[1:]) == 0
    _, e = _entry(out)
    rate = e["rate"]
    assert rate["status"] == "not_measured" and set(rate) == {"status", "reason"}
    assert reason in rate["reason"]
    assert "not measured" in e["description"]
