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
BARE_DECIMAL = r"(?<![\w.])\d*\.\d+\b"


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
        return s[1:] == ["count"] or (len(s) == 3 and s[1] in TASKS and s[2] == "floor")
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
            return len(s) >= 4 and s[2] in ("before", "after") and bool(ID.match(".".join(s[3:])))
        if s[1] == "baselines":
            return len(s) >= 4 and s[2] in BASELINES and bool(ID.match(".".join(s[3:])))
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
    assert all(r["value"] == "" for r in rows), "the template ships no numbers; filled values go to numbers.csv"
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
    assert not re.search(BARE_DECIMAL, text), "a bare decimal is typed in the script instead of a placeholder"


def test_no_mislabelled_scope_in_script_or_csv():
    """Keys resolve across all tables (row-weighted / worst table / dataset level), never one table or HEALTH-S1."""
    texts = [(KIT / "pitch-beats.md").read_text(encoding="utf-8"), (KIT / "numbers-template.csv").read_text(encoding="utf-8"),
             (KIT / "numbers.csv").read_text(encoding="utf-8")]
    assert all("ed_visits" not in t for t in texts)
    assert "same scenario" not in texts[0]


def test_bare_decimal_regex_catches_typed_numbers():
    for typed in ("utility 0.8", "kept .75 of it", "is 12.5 here"):
        assert re.search(BARE_DECIMAL, typed), typed
    assert not re.search(BARE_DECIMAL, "see Art. 5(1)(b) and B2-k, H-U4")


def _fill_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("fill_numbers", KIT / "fill_numbers.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_fill_resolves_dotted_ids_and_renders_null_as_dash():
    fill = _fill_module()
    m = {"measured": {
        "privacy": {"status": "measured", "components": [
            {"component": "risk.ed_visits:_records_with_k_5", "before": 1.0, "after": 0.25},
            {"component": "person_k.min", "before": None, "after": 5.0}]},
        "baselines": {"status": "measured", "rows": [
            {"baseline": "B2-k", "metric": "utility.HEALTH-S1", "value": 0.5},
            {"baseline": "B2-k", "metric": "task.H-U6", "value": None}]},
        "utility": {"status": "not_measured", "reason": "x"}}}
    assert fill.resolve(m, "measured.privacy.after.risk.ed_visits:_records_with_k_5") == 0.25
    assert fill.resolve(m, "measured.privacy.before.person_k.min") is None
    assert fill.resolve(m, "measured.baselines.B2-k.utility.HEALTH-S1") == 0.5
    assert fill.resolve(m, "measured.baselines.B2-k.task.H-U6") is None
    assert fill.resolve(m, "measured.utility.after.H-U2") is None
    assert fill.fmt(None, "score_0_1") == "\u2014" and fill.fmt(0.5, "score_0_1") == "0.5000"
    assert fill.fmt(24204.0, "count") == "24204"


def test_every_template_row_has_a_fill_branch():
    fill = _fill_module()
    m = {"release": {"scenario": "S", "recipient": "r"}, "inventory": [], "sacrifices": [],
         "fieldJustifications": [], "gate": {"checks": []}, "exportAssertions": {}, "assertionEvidence": {},
         "measured": {k: {"status": "not_measured"} for k in ("utility", "privacy", "baselines", "search")}}
    for r in csv_rows():
        fill.resolve(m, r["manifest_key_path"])  # KeyError would mean a grammar gap
