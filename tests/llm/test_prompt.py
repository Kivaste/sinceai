"""The LLM call site sees the request text and the data dictionary only (ADR 0002)."""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pandas as pd
import pytest

from pets_release.llm.dictionary import DataDictionary, DictionaryError, parse_dictionary
from pets_release.llm.prompt import build_messages
from pets_release.llm.vocabulary import vocabulary_for

DICT_MD = """# Data dictionary

## health

### health / ed_visits

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `visit_id` | record_key | RECORD_ID |  | Visit identifier |
| `los_minutes` | sensitive_attribute | HEALTH_DATA | yes | Length of stay in minutes |

### health / lab_results

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `lab_id` | record_key | RECORD_ID |  | Lab result identifier |

## other

### other / things

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `thing` | non_sensitive | CATEGORY |  | A thing |
"""

SRC = Path(__file__).resolve().parents[2] / "src" / "pets_release" / "llm"


def _dictionary() -> DataDictionary:
    return parse_dictionary(DICT_MD, "health")


def test_parse_dictionary_types_tables_and_columns():
    d = _dictionary()
    assert d.dataset == "health"
    assert [t.name for t in d.tables] == ["ed_visits", "lab_results"]
    assert [c.name for c in d.tables[0].columns] == ["visit_id", "los_minutes"]
    assert d.tables[0].columns[1].description == "Length of stay in minutes"


def test_parse_dictionary_unknown_dataset_fails_closed():
    with pytest.raises(DictionaryError):
        parse_dictionary(DICT_MD, "nope")


def test_prompt_contains_request_dictionary_and_vocabulary_only():
    msgs = build_messages("Researchers want length of stay", _dictionary(), vocabulary_for("health"))
    text = json.dumps(msgs)
    assert "Researchers want length of stay" in text
    assert "los_minutes" in text and "lab_results" in text
    assert "H-U2" in text  # analysis vocabulary offered
    assert "CS-U1" not in text  # other dataset's analyses are not offered


def test_no_cell_value_can_reach_the_prompt():
    cells = {"visit_id": "ED25-777001", "los_minutes": "48213"}
    frame = pd.DataFrame([cells])
    # the only inputs the builder accepts are text and the typed dictionary;
    # a table (or a dict of tables) is refused outright
    with pytest.raises(TypeError):
        build_messages("req", frame, vocabulary_for("health"))  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        build_messages("req", {"ed_visits": frame}, vocabulary_for("health"))  # type: ignore[arg-type]
    text = json.dumps(build_messages("req", _dictionary(), vocabulary_for("health")))
    for value in cells.values():
        assert value not in text


def test_llm_package_imports_no_table_libraries():
    banned = ("pandas", "numpy", "pets_eval", "pets_attacker")
    seen = 0
    for path in sorted(SRC.glob("*.py")):
        seen += 1
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for n in names:
                assert n.split(".")[0] not in banned, (path.name, n)
                if n == "pets_release.kit":
                    assert path.name == "cli.py", (path.name, n)  # only the CLI reads the dictionary text
    assert seen >= 4
