"""Fixture candidate for the writer tests, built from ticket 02's hand-made synthetic fixture (no kit data)."""
from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "fixtures" / "manifest"))

import build_fixture as fx

from pets_release.checks import Outcome, all_checks
from pets_release.checks.registry import Check
from pets_release.manifest import ASSERTION_EVIDENCE, required_assertions
from pets_release.pseudonym import MasterKey
from pets_release.writer import Candidate, ProtectedTable
from pets_release.writer.assemble import NARRATIVE_KEYS

MASTER = MasterKey(fx.FIXTURE_MASTER_KEY)


def _frame(data: bytes) -> pd.DataFrame:
    rows = list(csv.reader(io.StringIO(data.decode("utf-8"), newline="")))
    return pd.DataFrame(rows[1:], columns=rows[0], dtype=object)


def make_candidate(**over) -> Candidate:
    files = fx.tables()
    tables = []
    for name, data in sorted(files.items()):
        frame = _frame(data)
        stem = name[:-4]
        # Reverse the order so the writer's sort is observable; source keys are synthetic labels.
        frame = frame.iloc[::-1].reset_index(drop=True)
        final = tuple(f"src-{stem}-{i}" for i in range(len(frame)))
        tables.append(ProtectedTable(name=name, frame=frame, final=final,
                                     suppressed=frozenset({f"src-{stem}-dropped"})))
    full = fx.manifest(files)
    kw = {"scenario": fx.SCENARIO, "recipient": fx.RECIPIENT, "tables": tuple(tables), "contract": fx.contract(),
              "inputs": dict(fx.INPUTS), "tool_revision": fx.TOOL_REVISION, "created": fx.CREATED,
              "narrative": {k: full[k] for k in NARRATIVE_KEYS}, "lexicon_digests": {}}
    kw.update(over)
    return Candidate(**kw)


def stub(name: str, *, status_outcome=None, scope=None, unit=None, applies_to=()) -> Check:
    """A test-only stand-in for a producer-scope check that needs source context the fixture lacks."""
    ev = {e["check"]: e for e in ASSERTION_EVIDENCE.values()}.get(name, {"scope": "producer", "unit": "cells"})
    out = status_outcome or Outcome(n=10)
    return Check(name=name, version="1.0.0", scope=scope or ev["scope"], unit=unit or ev["unit"],
                 run=lambda release, contract, context: out, applies_to=tuple(applies_to))


def checks_with_stubs(scenario: str = fx.SCENARIO, replace: dict | None = None) -> list[Check]:
    """Full registry; ``producer.*`` checks and unregistered assertion checks replaced by passing stubs."""
    reg = {c.name: c for c in all_checks()}
    for name, c in list(reg.items()):  # ticket 11's checks need source context the fixture does not carry
        if name.startswith("producer."):
            reg[name] = stub(name, scope=c.scope, unit=c.unit)
    for a in required_assertions(scenario):
        ev = ASSERTION_EVIDENCE[a]
        if ev["scope"] == "producer" or ev["check"] not in reg:
            reg[ev["check"]] = stub(ev["check"])
    for name, chk in (replace or {}).items():
        reg[name] = chk
    return sorted(reg.values(), key=lambda c: c.name)


