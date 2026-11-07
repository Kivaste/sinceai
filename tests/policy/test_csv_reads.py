"""Every CSV read in src/ and tests/ is ``dtype=str`` with NA parsing off (AGENTS.md hard rule); pets_eval.io readers infer.

Rows (trigger -> result):
  pd.read_csv(...) without dtype=str                       -> violation
  pd.read_csv(...) without keep_default_na=False           -> violation
  pd.read_csv(...) without na_filter=False                 -> violation
  a call to a pets_eval.io reader (load_catalog, ...)      -> violation (those infer types / parse NA)
  a locally defined read_csv wrapper called by bare name   -> not a pandas call, ignored
The production scan runs over the real src and tests trees; the planted-file tests prove it can fail.
"""
from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
# load_identity_truth is a kit reader too: kiteval.scorecard runs the kit's own locator with a string-preserving pd
# (the truth folder stays closed to this package, tests/pets_attacker/test_boundary.py), never by calling it directly.
KIT_READERS = {"load_catalog", "load_tables", "read_table", "load_holdout", "load_identity_truth"}
ROOT = Path(__file__).resolve().parents[2]


def scan_file(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    local = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    # name bound by `from M import orig as alias` -> (root package of M, orig): aliases resolve to the original symbol
    origin = {a.asname or a.name: ((n.module or "").split(".")[0], a.name) for n in ast.walk(tree)
              if isinstance(n, ast.ImportFrom) for a in n.names}
    pandas_names = {a.asname or a.name for n in ast.walk(tree) if isinstance(n, ast.Import)
                    for a in n.names if a.name.split(".")[0] == "pandas"}
    bad = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if isinstance(f, ast.Attribute):  # pd.read_csv, p.read_csv, k.load_tables: the attribute is the original name
            name = f.attr
            if name == "read_csv":  # only pandas' own; a repo module's read_csv (loader.read_csv) is its own contract
                r = f.value
                while isinstance(r, ast.Attribute):
                    r = r.value
                if not (isinstance(r, ast.Name) and r.id in pandas_names):
                    continue
        elif isinstance(f, ast.Name):
            if f.id in local:
                continue  # defined in this file, not a pandas / kit call
            root, name = origin.get(f.id, ("", f.id))
            if root not in ("pandas", "pets_eval"):
                continue
        else:
            continue
        if name in KIT_READERS:
            bad.append(f"{path.name}:{n.lineno} {name}")
        if name != "read_csv":
            continue
        kw = {k.arg: k.value for k in n.keywords}
        d, na = kw.get("dtype"), kw.get("keep_default_na")
        if not (isinstance(d, ast.Name) and d.id == "str"):
            bad.append(f"{path.name}:{n.lineno} read_csv without dtype=str")
        if not (isinstance(na, ast.Constant) and na.value is False):
            bad.append(f"{path.name}:{n.lineno} read_csv without keep_default_na=False")
        nf = kw.get("na_filter")
        if not (isinstance(nf, ast.Constant) and nf.value is False):
            bad.append(f"{path.name}:{n.lineno} read_csv without na_filter=False")
    return bad


def scan_tree(root: Path) -> list[str]:
    return [b for p in sorted(root.rglob("*.py")) for b in scan_file(p)]


def test_src_reads_every_csv_as_str_without_na_parsing():
    assert scan_tree(SRC) == []


def test_tests_read_every_csv_as_str_without_na_parsing():
    assert scan_tree(ROOT / "tests") == []


def test_scan_flags_missing_dtype(tmp_path):
    (tmp_path / "a.py").write_text("import pandas as pd\npd.read_csv('x.csv', keep_default_na=False, na_filter=False)\n")
    assert scan_tree(tmp_path) == ["a.py:2 read_csv without dtype=str"]


def test_scan_flags_missing_keep_default_na_in_multiline_call(tmp_path):
    (tmp_path / "a.py").write_text("import pandas as pd\nx = pd.read_csv(\n    'x.csv',\n    dtype=str, na_filter=False,\n)\n")
    assert scan_tree(tmp_path) == ["a.py:2 read_csv without keep_default_na=False"]


def test_scan_flags_kit_reader_and_pandas_import(tmp_path):
    (tmp_path / "a.py").write_text("from pets_eval.io import load_tables\nload_tables(1)\nimport pets_eval\npets_eval.io.load_catalog('r')\n"
                                   "from pandas import read_csv\nread_csv('x')\n")
    assert len(scan_tree(tmp_path)) == 5


def test_scan_passes_clean_and_local_wrapper(tmp_path):
    (tmp_path / "a.py").write_text("import pandas as pd\n"
                                   "pd.read_csv('x', dtype=str, keep_default_na=False, na_filter=False)\n"
                                   "def read_csv(p):\n    return p\nread_csv('y')\n")
    assert scan_tree(tmp_path) == []


def test_scan_flags_aliased_pandas_read_csv(tmp_path):
    (tmp_path / "a.py").write_text("from pandas import read_csv as rc\nrc('x')\n")
    assert scan_tree(tmp_path) == ["a.py:2 read_csv without dtype=str", "a.py:2 read_csv without keep_default_na=False",
                               "a.py:2 read_csv without na_filter=False"]


def test_scan_flags_module_aliased_pandas(tmp_path):
    (tmp_path / "a.py").write_text("import pandas as p\np.read_csv('x')\n")
    assert len(scan_tree(tmp_path)) == 3


def test_scan_flags_aliased_kit_reader(tmp_path):
    (tmp_path / "a.py").write_text("from pets_eval.io import load_tables as lt\nlt(1)\n")
    assert scan_tree(tmp_path) == ["a.py:2 load_tables"]


def test_scan_flags_module_aliased_kit_reader(tmp_path):
    (tmp_path / "a.py").write_text("from pets_eval import io as k\nk.load_catalog('r')\nimport pets_eval.io as q\nq.load_holdout(1)\n")
    assert len(scan_tree(tmp_path)) == 2


def test_scan_ignores_aliased_names_not_from_pandas_or_kit(tmp_path):
    (tmp_path / "a.py").write_text("from mylib import read_csv as rc, load_tables as lt\nrc('x')\nlt(1)\n")
    assert scan_tree(tmp_path) == []


def test_scan_flags_missing_na_filter(tmp_path):
    (tmp_path / "a.py").write_text("import pandas as pd\npd.read_csv('x', dtype=str, keep_default_na=False)\n")
    assert scan_tree(tmp_path) == ["a.py:2 read_csv without na_filter=False"]


def test_scan_flags_identity_truth_loader(tmp_path):
    (tmp_path / "a.py").write_text("from pets_eval import io as k\nk.load_identity_truth('r', 'd', 't')\n"
                                   "from pets_eval.io import load_identity_truth as lit\nlit(1, 2, 3)\n")
    assert scan_tree(tmp_path) == ["a.py:2 load_identity_truth", "a.py:4 load_identity_truth"]

def test_scan_ignores_read_csv_method_of_a_non_pandas_module(tmp_path):
    (tmp_path / "a.py").write_text("from pets_release.redactor.lexicon import loader\nloader.read_csv('x')\nimport pandas as pd\npd.read_csv('y')\n")
    assert scan_tree(tmp_path) == ["a.py:4 read_csv without dtype=str", "a.py:4 read_csv without keep_default_na=False",
                                  "a.py:4 read_csv without na_filter=False"]

