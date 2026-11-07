"""Build the hand-made fixture release for the manifest, writer, verify and dashboard tickets.

Everything here is synthetic: hand-made rows, schema names and invented counts. Nothing is copied from the kit.

    python tests/fixtures/manifest/build_fixture.py [out_dir]

Without an argument it rewrites ``tests/fixtures/manifest/release/``. Output is byte-deterministic.

The fixture master key below is a published, test-only constant (it signs nothing real). The manifest signing
key is HKDF-SHA256(master, salt=empty, info="manifest-signature", L=32), as the spec pins.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "src"))

from pets_release.ladders import CONTRACT_FORMS  # #109: every released column carries its rung's form
from pets_release.manifest import (
    MANIFEST_FILENAME,
    canonical_bytes,
    canonical_digest,
    compute_signature,
    not_measured,
)

FIXTURE_MASTER_KEY = b"fixture-only-master-key-not-a-secret-0000"
CREATED = "2026-11-07T00:00:00Z"
TOOL_REVISION = "0" * 40
RECIPIENT = "fixture-research-group"
SCENARIO = "HEALTH-S1"


def hkdf_sha256(master: bytes, info: bytes, length: int = 32) -> bytes:
    prk = hmac.new(b"\x00" * 32, master, hashlib.sha256).digest()
    out, block, counter = b"", b"", 1
    while len(out) < length:
        block = hmac.new(prk, block + info + bytes([counter]), hashlib.sha256).digest()
        out += block
        counter += 1
    return out[:length]


def signing_key() -> bytes:
    return hkdf_sha256(FIXTURE_MASTER_KEY, b"manifest-signature")


def _tok(label: str, n: int) -> str:
    return hashlib.sha256(f"fixture-token:{label}:{n}".encode()).hexdigest()


def _csv(header: list[str], rows: list[list[str]]) -> bytes:
    lines = [",".join(header)] + [",".join(r) for r in sorted(rows)]
    return ("\n".join(lines) + "\n").encode("utf-8")


def tables() -> dict[str, bytes]:
    # Two QI classes of five visits each, so per-row k >= 5 holds on (age_band, sex, municipality, arrival_ts).
    classes = [("40-44", "F", "Municipality-A", "2025-03-01T14:00"), ("70-74", "M", "other", "2025-04-01T09:00")]
    visits, labs = [], []
    for i in range(10):
        age, sex, muni, ts = classes[i // 5]
        visit = _tok("visit", i)
        visits.append([visit, age, sex, muni, ts, str(1 + i % 5), "J18", "0" if i % 3 else "1"])
        labs.append([_tok("lab", i), visit, "CRP", str(5 + 7 * i), "mg/L"])
    return {
        "ed_visits.csv": _csv(
            ["visit_id", "age_band", "sex", "municipality", "arrival_ts", "triage", "icd10_primary", "readmit_30d"],
            visits,
        ),
        "lab_results.csv": _csv(["lab_id", "visit_id", "test_code", "value", "unit"], labs),
    }


CHECK_VERSION = "1.0.0"


def _ev(check: str, scope: str, unit: str, n: int) -> dict:
    return {"check": check, "version": CHECK_VERSION, "scope": scope, "status": "pass",
            "denominator": {"unit": unit, "n": n}, "hits": 0}


# Data copy of ticket 04's ASSERTION_CHECKS (origin/ticket/04-gate 87bc8c8); not imported (04 not merged).
ASSERTION_CHECKS = {
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

# HEALTH-S1 assertion -> (scope, denominator unit, n); check name from ASSERTION_CHECKS
_EVIDENCE_SHAPE = {
    "accountNumbers": ("release", "cells", 130),
    "deviceIds": ("release", "cells", 130),
    "emails": ("release", "cells", 130),
    "ibans": ("release", "cells", 130),
    "ipAddresses": ("release", "cells", 130),
    "keyMaterial": ("producer", "cells", 130),
    "nationalIds": ("release", "cells", 130),
    "paymentCards": ("release", "cells", 130),
    "phones": ("release", "cells", 130),
    "plates": ("release", "cells", 130),
    "propertyIds": ("release", "cells", 130),
    "quasiIdentifiersBelowK": ("producer", "persons", 10),
    "rawTimestamps": ("release", "cells", 10),
    "reversibleHashes": ("producer", "cells", 30),
    "rowMaps": ("release", "files", 3),
    "secrets": ("release", "cells", 130),
    "urlsWithTokens": ("release", "cells", 130),
    "usernames": ("release", "cells", 130),
}
EVIDENCE = {a: (ASSERTION_CHECKS[a], *shape) for a, shape in _EVIDENCE_SHAPE.items()}
# Gate checks that back no assertion. contract.* / release.*: ticket 04's names;
# producer.row-k / producer.original-values: ticket 11's (26de63b). Only registered checks may be claimed.
EXTRA_GATE = [
    _ev("contract.columns", "release", "files", 2),
    _ev("contract.files", "release", "files", 2),
    _ev("contract.forms", "release", "cells", 130),
    _ev("release.empty-tables", "release", "files", 2),
    _ev("release.file-digests", "release", "files", 2),
    _ev("release.token-hex64", "release", "cells", 130),
    _ev("producer.row-k", "release", "rows", 10),
    _ev("producer.original-values", "producer", "cells", 130),
]

# Rungs whose contract form is a validator ID (keep/geo.topn: text, id.pseudonym: hex64, num.round: decimal) may
# declare a narrower anchored regex; regex-form rungs (timestamp, age, icd) carry exactly their rung's form (#109).
SHA = "^[0-9a-f]{64}$"


def contract() -> dict:
    return {
        "k": 5,
        "files": {
            "ed_visits.csv": {
                "required": ["age_band", "arrival_ts", "visit_id"],
                "columns": {
                    "age_band": {"form": CONTRACT_FORMS["age.band5"], "params": {"bandYears": 5, "rung": "age.band5"}},
                    "arrival_ts": {"form": CONTRACT_FORMS["ts.month_hour"], "params": {"rung": "ts.month_hour"}},
                    "icd10_primary": {"form": CONTRACT_FORMS["icd.3"], "params": {"rung": "icd.3"}},
                    "municipality": {"form": "^(Municipality-[A-Z]|other)$", "params": {"rung": "geo.topn", "topN": 8}},
                    "readmit_30d": {"form": "^[01]$", "params": {"rung": "keep"}},
                    "sex": {"form": "^[FMX]$", "params": {"rung": "keep"}},
                    "triage": {"form": "^[1-5]$", "params": {"rung": "keep"}},
                    "visit_id": {"form": SHA, "params": {"rung": "id.pseudonym"}},
                },
            },
            "lab_results.csv": {
                "required": ["visit_id"],
                "columns": {
                    "lab_id": {"form": SHA, "params": {"rung": "id.pseudonym"}},
                    "test_code": {"form": "^[A-Z]{2,8}$", "params": {"rung": "keep"}},
                    "unit": {"form": "^[A-Za-z/]{1,8}$", "params": {"rung": "keep"}},
                    "value": {"form": "^[0-9]+$", "params": {"roundTo": 1, "rung": "num.round"}},
                    "visit_id": {"form": SHA, "params": {"rung": "id.pseudonym"}},
                },
            },
        },
        "qi": [
            {"table": "ed_visits", "column": "age_band", "derived_from": "date_of_birth"},
            {"table": "ed_visits", "column": "arrival_ts", "derived_from": "arrival_ts"},
            {"table": "ed_visits", "column": "municipality", "derived_from": "municipality"},
            {"table": "ed_visits", "column": "sex", "derived_from": "sex"},
        ],
        "tokens": [
            {"table": "ed_visits", "column": "visit_id", "scope": "release"},
            {"table": "lab_results", "column": "lab_id", "scope": "release"},
            {"table": "lab_results", "column": "visit_id", "scope": "release"},
        ],
    }


def _inv(table: str, column: str, role: str, subtype: str, evidence: str) -> dict:
    return {"dataset": "health", "table": table, "column": column, "role": role, "subtype": subtype,
            "evidence": [evidence]}


def _fj(table, column, output, rung, floor, reason) -> dict:
    return {"table": table, "column": column, "outputColumn": output,
            "decision": "withheld" if rung == "withheld" else "released",
            "rung": rung, "floor": floor, "reason": reason, "source": "hand"}


INPUTS = {"ed_visits": _tok("input", 1), "lab_results": _tok("input", 2)}


def scope_id(scenario: str, recipient: str, inputs: dict, tool_revision: str) -> str:
    """Copy of the pinned derivation (spec; ticket 06 release_scope_id): first 16 hex of SHA-256 of canonical JSON."""
    payload = {"inputs": inputs, "recipient": recipient, "scenario": scenario, "toolRevision": tool_revision}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def manifest(files: dict[str, bytes]) -> dict:
    con = contract()
    gate_checks = sorted([_ev(*EVIDENCE[a]) for a in EVIDENCE] + EXTRA_GATE, key=lambda c: c["check"])
    m = {
        "schemaVersion": "1",
        "release": {"scenario": SCENARIO, "recipient": RECIPIENT, "releaseScopeId": scope_id(SCENARIO, RECIPIENT, INPUTS, TOOL_REVISION),
                    "created": CREATED},
        "bindings": {
            "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())},
            "inputs": dict(INPUTS),
            "toolRevision": TOOL_REVISION,
            "checkVersions": {c["check"]: c["version"] for c in gate_checks},
            "lexiconDigests": {},
            "contractDigest": canonical_digest(con),
        },
        "inventory": sorted([
            _inv("clinical_notes", "note_text", "free_text", "clinical_note", "column-name token"),
            _inv("ed_visits", "age_band", "quasi_identifier", "age", "derived from date column"),
            _inv("ed_visits", "arrival_ts", "quasi_identifier", "timestamp", "date parse rate"),
            _inv("ed_visits", "municipality", "quasi_identifier", "municipality", "column-name token"),
            _inv("ed_visits", "patient_name", "direct_identifier", "name", "column-name token"),
            _inv("ed_visits", "readmit_30d", "sensitive_attribute", "outcome", "binary domain"),
            _inv("ed_visits", "sex", "quasi_identifier", "sex", "low cardinality"),
            _inv("ed_visits", "visit_id", "record_key", "visit", "unique per row"),
            _inv("lab_results", "lab_id", "record_key", "lab", "unique per row"),
            _inv("lab_results", "visit_id", "technical_identifier", "visit", "foreign-key containment"),
        ], key=lambda r: (r["dataset"], r["table"], r["column"])),
        "pets": [
            {"table": "clinical_notes", "column": "note_text", "pet": "withholding", "params": {}},
            {"table": "ed_visits", "column": "age_band", "pet": "generalisation", "params": {"bandYears": 5}},
            {"table": "ed_visits", "column": "arrival_ts", "pet": "generalisation", "params": {"rung": "month_hour"}},
            {"table": "ed_visits", "column": "municipality", "pet": "top_n_grouping", "params": {"topN": 8}},
            {"table": "ed_visits", "column": "patient_name", "pet": "withholding", "params": {}},
            {"table": "ed_visits", "column": "visit_id", "pet": "keyed_pseudonym", "params": {"scope": "release"}},
            {"table": "lab_results", "column": "lab_id", "pet": "keyed_pseudonym", "params": {"scope": "release"}},
            {"table": "lab_results", "column": "value", "pet": "rounding", "params": {"roundTo": 1}},
            {"table": "lab_results", "column": "visit_id", "pet": "keyed_pseudonym", "params": {"scope": "release"}},
        ],
        "fieldJustifications": [
            _fj("clinical_notes", "note_text", None, "withheld", "withheld", "no purpose check needs it"),
            _fj("ed_visits", "arrival_ts", "arrival_ts", "ts.month_hour", "ts.exact", "H-U8 needs hour of day"),
            _fj("ed_visits", "date_of_birth", "age_band", "age.band5", "age.band5", "H-U6; quasi-identifier"),
            _fj("ed_visits", "icd10_primary", "icd10_primary", "icd.3", "icd.full", "H-U4, H-U7"),
            _fj("ed_visits", "municipality", "municipality", "geo.topn", "geo.full", "H-U4; quasi-identifier"),
            _fj("ed_visits", "patient_name", None, "withheld", "withheld", "direct identifier"),
            _fj("ed_visits", "readmit_30d", "readmit_30d", "keep", "keep", "H-U6"),
            _fj("ed_visits", "sex", "sex", "keep", "keep", "quasi-identifier; search keeps it"),
            _fj("ed_visits", "triage", "triage", "keep", "keep", "H-U2"),
            _fj("ed_visits", "visit_id", "visit_id", "id.pseudonym", "id.pseudonym", "H-U7 join"),
            _fj("lab_results", "lab_id", "lab_id", "id.pseudonym", "id.pseudonym", "record key"),
            _fj("lab_results", "test_code", "test_code", "keep", "keep", "H-U7"),
            _fj("lab_results", "unit", "unit", "keep", "keep", "H-U7"),
            _fj("lab_results", "value", "value", "num.round", "num.exact", "H-U7"),
            _fj("lab_results", "visit_id", "visit_id", "id.pseudonym", "id.pseudonym", "H-U7 join"),
        ],
        "contract": con,
        "exportAssertions": {name: False for name in EVIDENCE},
        "assertionEvidence": {name: _ev(*EVIDENCE[name]) for name in EVIDENCE},
        "gate": {"status": "pass", "checks": gate_checks},
        "measured": {
            "utility": {"status": "measured", "source": "fixture", "tasks": [
                {"task": "H-U2", "status": "ok", "before": 1.0, "after": 0.98},
                {"task": "H-U4", "status": "ok", "before": 1.0, "after": 0.95},
                {"task": "H-U6", "status": "ok", "before": 1.0, "after": 0.97},
                {"task": "H-U7", "status": "ok", "before": 1.0, "after": 0.99},
                {"task": "H-U8", "status": "ok", "before": 1.0, "after": 0.91},
            ]},
            "privacy": {"status": "measured", "source": "fixture", "components": [
                {"component": "k_below_5_share", "before": 0.9, "after": 0.0},
                {"component": "linkage_reid", "before": 0.8, "after": 0.1},
            ]},
            "search": not_measured("hand-picked plan; no search run"),
            "baselines": {"status": "measured", "source": "fixture", "rows": [
                {"baseline": "B0", "metric": "utility_mean", "value": 1.0},
                {"baseline": "B0", "metric": "worst_reid", "value": 0.9},
                {"baseline": "B2", "metric": "utility_mean", "value": 0.75},
                {"baseline": "B2", "metric": "worst_reid", "value": 0.4},
                {"baseline": "B2-k", "metric": "utility_mean", "value": 0.5},
                {"baseline": "B2-k", "metric": "worst_reid", "value": 0.1},
            ]},
            "redaction": not_measured("no free text released"),
        },
        "sacrifices": [],
        "residualRisks": [
            {"risk": "free-text-recall-vacuous", "kind": "note", "label": None,
             "rate": {"status": "not_applicable", "reason": "no free text released"},
             "description": "the scenario's text recall target is vacuous because no text is released"},
            {"risk": "linkage-data-broker", "kind": "linkage", "label": None,
             "rate": not_measured("attacker not run on fixture"),
             "description": "data broker persona"},
            {"risk": "tamper-limitation", "kind": "tamper_limitation", "label": None,
             "rate": {"status": "not_applicable", "reason": "structural"},
             "description": "file digests detect accidents only; only verify --full checks the signature"},
        ],
        "fitFor": [{"scenario": "HEALTH-S1", "reason": "built and gated for this purpose"}],
        "notFitFor": [{"scenario": "HEALTH-S2", "reason": "different recipient and purpose"}],
        "temporaryState": {"mappingTablesPersisted": False, "rowMapsInRelease": False, "buildDirRemoved": True},
    }
    m["signature"] = {"alg": "HMAC-SHA256", "keyId": "fixture-manifest-signature",
                      "value": compute_signature(m, signing_key())}
    return m


def build(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    files = tables()
    for name, data in files.items():
        (out_dir / name).write_bytes(data)
    (out_dir / MANIFEST_FILENAME).write_bytes(canonical_bytes(manifest(files)))


if __name__ == "__main__":
    build(Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "release")
