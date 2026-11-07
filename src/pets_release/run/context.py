"""Producer context for the gate and for ``verify --full``: one function, both paths.

The context ticket 11's producer checks read (``source``, ``rowmaps``, ``record_keys``, ``person``, ``joins``,
``identifiers``, ``keys``, ``k``) is derived only from the kit, the master key and the released tables:

* row maps are never read from a file. Every released table of a scenario carries its record key as a
  release-scope keyed pseudonym, so each released row is mapped back to its source record by recomputing
  the pseudonym of every source key (identity, not presence of a file someone could plant). A released
  token with no source record, or a table without its record key, gets no row map, so the k check errors
  (fail closed).
* the gate passes the candidate frames (already in the writer's row order); ``verify --full`` passes the
  tables read from the release folder and the manifest's (validated) release scope ID.

Values stay in memory; nothing here prints or returns a value outside the context dict.
"""
from __future__ import annotations

import functools
from collections.abc import Mapping
from pathlib import Path

import pandas as pd

from pets_release.ladders import PseudonymKeys
from pets_release.pseudonym import RECORD_KEY, MasterKey, Scope, manifest_signing_key, normalise, pseudonymiser_for
from pets_release.pseudonym.keys import recipient_key

DEFAULT_RECIPIENT = "default"  # manifest recipient when no --recipient is given (pseudonyms keyed by the master)

# Schema facts per scenario (names only). record_keys: the column that identifies a source record.
SCENARIO_SPEC = {
    "HEALTH-S1": {
        "person": {"table": "ed_visits", "column": "patient_hetu"},
        "record_keys": {"ed_visits": "visit_id", "lab_results": "lab_id", "clinical_notes": "note_id",
                        "published_weekly_stats": "stat_id"},
        "joins": [
            {"table": "lab_results", "column": "visit_id", "ref_table": "ed_visits", "ref_column": "visit_id"},
            {"table": "clinical_notes", "column": "visit_id", "ref_table": "ed_visits", "ref_column": "visit_id"},
        ],
        # identifiers whose original values must not survive (direct ones come from the policy)
        "technical_identifiers": [("ed_visits", "ambulance_unit"), ("ed_visits", "attending_physician_id"),
                                  ("clinical_notes", "author_staff_id")],
    },
}


class ContextError(Exception):
    """Content-free: the scenario has no producer-context spec."""


def person_normaliser(label: str = RECORD_KEY):
    """The pseudonymiser's own normalisation for the person column's label (person-k keys persons by it).

    The label is the ``id.pseudonym`` label the person column would be released under (spec ``label``,
    default RECORD_KEY, the ladders' default). person-k also refuses if a released person token and this
    identity do not map one-to-one, so a label mismatch cannot pass silently.
    """
    normalise("", label)  # validates the label now (content-free ValueError)
    return functools.partial(normalise, label=label)


def token_keys(master: MasterKey, scope_id: str, recipient: str) -> PseudonymKeys:
    rid = None if recipient == DEFAULT_RECIPIENT else recipient
    return PseudonymKeys(pseudonymiser_for(master, recipient=rid), Scope.release(scope_id))


def _rowmap(stem: str, src: pd.DataFrame, key_col: str, released: pd.DataFrame, keys: PseudonymKeys,
            contract: Mapping) -> pd.DataFrame | None:
    tok_cols = {t["column"] for t in contract.get("tokens", []) if t["table"] == stem}
    if key_col not in released.columns or key_col not in src.columns or key_col not in tok_cols:
        return None
    inverse: dict[str, str] = {}
    for v in src[key_col].tolist():
        if v == "":
            return None
        inverse[keys.token(v, "RECORD_KEY")] = v
    orig = [inverse.get(t) for t in released[key_col].tolist()]
    if any(o is None for o in orig):
        return None
    return pd.DataFrame({"protected_row": [str(i) for i in range(len(orig))], "original_record_id": orig},
                        dtype=str)


def producer_context(*, scenario_id: str, policy, source: Mapping[str, pd.DataFrame], master: MasterKey,
                     scope_id: str, recipient: str, contract: Mapping,
                     released: Mapping[str, pd.DataFrame] | None) -> dict:
    """The producer context. ``released`` None gives a context without row maps (suppression builds its own)."""
    spec = SCENARIO_SPEC.get(scenario_id)
    if spec is None:
        raise ContextError("no producer-context spec for this scenario")
    idents = sorted({*policy.direct_identifiers, *spec["technical_identifiers"]})
    ctx = {
        "source": dict(source),
        "record_keys": dict(spec["record_keys"]),
        "person": {**spec["person"], "normalise": person_normaliser(spec["person"].get("label", RECORD_KEY))},
        "joins": [dict(j) for j in spec["joins"]],
        "identifiers": [{"table": t, "column": c} for t, c in idents if t in source and c in source[t].columns],
        # every key the release could leak, as opaque key objects (producer.key-material scans their forms):
        # master, manifest-signing and, for a non-default recipient, the derived recipient key (#84)
        "keys": [master, manifest_signing_key(master),
                 *([recipient_key(master, recipient)] if recipient != DEFAULT_RECIPIENT else [])],
    }
    if "k" in contract:
        ctx["k"] = contract["k"]
    if released is not None:
        keys = token_keys(master, scope_id, recipient)
        rowmaps = {}
        for stem, df in sorted(released.items()):
            key_col = spec["record_keys"].get(stem)
            rm = _rowmap(stem, source[stem], key_col, df, keys, contract) if key_col and stem in source else None
            if rm is not None:
                rowmaps[stem] = rm
        ctx["rowmaps"] = rowmaps
    return ctx


def verify_context(kit, master: MasterKey, release_dir) -> dict:
    """``verify --full`` context: the same producer context, rebuilt from kit + key + the release folder."""
    from pets_release.manifest import MANIFEST_FILENAME, loads_strict
    from pets_release.policy import get_policy

    release = Path(release_dir)
    m = loads_strict((release / MANIFEST_FILENAME).read_bytes())
    scenario_id = m["release"]["scenario"]
    policy = get_policy(scenario_id)
    source = kit.load_dataset(policy.dataset)
    released = {}
    for name in sorted(m["contract"]["files"]):
        p = release / name
        if p.is_file():
            released[name[:-4]] = pd.read_csv(p, dtype=str, keep_default_na=False, na_filter=False,
                                              encoding="utf-8")
    return producer_context(scenario_id=scenario_id, policy=policy, source=source, master=master,
                            scope_id=m["release"]["releaseScopeId"], recipient=m["release"]["recipient"],
                            contract=m["contract"], released=released)
