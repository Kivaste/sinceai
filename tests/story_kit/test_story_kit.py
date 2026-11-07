"""Story kit consistency: every placeholder in the pitch script is a row in the numbers CSV, and every key path
resolves against ticket 02's manifest schema. Content-free: reads only docs/story-kit and the schema."""

from __future__ import annotations

import csv
import re
from pathlib import Path

from pets_release.manifest.schema import ALL_ASSERTIONS, MANIFEST_SCHEMA

KIT = Path(__file__).resolve().parents[2] / "docs" / "story-kit"
PLACEHOLDER = re.compile(r"\{\{([^{}]+)\}\}")
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+-]{0,63}$")
TASKS = {"H-U2", "H-U4", "H-U6", "H-U7", "H-U8"}
BASELINES = {"B0", "B2", "B2-k"}
TOP = MANIFEST_SCHEMA["properties"]


def script_placeholders() -> list[str]:
    return PLACEHOLDER.findall((KIT / "pitch-beats.md").read_text(encoding="utf-8"))


def csv_rows() -> list[dict]:
    with (KIT / "numbers-template.csv").open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def resolves(path: str) -> bool:
    """Grammar of key paths (see README.md); True only if the head exists in the closed schema."""
    s = path.split(".")
    if s[0] not in TOP:
        return False
    if s[0] == "release":
        return len(s) == 2 and s[1] in TOP["release"]["properties"]
    if s[0] == "inventory":
        return s[1:] == ["count"]
    if s[0] == "sacrifices":
        return s[1:] == ["count"]
    if s[0] == "fieldJustifications":
        return len(s) == 3 and s[1] in ("released", "withheld") and s[2] == "count"
    if s[0] == "gate":
        return len(s) == 4 and s[1] == "checks" and s[2] in ("release", "producer") and s[3] == "count"
    if s[0] == "exportAssertions":
        return len(s) == 2 and s[1] in ALL_ASSERTIONS
    if s[0] == "assertionEvidence":
        return (len(s) >= 3 and s[1] in ALL_ASSERTIONS
                and s[2:] in (["hits"], ["denominator", "n"]))
    if s[0] == "measured":
        if len(s) < 3 or s[1] not in TOP["measured"]["properties"]:
            return False
        if s[1] == "utility":
            return len(s) == 4 and s[2] in ("before", "after") and s[3] in TASKS
        if s[1] == "privacy":
            return len(s) == 4 and s[2] in ("before", "after") and bool(ID.match(s[3]))
        if s[1] == "baselines":
            return len(s) == 4 and s[2] in BASELINES and bool(ID.match(s[3]))
        if s[1] == "search":
            return s[2:] == ["candidates"]
    return False


def test_every_placeholder_is_in_the_csv():
    rows = {r["manifest_key_path"] for r in csv_rows()}
    missing = sorted(set(script_placeholders()) - rows)
    assert not missing, f"placeholders missing from numbers-template.csv: {missing}"


def test_every_csv_row_is_in_the_script_and_empty():
    used = set(script_placeholders())
    rows = csv_rows()
    assert [r["manifest_key_path"] for r in rows if r["manifest_key_path"] not in used] == []
    assert all(r["value"] == "" for r in rows), "Part A ships no numbers"
    paths = [r["manifest_key_path"] for r in rows]
    assert len(paths) == len(set(paths)), "duplicate key path rows"
    assert list(rows[0]) == ["beat", "label", "manifest_key_path", "unit", "value"]


def test_every_key_path_exists_in_the_manifest_schema():
    bad = sorted(p for p in set(script_placeholders()) | {r["manifest_key_path"] for r in csv_rows()}
                 if not resolves(p))
    assert not bad, f"key paths not in ticket 02's schema: {bad}"


def test_resolver_rejects_unknown_paths():
    for p in ("measured.utility.after.H-U9", "exportAssertions.directIdentifiers", "nope.x",
              "measured.baselines.B1.utility_mean", "assertionEvidence.paymentCards.status"):
        assert not resolves(p), p


def test_no_digit_literals_outside_placeholders_in_numbers_sections():
    text = PLACEHOLDER.sub("", (KIT / "pitch-beats.md").read_text(encoding="utf-8"))
    assert not re.search(r"\d+(\.\d+)?\s?%", text), "a percentage is typed in the script instead of a placeholder"
