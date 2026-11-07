"""#143: per-person k when the adversary also knows each target's diagnosis, as one ``residualRisks`` entry.

Measure-only: the search, the declared quasi-identifiers and the release are unchanged. The production
``person_k_values`` (the producer.person-k check's own function) runs on the release with the released diagnosis
column added to the contract's QI list, in the same context ``verify --full`` rebuilds (kit + key + release).
Only aggregates leave: persons n, persons below k, and their share. Unidentified units count as persons and as
below k, as in the producer check. Runs inside the release tool (needs the key); never imports the attacker.

Fail closed: a diagnosis not released, or any error in the measurement, gives ``not_measured`` with our own
content-free reason (class name only), never a value.
"""
from __future__ import annotations

from pathlib import Path

RISK = "person-k-diagnosis-known"
DIAGNOSIS = {"HEALTH-S1": ("ed_visits", "icd10_primary")}  # (table, source column); schema names only
SOURCE = ("producer.person-k person_k_values over the contract quasi-identifiers plus the released diagnosis "
          "column, on this release (measure-only)")
_LEAD = ("k>=5 holds over the declared quasi-identifiers (age band, municipality, arrival hour). Diagnosis "
         "(ICD10 code, 3 characters) is treated as a sensitive attribute, not a quasi-identifier; an adversary who "
         "knows a target's diagnosis in addition would find ")
_TAIL = (" below {k}. Per-person k is producer-attested for the recipient; only the key holder can re-verify "
         "it in full mode.")


class DiagnosisKUnavailable(Exception):
    """Our own short, content-free reason."""


def _diagnosis_qi(manifest: dict, scenario: str) -> dict:
    if scenario not in DIAGNOSIS:
        raise DiagnosisKUnavailable(f"no diagnosis attribute defined for {scenario}")
    table, column = DIAGNOSIS[scenario]
    out = [f["outputColumn"] for f in manifest["fieldJustifications"]
           if f["table"] == table and f["column"] == column and f["decision"] == "released"]
    if len(out) != 1 or not isinstance(out[0], str):
        raise DiagnosisKUnavailable("diagnosis not released")
    return {"table": table, "column": out[0], "derived_from": column}


def _counts(*, kit, key_text: str, release: Path) -> tuple[int, int, int]:
    """(persons n, persons below k, k) of ``release`` with the diagnosis known. Raises on any failure."""
    from pets_release.checks.producer.kanon import person_k_values
    from pets_release.manifest import MANIFEST_FILENAME, loads_strict
    from pets_release.pseudonym import MasterKey
    from pets_release.run.context import verify_context

    manifest = loads_strict((release / MANIFEST_FILENAME).read_bytes())
    extra = _diagnosis_qi(manifest, manifest["release"]["scenario"])
    contract = dict(manifest["contract"])
    k = contract.get("k")
    if type(k) is not int or k < 2:
        raise DiagnosisKUnavailable("no k target in the release contract")
    contract["qi"] = [*contract.get("qi", []), extra]
    ctx = verify_context(kit, MasterKey.from_text(key_text), release)
    res = person_k_values(release, contract, ctx)
    values = list(res.per_person.values())
    if type(res.unidentified) is not int or res.unidentified < 0 or not all(type(v) is int and v >= 1
                                                                            for v in values):
        raise DiagnosisKUnavailable("per-person k result malformed")
    n = len(values) + res.unidentified
    if n < 1:
        raise DiagnosisKUnavailable("no persons in the release")
    return n, sum(1 for v in values if v < k) + res.unidentified, k


def risk_entry(*, kit, key_text: str, release: Path) -> dict:
    """The ``person-k-diagnosis-known`` residualRisks entry for ``release``: measured, or not_measured."""
    try:
        n, below, k = _counts(kit=kit, key_text=key_text, release=Path(release))
    except DiagnosisKUnavailable as e:
        why = str(e)
    except Exception as e:  # noqa: BLE001  content-free: the class name only, never the message
        why = f"per-person k with the diagnosis known: measurement failed ({type(e).__name__})"
    else:
        share = below / n
        rate = {"status": "measured", "value": share, "denominator": {"unit": "persons", "n": n}, "source": SOURCE}
        text = f"{share:.1%} ({below} of {n} persons)" + _TAIL.format(k=f"k={k}")
        return _entry(rate, _LEAD + text)
    rate = {"status": "not_measured", "reason": f"{why}; share unknown"[:500]}
    return _entry(rate, _LEAD + "a share (not measured for this release) of persons" + _TAIL.format(k="k"))


def _entry(rate: dict, description: str) -> dict:
    # kind "note", never "linkage": a measured linkage entry means an attacker ran (#138); this is the producer's k
    return {"risk": RISK, "kind": "note", "label": None, "rate": rate, "description": description[:500]}
