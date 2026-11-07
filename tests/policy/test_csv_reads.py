"""Every CSV read in src/ is ``dtype=str`` with NA parsing off (AGENTS.md hard rule); pets_eval.io readers infer.

Rows (trigger -> result):
  pd.read_csv(...) without dtype=str                       -> violation
  pd.read_csv(...) without keep_default_na=False           -> violation
  a call to a pets_eval.io reader (load_catalog, ...)      -> violation (those infer types / parse NA)
  a locally defined read_csv wrapper called by bare name   -> not a pandas call, ignored
The production scan runs over the real src tree; the planted-file tests prove it can fail.
"""
from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
# load_identity_truth stays: the ground-truth folder may only be read by pets_attacker or pets-eval
# (tests/pets_attacker/test_boundary.py); its one consumer only asks whether any person id is present.
KIT_READERS = {"load_catalog", "load_tables", "read_table", "load_holdout"}


def scan_file(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    local = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    imported = {a.asname or a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
                and (n.module or "").split(".")[0] == "pandas" for a in n.names}
    bad = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None
        if name in KIT_READERS and not (isinstance(f, ast.Name) and name in local):
            bad.append(f"{path.name}:{n.lineno} {name}")
        if name != "read_csv":
            continue
        if isinstance(f, ast.Name) and (name in local or name not in imported):
            continue
        kw = {k.arg: k.value for k in n.keywords}
        d, na = kw.get("dtype"), kw.get("keep_default_na")
        if not (isinstance(d, ast.Name) and d.id == "str"):
            bad.append(f"{path.name}:{n.lineno} read_csv without dtype=str")
        if not (isinstance(na, ast.Constant) and na.value is False):
            bad.append(f"{path.name}:{n.lineno} read_csv without keep_default_na=False")
    return bad


def scan_tree(root: Path) -> list[str]:
    return [b for p in sorted(root.rglob("*.py")) for b in scan_file(p)]


def test_src_reads_every_csv_as_str_without_na_parsing():
    assert scan_tree(SRC) == []


def test_scan_flags_missing_dtype(tmp_path):
    (tmp_path / "a.py").write_text("import pandas as pd\npd.read_csv('x.csv', keep_default_na=False)\n")
    assert scan_tree(tmp_path) == ["a.py:2 read_csv without dtype=str"]


def test_scan_flags_missing_keep_default_na_in_multiline_call(tmp_path):
    (tmp_path / "a.py").write_text("import pandas as pd\nx = pd.read_csv(\n    'x.csv',\n    dtype=str,\n)\n")
    assert scan_tree(tmp_path) == ["a.py:2 read_csv without keep_default_na=False"]


def test_scan_flags_kit_reader_and_pandas_import(tmp_path):
    (tmp_path / "a.py").write_text("from pets_eval import io as kit_io\nkit_io.load_catalog('r')\n"
                                   "from pandas import read_csv\nread_csv('x')\n")
    assert len(scan_tree(tmp_path)) == 3


def test_scan_passes_clean_and_local_wrapper(tmp_path):
    (tmp_path / "a.py").write_text("import pandas as pd\n"
                                   "pd.read_csv('x', dtype=str, keep_default_na=False, na_filter=False)\n"
                                   "def read_csv(p):\n    return p\nread_csv('y')\n")
    assert scan_tree(tmp_path) == []
