"""Draft-policy CLI seam: canned provider replies, real validation, no network."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


DICTIONARY = """## health
### health / ed_visits
| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `outcome` | non_sensitive | CATEGORY | | Synthetic outcome |
| `subject` | direct_identifier | PERSON_NAME | | Synthetic identifier |
| `patient_name` | non_sensitive | CATEGORY | | Policy classification remains authoritative |
| `narrative` | free_text | FREE_TEXT | | Synthetic text |
"""
GOOD = {
    "recipient": "Research group",
    "trustLevel": "controlled_research",
    "purposeChecks": [{"id": "H-U2", "reason": "Analyse outcomes"}],
    "fieldsNeeded": [{"table": "ed_visits", "column": "outcome", "detail": "exact", "reason": "Outcome"}],
}


def _draft_cli(make_kit, tmp_path, reply, *, align=False, planted=True):
    kit = make_kit(dictionary=DICTIONARY, scenarios=[{
        "id": "HEALTH-S1", "dataset": "health", "recipient": "Research group",
        "purpose": "Analyse outcomes", "utility_requirements": ["H-U2"],
    }])
    out = tmp_path / "draft.json"
    # A planted earlier draft/temporary file must not bypass validation or be overwritten on refusal.
    temp = tmp_path / "draft.json.tmp"
    if planted:
        out.write_text("previous draft", encoding="utf-8")
        temp.write_text("planted temporary draft", encoding="utf-8")
    args = ["--kit", str(kit), "--allow-network", "--endpoint", "https://provider.invalid/v1",
            "--model", "canned", "--out", str(out)]
    args += ["--align-with", "HEALTH-S1"] if align else [
        "--request", "Researchers analyse outcomes", "--dataset", "health",
    ]
    code = (
        "import json, socket\n"
        "from pets_release.llm.cli import main\n"
        "def canned(url, body, key, timeout):\n"
        "    try:\n"
        "        socket.socket()\n"
        "    except OSError:\n"
        "        pass\n"
        "    else:\n"
        "        raise AssertionError('offline guard missing')\n"
        f"    return {json.dumps({'choices': [{'message': {'content': json.dumps(reply)}}]}).encode()!r}\n"
        f"raise SystemExit(main({args!r}, transport=canned))\n"
    )
    env = {k: v for k, v in os.environ.items() if not k.startswith("PETS_")}
    env.update(PYTHONPATH=str(Path(__file__).resolve().parents[2] / "src"), PETS_OFFLINE="1")
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True,
                            text=True, encoding="utf-8", timeout=30, check=False)
    return result, out, temp


@pytest.mark.parametrize("align", [False, True], ids=["ordinary", "aligned"])
def test_cli_refuses_empty_fields_needed(make_kit, tmp_path, align):
    """Rule: purpose checks without a needs spec are refused, even when alignment succeeds."""
    result, out, temp = _draft_cli(make_kit, tmp_path, dict(GOOD, fieldsNeeded=[]), align=align)
    assert result.returncode == 1, result.stderr
    assert result.stdout == ""
    assert result.stderr == ("pets-release draft-policy: draft refused, nothing written: "
                             "schema violation (minItems) at $.fieldsNeeded\n")
    assert out.read_text(encoding="utf-8") == "previous draft"
    assert temp.read_text(encoding="utf-8") == "planted temporary draft"


@pytest.mark.parametrize("column,detail", [
    ("outcome", "exact"), ("subject", "pseudonymised"),
    ("patient_name", "pseudonymised"), ("narrative", "redacted"),
])
def test_cli_preserves_safe_draft_details(make_kit, tmp_path, column, detail):
    field = {"table": "ed_visits", "column": column, "detail": detail, "reason": "Analysis input"}
    result, out, temp = _draft_cli(make_kit, tmp_path, dict(GOOD, fieldsNeeded=[field]), planted=False)
    assert result.returncode == 0, result.stderr
    draft = json.loads(out.read_text(encoding="utf-8"))
    assert draft["status"] == "draft"
    assert draft["fieldsNeeded"] == [field]
    assert not temp.exists()


def test_cli_refusal_creates_no_draft_files(make_kit, tmp_path):
    result, out, temp = _draft_cli(make_kit, tmp_path, dict(GOOD, fieldsNeeded=[]), planted=False)
    assert result.returncode == 1, result.stderr
    assert result.stdout == ""
    assert not out.exists()
    assert not temp.exists()


@pytest.mark.parametrize("column", ["subject", "patient_name"], ids=["dictionary-role", "policy-classification"])
@pytest.mark.parametrize("detail", ["exact", "generalised", "redacted", "aggregate"])
def test_cli_refuses_unprotected_direct_identifiers(make_kit, tmp_path, column, detail):
    """Rule: a direct identifier can only be requested as a keyed pseudonym, never full detail."""
    field = {"table": "ed_visits", "column": column, "detail": detail, "reason": "PRIVATE_REPLY_MARKER"}
    result, out, temp = _draft_cli(make_kit, tmp_path, dict(GOOD, fieldsNeeded=[field]))
    assert result.returncode == 1, result.stderr
    assert result.stdout == ""
    assert result.stderr == ("pets-release draft-policy: draft refused, nothing written: "
                             "fieldsNeeded[0] requests an unsafe detail for a direct identifier\n")
    assert out.read_text(encoding="utf-8") == "previous draft"
    assert temp.read_text(encoding="utf-8") == "planted temporary draft"


@pytest.mark.parametrize("detail", ["exact", "pseudonymised", "generalised", "aggregate"])
def test_cli_refuses_non_redacted_free_text(make_kit, tmp_path, detail):
    """Rule: free text is requested redacted or omitted, never on another detail ladder."""
    field = {"table": "ed_visits", "column": "narrative", "detail": detail, "reason": "PRIVATE_REPLY_MARKER"}
    result, out, temp = _draft_cli(make_kit, tmp_path, dict(GOOD, fieldsNeeded=[field]))
    assert result.returncode == 1, result.stderr
    assert result.stdout == ""
    assert result.stderr == ("pets-release draft-policy: draft refused, nothing written: "
                             "fieldsNeeded[0] requests an unsafe detail for free text\n")
    assert out.read_text(encoding="utf-8") == "previous draft"
    assert temp.read_text(encoding="utf-8") == "planted temporary draft"
