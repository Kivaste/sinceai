"""Model output -> DRAFT scenario policy. Closed schema first, then the dictionary and the vocabulary.

Every failure is `DraftRejected` with a content-free message: a schema keyword and a path of known keys
or list indices, never a value the model produced.
"""
from __future__ import annotations

import hashlib
import json
import re

from jsonschema import Draft202012Validator

from pets_release.llm.dictionary import DataDictionary
from pets_release.llm.vocabulary import DETAIL_LEVELS, TRUST_LEVELS, vocabulary_for

SCHEMA_VERSION = "1"
_TEXT = {"type": "string", "minLength": 1, "maxLength": 300}

MODEL_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["recipient", "trustLevel", "purposeChecks", "fieldsNeeded"],
    "properties": {
        "recipient": _TEXT,
        "trustLevel": {"enum": list(TRUST_LEVELS)},
        "purposeChecks": {
            "type": "array",
            "minItems": 1,
            "maxItems": 32,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "reason"],
                "properties": {"id": _TEXT, "reason": _TEXT},
            },
        },
        "fieldsNeeded": {
            "type": "array",
            "maxItems": 400,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["table", "column", "detail", "reason"],
                "properties": {
                    "table": _TEXT,
                    "column": _TEXT,
                    "detail": {"enum": list(DETAIL_LEVELS)},
                    "reason": _TEXT,
                },
            },
        },
    },
}

DRAFT_SCHEMA = {
    **MODEL_OUTPUT_SCHEMA,
    "required": sorted(
        [*MODEL_OUTPUT_SCHEMA["required"], "schemaVersion", "status", "dataset", "requestSha256", "model"]
    ),
    "properties": {
        **MODEL_OUTPUT_SCHEMA["properties"],
        "schemaVersion": {"const": SCHEMA_VERSION},
        "status": {"const": "draft"},
        "dataset": _TEXT,
        "requestSha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "model": {"type": "string", "maxLength": 200},
    },
}


class DraftRejected(ValueError):
    """The model output is not an acceptable draft. The message never contains model-produced text."""


_FENCE = re.compile(r"^\s*```[A-Za-z]*\s*\n(.*?)\n\s*```\s*$", re.DOTALL)


def _no_dupes(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise DraftRejected("model output has a duplicate key")
        out[k] = v
    return out


def _bad_constant(_name):
    raise DraftRejected("model output is not strict JSON")


def parse_model_output(text: str) -> dict:
    if not isinstance(text, str) or not text.strip():
        raise DraftRejected("model output is empty")
    m = _FENCE.match(text)
    body = m.group(1) if m else text
    try:
        obj = json.loads(body, object_pairs_hook=_no_dupes, parse_constant=_bad_constant)
    except json.JSONDecodeError:
        raise DraftRejected("model output is not valid JSON") from None
    if not isinstance(obj, dict):
        raise DraftRejected("model output is not a JSON object")
    return obj


def _path(error) -> str:
    return "$" + "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in error.absolute_path)


def _check_schema(schema: dict, obj: dict) -> None:
    errors = sorted(Draft202012Validator(schema).iter_errors(obj), key=lambda e: (list(map(str, e.absolute_path)), e.validator))
    if errors:
        e = errors[0]
        raise DraftRejected(f"schema violation ({e.validator}) at {_path(e)}")


def build_draft(output: dict, dictionary: DataDictionary, *, request: str, model: str) -> dict:
    """Validate parsed model output and return the DRAFT record (status "draft", for human approval)."""
    _check_schema(MODEL_OUTPUT_SCHEMA, output)
    allowed = {a.id for a in vocabulary_for(dictionary.dataset)}
    seen_checks: set[str] = set()
    for i, pc in enumerate(output["purposeChecks"]):
        if pc["id"] not in allowed:
            raise DraftRejected(f"purposeChecks[{i}] is not in the analysis vocabulary for this dataset")
        if pc["id"] in seen_checks:
            raise DraftRejected(f"purposeChecks[{i}] repeats an analysis type")
        seen_checks.add(pc["id"])
    known = dictionary.columns()
    seen_fields: set[tuple[str, str]] = set()
    for i, f in enumerate(output["fieldsNeeded"]):
        key = (f["table"], f["column"])
        if key not in known:
            raise DraftRejected(f"fieldsNeeded[{i}] names a table or column that is not in the data dictionary")
        if key in seen_fields:
            raise DraftRejected(f"fieldsNeeded[{i}] repeats a field")
        seen_fields.add(key)
    draft = {
        **output,
        "purposeChecks": sorted(output["purposeChecks"], key=lambda c: c["id"]),
        "fieldsNeeded": sorted(output["fieldsNeeded"], key=lambda f: (f["table"], f["column"])),
        "schemaVersion": SCHEMA_VERSION,
        "status": "draft",
        "dataset": dictionary.dataset,
        "requestSha256": hashlib.sha256(request.encode("utf-8")).hexdigest(),
        "model": model,
    }
    _check_schema(DRAFT_SCHEMA, draft)
    return draft
