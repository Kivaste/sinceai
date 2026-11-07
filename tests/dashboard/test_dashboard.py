"""Dashboard tests: seams are render_html/render_csv (manifest dict in) and the CLI main (release folder in)."""

from __future__ import annotations

import copy
import csv
import io
import json
import re
import shutil
from pathlib import Path

import pytest

from pets_release.dashboard import render_csv, render_html
from pets_release.dashboard.cli import main

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "manifest" / "release"


@pytest.fixture()
def manifest() -> dict:
    return json.loads((FIXTURE / "privacy_manifest.json").read_text(encoding="utf-8"))


def _section(html: str, n: int) -> str:
    m = re.search(rf'<section id="item-{n}".*?</section>', html, re.DOTALL)
    assert m, f"section {n} not rendered"
    return m.group(0)


def test_no_external_urls_or_scripts(manifest):
    html = render_html(manifest, files_base=".")
    assert not re.search(r"https?://|//cdn|@import|<script|<link|<img|src=|url\(", html, re.IGNORECASE)


def test_all_five_sections_and_extras_render_from_fixture(manifest):
    html = render_html(manifest, files_base=".")
    for n in range(1, 6):
        assert f'id="item-{n}"' in html
    assert 'id="baselines"' in html
    assert "B0" in html and "B2-k" in html
    assert "H-U8" in html  # a utility task from measured.utility
    assert "age_band" in html  # schema names appear


def test_assertion_scope_shown_for_every_assertion(manifest):
    html = render_html(manifest, files_base=".")
    sec = _section(html, 3)
    for name, ev in manifest["assertionEvidence"].items():
        row = re.search(rf'<tr data-assertion="{name}">(.*?)</tr>', sec, re.DOTALL)
        assert row, name
        assert ev["scope"] in row.group(1)
    assert "producer" in sec and "release" in sec


def test_file_links_are_relative_and_use_manifest_digests(manifest):
    html = render_html(manifest, files_base="rel")
    assert 'href="rel/ed_visits.csv"' in html
    assert manifest["bindings"]["files"]["ed_visits.csv"] in html


@pytest.mark.parametrize(
    "path,item",
    [
        (("inventory",), 1),
        (("pets",), 2),
        (("fieldJustifications",), 2),
        (("contract",), 3),
        (("bindings", "files"), 3),
        (("gate",), 3),
        (("exportAssertions",), 3),
        (("assertionEvidence",), 3),
        (("measured", "utility"), 4),
        (("sacrifices",), 4),
        (("release",), 5),
        (("fitFor",), 5),
        (("notFitFor",), 5),
        (("residualRisks",), 5),
        (("measured", "privacy"), 5),
    ],
)
def test_removing_a_mapped_key_makes_only_that_section_say_missing(manifest, path, item):
    full = render_html(manifest, files_base=".")
    for n in range(1, 6):
        assert 'data-status="complete"' in _section(full, n)
    m = copy.deepcopy(manifest)
    node = m
    for p in path[:-1]:
        node = node[p]
    del node[path[-1]]
    html = render_html(m, files_base=".")
    sec = _section(html, item)
    assert 'data-status="missing"' in sec
    assert "missing" in sec.lower()
    affected = {item} | ({2, 3} if path == ("contract",) else set())  # the spec maps contract to items 2 and 3
    for n in affected:
        assert 'data-status="missing"' in _section(html, n)
    for n in set(range(1, 6)) - affected:
        assert 'data-status="complete"' in _section(html, n)


def test_not_measured_shows_not_yet_measured_and_invents_nothing(manifest):
    m = copy.deepcopy(manifest)
    m["measured"]["utility"] = {"status": "not_measured", "reason": "search not run"}
    html = render_html(m, files_base=".")
    sec = _section(html, 4)
    assert "not yet measured" in sec
    assert "search not run" in sec
    assert "H-U8" not in sec
    assert "0.91" not in sec
    # the fixture has no measured.search: no chart is drawn
    assert "<svg" not in html
    assert "not yet measured" in html


def test_chart_only_when_search_measured(manifest):
    assert "<svg" not in render_html(manifest, files_base=".")
    m = copy.deepcopy(manifest)
    m["measured"]["search"] = {
        "status": "measured", "source": "fixture", "candidates": 9, "accepted": 2, "boundReached": False,
        "points": [
            {"step": 0, "risk": 0.9, "utility": 1.0, "accepted": False},
            {"step": 1, "risk": 0.2, "utility": 0.9, "accepted": True},
        ],
    }
    html = render_html(m, files_base=".")
    assert html.count("<svg") == 1
    assert "xmlns" not in html


def test_html_escapes_manifest_text(manifest):
    m = copy.deepcopy(manifest)
    m["fitFor"][0]["reason"] = "<b>x</b>&"
    html = render_html(m, files_base=".")
    assert "<b>x</b>" not in html and "&lt;b&gt;x&lt;/b&gt;&amp;" in html


def test_csv_has_aggregates_only_with_before_after(manifest):
    rows = list(csv.reader(io.StringIO(render_csv(manifest))))
    assert rows[0] == ["kind", "name", "before", "after"]
    assert ["utility", "H-U8", "1.0000", "0.9100"] in rows
    assert ["privacy", "k_below_5_share", "0.9000", "0.0000"] in rows
    assert ["baseline", "B2-k/utility_mean", "", "0.5000"] in rows
    for r in rows[1:]:
        assert len(r) == 4


def test_csv_omits_unmeasured_sections(manifest):
    m = copy.deepcopy(manifest)
    m["measured"]["utility"] = {"status": "not_measured", "reason": "x"}
    del m["measured"]["baselines"]
    kinds = {r[0] for r in list(csv.reader(io.StringIO(render_csv(m))))[1:]}
    assert kinds == {"privacy"}


def test_render_is_deterministic(manifest):
    assert render_html(manifest, files_base=".") == render_html(manifest, files_base=".")
    assert render_csv(manifest) == render_csv(manifest)


# ---- CLI: real entry point, release folder with marker values in the release tables ----

MARKERS = ("ZZMARKER-alpha-7731", "ZZMARKER-beta-9042")


@pytest.fixture()
def release(tmp_path) -> Path:
    dest = tmp_path / "release"
    shutil.copytree(FIXTURE, dest)
    for f in dest.glob("*.csv"):
        f.write_text("c1,c2\n" + "\n".join(f"{m},{m}" for m in MARKERS) + "\n", encoding="utf-8")
    return dest


def test_cli_writes_html_and_csv_without_release_values(release, tmp_path, capsys):
    out = tmp_path / "out" / "dash.html"
    assert main([str(release), "--out", str(out)]) == 0
    html = out.read_text(encoding="utf-8")
    csv_text = out.with_suffix(".csv").read_text(encoding="utf-8")
    for m in MARKERS:
        assert m not in html and m not in csv_text and m not in capsys.readouterr().out
    assert "<svg" not in html and "H-U8" in csv_text
    # links resolve from the html location back to the release files
    href = re.search(r'href="([^"]*ed_visits\.csv)"', html).group(1)
    assert (out.parent / href).resolve() == (release / "ed_visits.csv").resolve()


def test_cli_dispatcher_runs_dashboard(release, tmp_path):
    from pets_release.cli import main as top

    out = tmp_path / "d.html"
    assert top(["dashboard", str(release), "--out", str(out)]) == 0
    assert out.is_file()


def test_cli_refuses_invalid_manifest_and_writes_nothing(release, tmp_path):
    p = release / "privacy_manifest.json"
    p.write_text(p.read_text(encoding="utf-8").replace('"HEALTH-S1"', '"NOPE"'), encoding="utf-8")
    out = tmp_path / "bad.html"
    assert main([str(release), "--out", str(out)]) == 1
    assert not out.exists() and not out.with_suffix(".csv").exists()


def test_cli_usage_errors(tmp_path):
    assert main([str(tmp_path / "nope")]) == 2
    assert main([]) == 2
