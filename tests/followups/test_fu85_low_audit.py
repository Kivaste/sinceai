"""Follow-up #85 (low-severity rule-audit items, pass 1). Content-free: aggregate counts and names only."""

from __future__ import annotations

import ast
import hashlib
import json
import secrets
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from pets_release.dashboard import cli as dashboard_cli
from pets_release.kit import FORBIDDEN_DATASETS, Kit, KitError, refuse_forbidden_path
from pets_release.pseudonym import (
    RECORD_KEY,
    MasterKey,
    Scope,
    pseudonymiser_for,
    release_scope_id,
)
from pets_release.redaction_eval.harness import evaluate_frames

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src" / "pets_release"
MINIKIT = REPO / "tests" / "fixtures" / "minikit" / "health"
MANIFEST_RELEASE = REPO / "tests" / "fixtures" / "manifest" / "release"


# ---- 1.5: fixture-based counterpart of the kit-gated visit-key join check -------------------------------------
def test_visit_keys_tokenise_one_to_one_and_keep_the_join_on_fixture():
    tables = ("ed_visits", "lab_results")
    files = {t: MINIKIT / f"{t}.csv" for t in tables}
    digests = {t: hashlib.sha256(p.read_bytes()).hexdigest() for t, p in files.items()}
    rsid = release_scope_id(scenario="HEALTH-S1", recipient=None, input_digests=digests, tool_revision="test")
    p = pseudonymiser_for(MasterKey.from_text(secrets.token_hex(32)))
    scope = Scope.release(rsid)
    raw, tok = {}, {}
    for t, path in files.items():
        col = pd.read_csv(path, dtype=str, usecols=["visit_id"], keep_default_na=False)
        raw[t] = set(col["visit_id"])
        assert raw[t] and "" not in raw[t]
        tok[t] = {p.token(v, label=RECORD_KEY, scope=scope) for v in raw[t]}
        assert len(tok[t]) == len(raw[t])
    lab, ed = raw["lab_results"], raw["ed_visits"]
    assert lab & ed, "fixture must exercise a non-empty join"
    assert len(tok["lab_results"] & tok["ed_visits"]) / len(lab) == len(lab & ed) / len(lab)


# ---- 2.4: dashboard CLI parse exits ---------------------------------------------------------------------------
@pytest.mark.parametrize("code", [None, 0, "", 1, 3, "x"])
def test_dashboard_cli_systemexit_only_zero_is_zero(monkeypatch, code):
    def boom(self, argv=None):
        raise SystemExit(code)

    monkeypatch.setattr(dashboard_cli._Parser, "parse_args", boom)
    expected = 0 if code == 0 else 2
    assert dashboard_cli.main(["x"]) == expected


def test_dashboard_cli_help_still_exits_zero():
    assert dashboard_cli.main(["--help"]) == 0


def test_dashboard_cli_usage_error_exits_two():
    assert dashboard_cli.main([]) == 2


# ---- 3.5 (harness half): spot-check sheet is opt-in ------------------------------------------------------------
def _tmpl_frames():
    import importlib.util

    spec = importlib.util.spec_from_file_location("_re_tests", REPO / "tests" / "redaction_eval" / "test_redaction_eval.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._tmpl_frames()


def test_evaluate_frames_default_writes_no_spot_check(tmp_path):
    from pets_release.redaction_eval.predictors import regex_predictor

    fr, notes = _tmpl_frames()
    out = tmp_path / "o"
    rep = evaluate_frames(fr, notes, lambda d: regex_predictor, out_dir=out)
    assert not (out / "spot_check.csv").exists()
    assert (out / "report.json").is_file()
    assert rep["spot_check_rows"] == 0


def test_cli_spot_check_only_with_explicit_flag(tmp_path, monkeypatch):
    import pets_release.redaction_eval.__main__ as m

    fr, notes = _tmpl_frames()
    monkeypatch.setattr(m, "load_frames", lambda kit: (fr, notes))
    base = ["--kit", "x", "--predictor", "regex-baseline", "--report-only"]
    off, on = tmp_path / "off", tmp_path / "on"
    assert m.main(base + ["--out", str(off)]) == 0
    assert not (off / "spot_check.csv").exists()
    assert m.main(base + ["--out", str(on), "--export-spot-check"]) == 0
    assert (on / "spot_check.csv").is_file()


# ---- 4.1: pii_spans is gold-span data, blocked from Kit access; scorer modules stay isolated ------------------
def _make_kit(tmp_path: Path) -> Path:
    root = tmp_path / "kit"
    (root / "metadata" / "pii_spans").mkdir(parents=True)
    (root / "metadata" / "pii_spans" / "a.jsonl").write_text("{}\n", encoding="utf-8")
    (root / "data" / "pii_spans").mkdir(parents=True)
    (root / "data" / "pii_spans" / "t.csv").write_text("a\n1\n", encoding="utf-8")
    return root


def test_pii_spans_is_a_forbidden_dataset():
    assert "pii_spans" in FORBIDDEN_DATASETS


def test_refuse_forbidden_path_blocks_pii_spans(tmp_path):
    root = _make_kit(tmp_path)
    with pytest.raises(KitError):
        refuse_forbidden_path(root / "metadata" / "pii_spans" / "a.jsonl")


def test_kit_blocks_pii_spans_dataset(tmp_path):
    kit = Kit(_make_kit(tmp_path))
    with pytest.raises(KitError):
        kit.load_table("pii_spans", "t")


def test_kit_resolve_blocks_pii_spans_path(tmp_path):
    root = _make_kit(tmp_path)
    kit = Kit(root)
    with pytest.raises(KitError):
        kit._resolve(root / "metadata" / "pii_spans" / "a.jsonl")


_FORBIDDEN_MODULES = ("pets_release.run", "pets_release.detect", "pets_release.redactor")


def _imports(path: Path, package: str) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")[: len(package.split(".")) - node.level + 1]
                mod = ".".join(base + ([node.module] if node.module else []))
            else:
                mod = node.module or ""
            out.add(mod)
            out.update(f"{mod}.{a.name}" for a in node.names)
    return out


def _closure(start: Path) -> set[str]:
    seen_files: set[Path] = set()
    mods: set[str] = set()
    todo = [start]
    while todo:
        f = todo.pop()
        if f in seen_files:
            continue
        seen_files.add(f)
        rel = f.relative_to(SRC.parent).with_suffix("")
        pkg = ".".join(rel.parts[:-1])
        for m in _imports(f, pkg):
            mods.add(m)
            if m.startswith("pets_release"):
                cand = SRC.parent / Path(*m.split("."))
                for c in (cand.with_suffix(".py"), cand / "__init__.py"):
                    if c.is_file() and c not in seen_files:
                        todo.append(c)
    return mods


@pytest.mark.parametrize("rel", ["kiteval/scorecard.py", "redaction_eval/frame.py"])
def test_scorer_modules_do_not_reach_pipeline_modules(rel):
    mods = _closure(SRC / rel)
    bad = sorted(m for m in mods if any(m == f or m.startswith(f + ".") for f in _FORBIDDEN_MODULES))
    assert bad == []


def test_import_graph_helper_detects_a_planted_import(tmp_path, monkeypatch):
    pkg = tmp_path / "pets_release"
    (pkg / "x").mkdir(parents=True)
    (pkg / "x" / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "x" / "a.py").write_text("from pets_release.detect import cli\n", encoding="utf-8")
    monkeypatch.setitem(globals(), "SRC", pkg)
    mods = _closure(pkg / "x" / "a.py")
    assert any(m.startswith("pets_release.detect") for m in mods)


# ---- real CLI: dashboard exit codes through the actual entry point ----------------------------------------------
def test_dashboard_real_cli_exit_codes(tmp_path):
    env_py = [sys.executable, "-m", "pets_release", "dashboard"]
    ok = subprocess.run([*env_py, str(MANIFEST_RELEASE), "--out", str(tmp_path / "d.html")],
                        capture_output=True, text=True)
    assert ok.returncode == 0
    bad = subprocess.run([*env_py, str(MANIFEST_RELEASE), "--bogus-flag"], capture_output=True, text=True)
    assert bad.returncode == 2
    assert json.dumps(bad.returncode)
