"""Helpers for text gate-check tests: build a tiny synthetic release folder.

All rows are hand-made synthetic examples (textbook test identifiers), never kit rows.
Checks are taken from the shared registry and run through the real gate runner.
"""
import csv
from pathlib import Path

import pytest

TURN_COLUMNS = ["turn_id", "conversation_id", "seq", "speaker", "text"]


def text_contract(health_required=True):
    return {
        "files": {
            "turns.csv": {
                "required": ["turn_id", "conversation_id", "seq", "text"],
                "columns": {
                    "turn_id": {"form": "^T[0-9]+$", "params": {}},
                    "conversation_id": {"form": "^C[0-9]+$", "params": {}},
                    "seq": {"form": "integer", "params": {}},
                    "speaker": {"form": "enum", "params": {"values": ["customer", "agent"]}},
                    "text": {"form": "text",
                             "params": {"conversation": "conversation_id", "order": "seq"}},
                },
            }
        },
        "qi": [],
        "tokens": [],
        "healthInTextRequired": health_required,
    }


def write_turns(folder: Path, conversations):
    """conversations: list of lists of (speaker, text); one list per conversation."""
    folder.mkdir(parents=True, exist_ok=True)
    rows = []
    n = 0
    for ci, turns in enumerate(conversations):
        for si, (speaker, text) in enumerate(turns):
            n += 1
            rows.append([f"T{n}", f"C{ci + 1}", str(si + 1), speaker, text])
    with open(folder / "turns.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(TURN_COLUMNS)
        w.writerows(rows)
    return folder


@pytest.fixture
def release(tmp_path):
    def _make(conversations):
        return write_turns(tmp_path / "release", conversations)

    return _make


@pytest.fixture
def contract():
    return text_contract


@pytest.fixture
def registry():
    from pets_release.checks import all_checks

    return {c.name: c for c in all_checks() if c.name.startswith("text.")}


@pytest.fixture
def gate(registry):
    """gate(name, folder, contract, context=None) -> CheckRecord dict, via the real runner.

    The default context is the gate phase (no manifest written yet)."""
    from pets_release.checks import run_checks

    def _run(name, folder, contract, context=None):
        ctx = {"phase": "gate"} if context is None else context
        result = run_checks(folder, contract, ctx, checks=[registry[name]])
        (rec,) = result.records
        return rec.to_dict()

    return _run
