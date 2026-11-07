"""Follow-up #51: PET lookup by output column, chart overplot, one number formatter, extra coverage."""

from __future__ import annotations

import copy
import csv
import io
import json
import re
from pathlib import Path

import pytest

from pets_release.dashboard import render_csv, render_html

FIXTURE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "manifest" / "release"
DASH = "—"


@pytest.fixture()
def manifest() -> dict:
    return json.loads((FIXTURE / "privacy_manifest.json").read_text(encoding="utf-8"))


def _section(html: str, n) -> str:
    m = re.search(rf'<section id="{n}".*?</section>', html, re.DOTALL)
    assert m, f"section {n} not rendered"
    return m.group(0)


def _item(html: str, n: int) -> str:
    return _section(html, f"item-{n}")


def _search(points):
    return {"status": "measured", "source": "fixture", "candidates": len(points), "accepted": 1,
            "boundReached": False, "points": points}


def test_pet_found_for_derived_column_by_output_name(manifest):
    s2 = _item(render_html(manifest), 2)
    row = re.search(r"<tr><td>ed_visits\.date_of_birth</td>.*?</tr>", s2, re.DOTALL).group(0)
    assert "generalisation" in row and "bandYears=5" in row


def test_accepted_point_drawn_after_rejected_at_same_coordinates(manifest):
    m = copy.deepcopy(manifest)
    m["measured"]["search"] = _search([
        {"step": 0, "risk": 0.2, "utility": 0.9, "accepted": True},
        {"step": 1, "risk": 0.2, "utility": 0.9, "accepted": False},
        {"step": 2, "risk": 0.5, "utility": 0.95, "accepted": False},
    ])
    circles = re.findall(r"<circle[^>]*>", render_html(m))
    assert len(circles) == 3
    assert [c for c in circles if 'fill="#14365d"' in c] == circles[-1:]


@pytest.mark.parametrize("v,text", [(0.9996, "0.9996"), (1.0, "1.0000"), (0.00001, "<0.0001"), (0, "0.0000"),
                                    (0.5, "0.5000")])
def test_one_formatter_fixed_decimals_no_scientific(manifest, v, text):
    m = copy.deepcopy(manifest)
    task = m["measured"]["utility"]["tasks"][0]
    task["before"] = task["after"] = v
    html = render_html(m)
    assert f"<td>{text.replace('<', '&lt;')}</td>" in _item(html, 4)
    assert not re.search(r"\de-0\d", html)
    rows = [r for r in csv.reader(io.StringIO(render_csv(m))) if r[:2] == ["utility", task["task"]]]
    assert rows[0][2:] == [text, text]


def test_null_scores_render_as_dash_in_html_and_csv_never_none(manifest):
    m = copy.deepcopy(manifest)
    t = m["measured"]["utility"]["tasks"][0]
    t["before"] = t["after"] = None
    m["measured"]["privacy"]["components"][0]["after"] = None
    m["measured"]["baselines"]["rows"][0]["value"] = None
    html, text = render_html(m), render_csv(m)
    assert "None" not in html and "None" not in text
    assert f"<td>{DASH}</td>" in _item(html, 4)
    assert ["utility", t["task"], DASH, DASH] in list(csv.reader(io.StringIO(text)))


def test_residual_rate_uses_formatter_and_null(manifest):
    m = copy.deepcopy(manifest)
    m["residualRisks"][0]["rate"] = {"status": "measured", "value": 0.00001,
                                     "denominator": {"n": 7, "unit": "rows"}}
    assert "&lt;0.0001 (n=7 rows)" in _item(render_html(m), 5)
    m["residualRisks"][0]["rate"]["value"] = None
    s5 = _item(render_html(m), 5)
    assert "None" not in s5 and f"{DASH} (n=7 rows)" in s5


def test_header_for_missing_release_says_missing(manifest):
    m = copy.deepcopy(manifest)
    del m["release"]
    assert "Scenario missing" in render_html(m)


@pytest.mark.parametrize("key,sec", [("baselines", "baselines"), ("search", "chart")])
def test_missing_extra_sections(manifest, key, sec):
    m = copy.deepcopy(manifest)
    m["measured"]["search"] = _search([{"step": 0, "risk": 0.2, "utility": 0.9, "accepted": True}])
    assert 'data-status="complete"' in _section(render_html(m), sec)[:200]
    del m["measured"][key]
    html = render_html(m)
    assert 'data-status="missing"' in _section(html, sec)[:200]
    assert f'data-key="measured.{key}"' in html


def test_contract_removal_makes_section_two_missing_with_key_note(manifest):
    m = copy.deepcopy(manifest)
    del m["contract"]
    s2 = _item(render_html(m), 2)
    assert 'data-status="missing"' in s2 and 'data-key="contract"' in s2


def test_item3_renders_contract_qi_and_tokens(manifest):
    s3 = _item(render_html(manifest), 3)
    assert "Quasi-identifiers" in s3 and "Tokens" in s3
    assert "<td>ed_visits</td><td>age_band</td><td>date_of_birth</td>" in s3
    assert "<td>lab_results</td><td>lab_id</td><td>release</td>" in s3
