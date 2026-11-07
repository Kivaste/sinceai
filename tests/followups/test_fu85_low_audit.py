"""Follow-up #85 (low-severity rule-audit items, pass 1). Content-free: aggregate counts and names only."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from pets_release.dashboard import cli as dashboard_cli
from pets_release.kit import FORBIDDEN_DATASETS, Kit, KitError, refuse_forbidden_path
from pets_release.redaction_eval.harness import evaluate_frames

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src" / "pets_release"
MANIFEST_RELEASE = REPO / "tests" / "fixtures" / "manifest" / "release"


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
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
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
        # Importing a module runs every parent package's __init__.py first.
        for i in range(1, len(rel.parts)):
            init = SRC.parent.joinpath(*rel.parts[:i], "__init__.py")
            if init.is_file() and init not in seen_files:
                todo.append(init)
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


def test_import_graph_helper_detects_forbidden_import_in_parent_init(tmp_path, monkeypatch):
    pkg = tmp_path / "pets_release"
    (pkg / "x" / "helper").mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "x" / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "x" / "helper" / "__init__.py").write_text("from pets_release.run import go\n", encoding="utf-8")
    (pkg / "x" / "helper" / "api.py").write_text("", encoding="utf-8")
    (pkg / "x" / "scorer.py").write_text("import pets_release.x.helper.api\n", encoding="utf-8")
    monkeypatch.setitem(globals(), "SRC", pkg)
    mods = _closure(pkg / "x" / "scorer.py")
    assert any(m == "pets_release.run" or m.startswith("pets_release.run.") for m in mods)


def test_import_graph_helper_detects_forbidden_import_in_start_files_parent_init(tmp_path, monkeypatch):
    pkg = tmp_path / "pets_release"
    (pkg / "x").mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "x" / "__init__.py").write_text("import pets_release.detect\n", encoding="utf-8")
    (pkg / "x" / "scorer.py").write_text("", encoding="utf-8")
    monkeypatch.setitem(globals(), "SRC", pkg)
    mods = _closure(pkg / "x" / "scorer.py")
    assert "pets_release.detect" in mods


# ---- real CLI: dashboard exit codes through the actual entry point ----------------------------------------------
def test_dashboard_real_cli_exit_codes(tmp_path):
    env_py = [sys.executable, "-m", "pets_release", "dashboard"]
    ok = subprocess.run([*env_py, str(MANIFEST_RELEASE), "--out", str(tmp_path / "d.html")],
                        capture_output=True, text=True)
    assert ok.returncode == 0
    bad = subprocess.run([*env_py, str(MANIFEST_RELEASE), "--bogus-flag"], capture_output=True, text=True)
    assert bad.returncode == 2
    assert "Traceback" not in bad.stderr
