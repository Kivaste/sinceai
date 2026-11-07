"""The closed privacy-manifest JSON Schema (draft 2020-12), built as a Python dict.

Every record level has ``additionalProperties: false``. Maps keyed by names (file, table, check, lexicon, PET
parameter) constrain key pattern and value schema instead. The exact export-assertion and evidence key sets are
pinned per scenario through ``allOf``/``if``/``then`` on ``release.scenario``.
"""

from __future__ import annotations

SCHEMA_VERSION = "1"

LABEL_ASSERTIONS = (
    "accountNumbers", "deviceIds", "emails", "ibans", "ipAddresses", "nationalIds", "paymentCards", "phones",
    "plates", "propertyIds", "secrets", "urlsWithTokens", "usernames",
)
_COMMON = LABEL_ASSERTIONS + ("keyMaterial", "rawTimestamps", "reversibleHashes", "rowMaps")
_SCENARIO_ASSERTIONS = {
    "CS-S1": tuple(sorted(_COMMON + ("healthInText",))),
    "HEALTH-S1": tuple(sorted(_COMMON + ("quasiIdentifiersBelowK",))),
}
SCENARIOS = tuple(sorted(_SCENARIO_ASSERTIONS))
ALL_ASSERTIONS = tuple(sorted(set().union(*_SCENARIO_ASSERTIONS.values())))

ROLES = ("direct_identifier", "free_text", "non_sensitive", "quasi_identifier", "record_key", "sensitive_attribute",
         "technical_identifier")
SPAN_LABELS = ("ACCOUNT_NUMBER", "ADDRESS", "AGE", "DATE", "DEVICE_ID", "EMAIL", "HEALTH", "IBAN", "IP_ADDRESS",
               "LICENSE_PLATE", "LOCATION", "NATIONAL_ID", "ORG", "PAYMENT_CARD", "PERSON", "PHONE", "PROPERTY_ID",
               "SECRET", "URL", "USERNAME")
PETS = ("binning", "generalisation", "keyed_pseudonym", "local_suppression", "none", "rounding", "text_redaction",
        "top_coding", "top_n_grouping", "withholding")


def required_assertions(scenario: str) -> tuple[str, ...]:
    """Exact, sorted export-assertion names a manifest for ``scenario`` must carry. KeyError if unknown."""
    return _SCENARIO_ASSERTIONS[scenario]


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": sorted(required or props),
            "additionalProperties": False}


def _ref(name: str) -> dict:
    return {"$ref": f"#/$defs/{name}"}


def _arr(item: dict, min_items: int = 0) -> dict:
    return {"type": "array", "items": item, "minItems": min_items}


def _map(key: str, value: dict, min_props: int = 0) -> dict:
    return {"type": "object", "propertyNames": _ref(key), "additionalProperties": value, "minProperties": min_props}


def _status(value: str) -> dict:
    return {"const": value}


_SCORE = {"type": ["number", "null"]}

_DEFS = {
    "name": {"type": "string", "pattern": "^[A-Za-z0-9_]{1,64}$"},
    "fileName": {"type": "string", "pattern": "^[A-Za-z0-9_]{1,64}\\.csv$"},
    "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
    "checkName": {"type": "string", "pattern": "^[a-z0-9][a-z0-9._-]{0,63}$"},
    "version": {"type": "string", "pattern": "^[0-9]+\\.[0-9]+\\.[0-9]+$"},
    "id": {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9._:+-]{0,63}$"},
    "paramName": {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_]{0,63}$"},
    "text": {"type": "string", "minLength": 1, "maxLength": 500},
    "scope": {"enum": ["producer", "release"]},
    "denominator": _obj({
        "unit": {"enum": ["cells", "files", "persons", "rows", "turns"]},
        "n": {"type": "integer", "minimum": 1},
    }),
    "evidence": _obj({
        "check": _ref("checkName"), "version": _ref("version"), "scope": _ref("scope"),
        "status": _status("pass"), "denominator": _ref("denominator"), "hits": {"const": 0},
    }),
    "gateCheck": _obj({
        "check": _ref("checkName"), "version": _ref("version"), "scope": _ref("scope"),
        "status": _status("pass"), "denominator": _ref("denominator"), "hits": {"type": "integer", "minimum": 0},
    }),
    "params": _map("paramName", {"oneOf": [{"type": "string", "maxLength": 200}, {"type": "number"},
                                           {"type": "boolean"}]}),
    "notMeasured": _obj({"status": _status("not_measured"), "reason": _ref("text")}),
    "notApplicable": _obj({"status": _status("not_applicable"), "reason": _ref("text")}),
    "fit": _obj({"scenario": _ref("id"), "reason": _ref("text")}),
}


def _measured(props: dict) -> dict:
    return {"oneOf": [_ref("notMeasured"), _obj({"status": _status("measured"), "source": _ref("text"), **props})]}


_MEASURED = _obj({
    "utility": _measured({"tasks": _arr(_obj({
        "task": _ref("id"), "status": {"enum": ["error", "not_answerable", "ok"]}, "before": _SCORE, "after": _SCORE,
    }), 1)}),
    "privacy": _measured({"components": _arr(_obj({
        "component": _ref("id"), "before": _SCORE, "after": _SCORE,
    }), 1)}),
    "search": _measured({
        "candidates": {"type": "integer", "minimum": 0},
        "accepted": {"type": "integer", "minimum": 0},
        "boundReached": {"type": "boolean"},
        "points": _arr(_obj({"step": {"type": "integer", "minimum": 0}, "risk": {"type": "number"},
                             "utility": {"type": "number"}, "accepted": {"type": "boolean"}})),
    }),
    "baselines": _measured({"rows": _arr(_obj({
        "baseline": _ref("id"), "metric": _ref("id"), "value": _SCORE,
    }), 1)}),
    "redaction": _measured({
        "mode": {"const": "exact"},
        "frame": _ref("text"),
        "split": _ref("text"),
        "labels": _arr(_obj({
            "label": {"enum": list(SPAN_LABELS)},
            "support": {"type": "integer", "minimum": 0},
            "tp": {"type": "integer", "minimum": 0},
            "fp": {"type": "integer", "minimum": 0},
            "fn": {"type": "integer", "minimum": 0},
            "precision": _SCORE, "recall": _SCORE,
        }), 1),
        "summary": _arr(_obj({"metric": _ref("id"), "value": _SCORE})),
    }),
})

_FIELD_JUSTIFICATION = {
    **_obj({
        "table": _ref("name"), "column": _ref("name"),
        "outputColumn": {"oneOf": [_ref("name"), {"type": "null"}]},
        "decision": {"enum": ["released", "withheld"]},
        "rung": _ref("id"), "floor": _ref("id"), "reason": _ref("text"), "source": {"enum": ["hand", "search"]},
    }),
    "allOf": [
        {"if": {"properties": {"decision": {"const": "withheld"}}, "required": ["decision"]},
         "then": {"properties": {"rung": {"const": "withheld"}, "outputColumn": {"type": "null"}}}},
        {"if": {"properties": {"decision": {"const": "released"}}, "required": ["decision"]},
         "then": {"properties": {"rung": {"not": {"const": "withheld"}}, "outputColumn": {"type": "string"}}}},
    ],
}

_RESIDUAL_RISK = _obj({
    "risk": _ref("id"),
    "kind": {"enum": ["attribute_inference", "linkage", "note", "scorecard_defect", "tamper_limitation",
                      "text_recall"]},
    "label": {"oneOf": [{"enum": list(SPAN_LABELS)}, {"type": "null"}]},
    "rate": {"oneOf": [
        _ref("notMeasured"), _ref("notApplicable"),
        _obj({"status": _status("measured"), "value": {"type": "number", "minimum": 0, "maximum": 1},
              "denominator": _ref("denominator"), "source": _ref("text")}),
    ]},
    "description": _ref("text"),
})


def _scenario_rule(scenario: str) -> dict:
    names = required_assertions(scenario)
    return {
        "if": {"properties": {"release": {"properties": {"scenario": {"const": scenario}},
                                          "required": ["scenario"]}},
               "required": ["release"]},
        "then": {"properties": {
            "exportAssertions": {"type": "object", "properties": {n: {"const": False} for n in names},
                                 "required": list(names), "additionalProperties": False},
            "assertionEvidence": {"type": "object", "properties": {n: _ref("evidence") for n in names},
                                  "required": list(names), "additionalProperties": False},
        }},
    }


MANIFEST_SCHEMA: dict = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "urn:pets-release:privacy-manifest:1",
    "title": "pets-release privacy manifest",
    "$defs": _DEFS,
    **_obj({
        "schemaVersion": {"const": SCHEMA_VERSION},
        "release": _obj({
            "scenario": {"enum": list(SCENARIOS)},
            "recipient": _ref("id"),
            "releaseScopeId": {"type": "string", "pattern": "^[0-9a-f]{16}$"},
            "created": {"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"},
        }),
        "bindings": _obj({
            "files": _map("fileName", _ref("sha256"), 1),
            "inputs": _map("name", _ref("sha256"), 1),
            "toolRevision": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
            "checkVersions": _map("checkName", _ref("version"), 1),
            "lexiconDigests": _map("id", _ref("sha256")),
            "contractDigest": _ref("sha256"),
        }),
        "inventory": _arr(_obj({
            "dataset": _ref("name"), "table": _ref("name"), "column": _ref("name"),
            "role": {"enum": list(ROLES)},
            "subtype": {"type": "string", "pattern": "^[A-Za-z0-9_]{0,64}$"},
            "evidence": _arr(_ref("text"), 1),
        }), 1),
        "pets": _arr(_obj({
            "table": _ref("name"), "column": _ref("name"), "pet": {"enum": list(PETS)}, "params": _ref("params"),
        }), 1),
        "fieldJustifications": _arr(_FIELD_JUSTIFICATION, 1),
        "contract": _obj({
            "files": _map("fileName", _obj({
                "required": _arr(_ref("name")),
                "columns": _map("name", _obj({"form": {"type": "string", "minLength": 1, "maxLength": 300},
                                              "params": _ref("params")}), 1),
            }), 1),
            "qi": _arr(_obj({"table": _ref("name"), "column": _ref("name"), "derived_from": _ref("name")})),
            "tokens": _arr(_obj({"table": _ref("name"), "column": _ref("name"),
                                 "scope": {"enum": ["conversation", "recipient", "release"]}})),
        }),
        "exportAssertions": {"type": "object"},
        "assertionEvidence": {"type": "object"},
        "gate": _obj({"status": _status("pass"), "checks": _arr(_ref("gateCheck"), 1)}),
        "measured": _MEASURED,
        "sacrifices": _arr(_obj({
            "check": _ref("id"), "floor": {"type": "number"}, "before": _SCORE, "after": _SCORE,
            "reason": _ref("text"),
        })),
        "residualRisks": _arr(_RESIDUAL_RISK, 1),
        "fitFor": _arr(_ref("fit"), 1),
        "notFitFor": _arr(_ref("fit")),
        "temporaryState": _obj({
            "mappingTablesPersisted": {"const": False},
            "rowMapsInRelease": {"const": False},
            "buildDirRemoved": {"const": True},
        }),
        "signature": _obj({
            "alg": {"const": "HMAC-SHA256"}, "keyId": _ref("id"), "value": _ref("sha256"),
        }),
    }),
    "allOf": [_scenario_rule(s) for s in SCENARIOS],
}
