"""Detector tests. Synthetic rows only; the kit's headers are copied from pets_eval (detect.py docstring) and
the unseen README, and the real-kit tests are marked `kit`."""

from __future__ import annotations

import csv
import io
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent))
import helpers  # noqa: E402

from pets_release.detect import inventory, serialise  # noqa: E402

KIT_ROLES = {
    "direct_identifier", "quasi_identifier", "sensitive_attribute", "technical_identifier",
    "free_text", "record_key", "non_sensitive",
}
KIT_HEADER = ["dataset", "table", "column", "privacy_role", "subtype"]
UNSEEN_HEADER = ["column", "privacy_role", "subtype"]


def _frame(**kw) -> pd.DataFrame:
    return pd.DataFrame(helpers.make_frame(**kw), dtype=str)


def _roles(inv) -> dict[str, str]:
    return {r["column"]: r["role"] for r in inv}


def test_obfuscated_headers_get_the_expected_roles():
    inv = inventory.detect_table(_frame(), dataset="x", table="export")
    assert _roles(inv) == helpers.EXPECTED


def test_every_column_gets_exactly_one_kit_role_even_when_empty_or_constant():
    df = pd.DataFrame({"a": [""] * 30, "b": ["x"] * 30, "c": [str(i) for i in range(30)]}, dtype=str)
    inv = inventory.detect_table(df, dataset="x", table="t")
    assert [r["column"] for r in inv] == ["a", "b", "c"]
    assert {r["role"] for r in inv} <= KIT_ROLES
    assert all(r["evidence"] for r in inv)


def test_zero_row_table_still_labels_every_column():
    df = pd.DataFrame({"patient_hetu": [], "zzz": []}, dtype=str)
    inv = inventory.detect_table(df, dataset="x", table="t")
    assert _roles(inv)["patient_hetu"] == "direct_identifier"
    assert _roles(inv)["zzz"] in KIT_ROLES


def test_renamed_columns_keep_their_roles():
    """Same values under different, meaningless headers: roles must not depend on the header."""
    df = _frame()
    renamed = df.rename(columns={c: f"field_{i * 7 + 3}" for i, c in enumerate(df.columns)})
    a = _roles(inventory.detect_table(df, dataset="x", table="t"))
    b = _roles(inventory.detect_table(renamed, dataset="x", table="t"))
    assert list(a.values()) == list(b.values())


def test_validators_reject_invalid_check_digits():
    rng = __import__("random").Random(1)
    good = [helpers.hetu(rng) for _ in range(60)]
    bad = [g[:-1] + ("Z" if g[-1] != "Z" else "Y") for g in good]  # wrong check char
    assert _roles(inventory.detect_table(pd.DataFrame({"v": good}, dtype=str), "x", "t"))["v"] == "direct_identifier"
    assert _roles(inventory.detect_table(pd.DataFrame({"v": bad}, dtype=str), "x", "t"))["v"] != "direct_identifier"


def test_foreign_key_containment_marks_key_and_reference():
    parent = pd.DataFrame({"x1": [f"V{i:05d}" for i in range(100)], "x2": ["a", "b"] * 50}, dtype=str)
    child = pd.DataFrame({"y1": [f"V{i % 100:05d}" for i in range(300)], "y2": [str(i) for i in range(300)]},
                         dtype=str)
    inv = inventory.detect_dataset("d", {"parent": parent, "child": child})
    by = {(r["table"], r["column"]): r["role"] for r in inv}
    assert by[("parent", "x1")] == "record_key"
    assert by[("child", "y1")] == "technical_identifier"


def test_sensitive_attribute_from_physiological_range_and_name_tokens():
    n = 200
    df = pd.DataFrame(
        {
            "temp": [f"{36 + (i % 40) / 10:.1f}" for i in range(n)],
            "diagnosis_code": [["J18.9", "I21.0", "K35.8", "E11.9"][i % 4] for i in range(n)],
            "region": [["north", "south", "east"][i % 3] for i in range(n)],
        },
        dtype=str,
    )
    r = _roles(inventory.detect_table(df, "x", "t"))
    assert r["temp"] == "sensitive_attribute"
    assert r["diagnosis_code"] == "sensitive_attribute"
    assert r["region"] == "non_sensitive"


def test_mixed_real_world_formats():
    n = 300
    rng = __import__("random").Random(3)
    ids = [helpers.hetu(rng) for _ in range(n)]
    ids = [x[:-1] + "0" if i % 3 == 0 else x for i, x in enumerate(ids)]  # some with a wrong check character
    df = pd.DataFrame(
        {
            "a": ids,
            "b": [f"{rng.randint(1, 28):02d}/{rng.randint(1, 12):02d}/{rng.randint(10, 24)}" if i % 2 else
                  f"20{rng.randint(10, 24)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}" for i in range(n)],
            "c": [f"Mäntykatu {rng.randint(1, 99)} A {rng.randint(1, 9)}, 20{rng.randint(100, 900)} Turku"
                  for _ in range(n)],
            "d": [f"{rng.randint(2, 6)} {rng.randint(0, 999):03d},{rng.randint(0, 99):02d}" for _ in range(n)],
        },
        dtype=str,
    )
    r = _roles(inventory.detect_table(df, "x", "t"))
    assert r == {"a": "direct_identifier", "b": "quasi_identifier", "c": "direct_identifier",
                 "d": "sensitive_attribute"}


def test_detection_is_deterministic():
    df = _frame()
    assert inventory.detect_table(df, "x", "t") == inventory.detect_table(df, "x", "t")


def test_kit_serialiser_header_and_rows():
    inv = inventory.detect_table(_frame(n=60), dataset="x", table="export")
    text = serialise.to_kit_csv(inv)
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0] == KIT_HEADER
    assert len(rows) == 1 + 12
    assert all(r[3] in KIT_ROLES for r in rows[1:])


def test_unseen_serialiser_header_and_rows():
    inv = inventory.detect_table(_frame(n=60), dataset="x", table="export")
    rows = list(csv.reader(io.StringIO(serialise.to_unseen_csv(inv))))
    assert rows[0] == UNSEEN_HEADER
    assert [r[0] for r in rows[1:]] == [f"c{i:02d}" for i in range(1, 13)]


def test_headers_match_the_kit_scorer_source():
    """Copied-from-kit check: the scorer's docstring names the prediction columns."""
    kit = os.environ.get("PETS_KIT")
    if not kit:
        pytest.skip("PETS_KIT not set (kit test not run)")
    src = (Path(kit) / "toolkit" / "pets_eval" / "detect.py").read_text(encoding="utf-8")
    assert "dataset, table, column, privacy_role [, subtype]" in src
    assert ",".join(KIT_HEADER) == serialise.KIT_HEADER_LINE
    unseen = (Path(kit) / "data" / "unseen" / "README.md").read_text(encoding="utf-8")
    assert "`column,privacy_role,subtype`" in unseen
    assert ",".join(UNSEEN_HEADER) == serialise.UNSEEN_HEADER_LINE


# CLI seam
def _write_csv(path: Path, df: pd.DataFrame) -> None:
    df.to_csv(path, index=False, encoding="utf-8")


def test_cli_on_a_csv_writes_unseen_format(tmp_path, cli):
    src = tmp_path / "export.csv"
    _write_csv(src, _frame(n=80))
    out = tmp_path / "labels.csv"
    p = cli("detect", str(src), "--out", str(out))
    assert p.returncode == 0, p.stderr
    rows = list(csv.reader(out.read_text(encoding="utf-8").splitlines()))
    assert rows[0] == UNSEEN_HEADER
    assert len(rows) == 13
    assert "@example.fi" not in p.stdout + p.stderr  # no values on the console


def test_cli_kit_format_for_a_csv(tmp_path, cli):
    src = tmp_path / "export.csv"
    _write_csv(src, _frame(n=80))
    out = tmp_path / "labels.csv"
    p = cli("detect", str(src), "--out", str(out), "--format", "kit")
    assert p.returncode == 0, p.stderr
    assert out.read_text(encoding="utf-8").splitlines()[0] == ",".join(KIT_HEADER)


def test_cli_kit_dataset(tmp_path, cli, make_kit):
    kit = make_kit()
    out = tmp_path / "labels.csv"
    p = cli("detect", "health", "--kit", str(kit), "--out", str(out))
    assert p.returncode == 0, p.stderr
    rows = list(csv.reader(out.read_text(encoding="utf-8").splitlines()))
    assert rows[0] == KIT_HEADER
    assert {(r[1], r[2]) for r in rows[1:]} == {
        ("ed_visits", "id"), ("ed_visits", "when"), ("ed_visits", "code"), ("lab_results", "lab_id")}


def test_cli_unknown_dataset_exits_2(tmp_path, cli, make_kit):
    p = cli("detect", "nope", "--kit", str(make_kit()))
    assert p.returncode == 2


def test_cli_no_kit_for_dataset_exits_2(cli):
    p = cli("detect", "health")
    assert p.returncode == 2


def test_cli_unseen_format_on_multi_table_dataset_exits_2(tmp_path, cli, make_kit):
    p = cli("detect", "health", "--kit", str(make_kit()), "--format", "unseen")
    assert p.returncode == 2


# Runs the real CLI (`python -m pets_release ...`) under an audit hook that records every open/listdir/scandir
# touching a `truth` path segment or `field_catalog*` under the kit. The hook's report goes to a side file.
_AUDIT_RUNNER = r"""
import os, runpy, sys
kit = os.path.normcase(os.path.realpath(sys.argv[1]))
report = sys.argv[2]
hits = []
def bad(p):
    try:
        p = os.path.normcase(os.path.realpath(os.fsdecode(p)))
    except Exception:
        return False
    if not (p == kit or p.startswith(kit + os.sep)):
        return False
    parts = p[len(kit):].split(os.sep)
    return any(s == "truth" or s.startswith("field_catalog") for s in parts)
def hook(event, args):
    if event in ("open", "os.listdir", "os.scandir", "os.rename", "os.remove") and args \
            and isinstance(args[0], (str, bytes, os.PathLike)) and bad(args[0]):
        hits.append(event)
sys.addaudithook(hook)
sys.argv = ["pets_release"] + sys.argv[3:]
code = 0
try:
    runpy.run_module("pets_release", run_name="__main__", alter_sys=True)
except SystemExit as e:
    code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
with open(report, "w", encoding="utf-8") as f:
    f.write(str(len(hits)))
sys.exit(code)
"""


def _audited_cli(tmp_path: Path, kit: Path, *args: str):
    import subprocess
    import importlib.util

    ROOT = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("_tests_conftest", ROOT / "tests" / "conftest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cli_env = mod.cli_env

    runner = tmp_path / "audit_runner.py"
    runner.write_text(_AUDIT_RUNNER, encoding="utf-8")
    report = tmp_path / "audit_report.txt"
    p = subprocess.run([sys.executable, str(runner), str(kit), str(report), *args], cwd=ROOT, env=cli_env(),
                       capture_output=True, text=True, encoding="utf-8", check=False)
    assert report.exists(), "audit runner did not complete: " + p.stderr
    return p, int(report.read_text(encoding="utf-8"))


def _poisoned_kit(make_kit) -> Path:
    kit = make_kit()
    (kit / "metadata" / "field_catalog.csv").write_text("dataset,table,column,privacy_role\n", encoding="utf-8")
    (kit / "truth").mkdir()
    (kit / "truth" / "labels.csv").write_text("column,privacy_role\n", encoding="utf-8")
    return kit


def test_cli_never_reads_catalog_or_truth(tmp_path, make_kit):
    kit = _poisoned_kit(make_kit)
    p, hits = _audited_cli(tmp_path, kit, "detect", "health", "--kit", str(kit), "--out", str(tmp_path / "o.csv"))
    assert p.returncode == 0, p.stderr
    assert (tmp_path / "o.csv").exists()
    assert hits == 0, "detect opened a truth/ or field_catalog path"


def test_audit_hook_would_catch_a_catalog_read(tmp_path):
    """Self-check of the audit harness: a script that opens the catalog and truth/ must be counted."""
    import subprocess

    kit = _poisoned_kit_plain(tmp_path)
    script = tmp_path / "evil.py"
    script.write_text(
        "import sys, pathlib\n"
        f"pathlib.Path({str(kit / 'metadata' / 'field_catalog.csv')!r}).read_text()\n"
        f"pathlib.Path({str(kit / 'truth' / 'labels.csv')!r}).read_text()\n", encoding="utf-8")
    # run the evil script through the same hook by pointing runpy at it via a tiny package-free shim
    shim = _AUDIT_RUNNER.replace('runpy.run_module("pets_release", run_name="__main__", alter_sys=True)',
                                 f'runpy.run_path({str(script)!r}, run_name="__main__")')
    runner = tmp_path / "shim.py"
    runner.write_text(shim, encoding="utf-8")
    report = tmp_path / "rep.txt"
    subprocess.run([sys.executable, str(runner), str(kit), str(report)], check=True, capture_output=True)
    assert int(report.read_text(encoding="utf-8")) == 2


def _poisoned_kit_plain(tmp_path: Path) -> Path:
    kit = tmp_path / "kit2"
    (kit / "metadata").mkdir(parents=True)
    (kit / "truth").mkdir()
    (kit / "metadata" / "field_catalog.csv").write_text("x\n", encoding="utf-8")
    (kit / "truth" / "labels.csv").write_text("x\n", encoding="utf-8")
    return kit


def test_detect_source_has_no_truth_reference():
    from pets_attacker.boundary import truth_references
    import pets_release

    # scan the real package tree (root = src/), then restrict to the detect package
    src = Path(pets_release.__file__).parent.parent
    detect_dir = Path(pets_release.__file__).parent / "detect"
    offenders = [f for f in truth_references(src) if Path(f).resolve().is_relative_to(detect_dir.resolve())]
    assert offenders == []
    assert not any("field_catalog" in f.read_text(encoding="utf-8") for f in detect_dir.glob("*.py"))


# --- follow-up #45 ---------------------------------------------------------


@pytest.mark.parametrize("rel", ["truth/export.csv", "metadata/field_catalog.csv", "a/TRUTH/b/x.csv"])
def test_cli_refuses_direct_csv_in_forbidden_locations(tmp_path, cli, rel):
    src = tmp_path / rel
    src.parent.mkdir(parents=True)
    _write_csv(src, _frame(n=80))
    out = tmp_path / "labels.csv"
    p = cli("detect", str(src), "--out", str(out))
    assert p.returncode == 2
    assert not out.exists()
    assert "forbidden" in p.stderr


def test_unknown_role_raises_instead_of_asserting(monkeypatch):
    from pets_release.detect import inventory

    monkeypatch.setattr(inventory, "_classify", lambda profile, link: ("bogus", "", ""))
    with pytest.raises(ValueError, match="unknown role"):
        inventory.detect_table(_frame(n=5), "csv", "t")


# --- follow-up #79: error paths and headers are content-free ------------------------------------------
# Rule: a foreign exception (pandas parse/decode/value error) prints its class name only; a CSV header
# cell that is not a schema identifier refuses the run (exit 2, nothing written). Rows: headerless CSV ->
# first row read as header -> header refused -> no value on console or in --out.
PLANTED = "ZZPLANTED_SECRET_4711"


def test_cli_headerless_csv_never_emits_first_row_values(tmp_path, cli):
    src = tmp_path / "export.csv"
    src.write_text(f"{PLANTED},Maija Planted,x@example.fi\nEMP1,Other Name,y@example.fi\n", encoding="utf-8")
    out = tmp_path / "labels.csv"
    p = cli("detect", str(src), "--out", str(out))
    assert p.returncode == 2
    assert not out.exists()
    for text in (p.stdout, p.stderr):
        assert PLANTED not in text and "Maija" not in text and "example.fi" not in text
    assert "header" in p.stderr


def test_cli_headerless_csv_to_stdout_never_emits_values(tmp_path, cli):
    src = tmp_path / "export.csv"
    src.write_text(f"{PLANTED},Maija Planted\nEMP1,Other Name\n", encoding="utf-8")
    p = cli("detect", str(src))
    assert p.returncode == 2
    assert PLANTED not in p.stdout + p.stderr and "Maija" not in p.stdout + p.stderr


def test_cli_malformed_csv_prints_class_name_only(tmp_path, cli):
    src = tmp_path / "export.csv"
    src.write_bytes(f"a,b\n{PLANTED},x\n{PLANTED},y,z\n".encode("utf-8"))
    p = cli("detect", str(src), "--out", str(tmp_path / "o.csv"))
    assert p.returncode == 2
    assert PLANTED not in p.stdout + p.stderr
    assert "ParserError" in p.stderr


@pytest.mark.parametrize("exc", [
    pd.errors.ParserError(f"Error tokenizing data near '{PLANTED}'"),
    UnicodeDecodeError("utf-8", PLANTED.encode(), 0, 1, f"bad byte in {PLANTED}"),
    ValueError(f"could not convert {PLANTED}"),
    OSError(f"cannot read {PLANTED}"),
])
def test_foreign_exception_text_is_never_printed(tmp_path, monkeypatch, capsys, exc):
    from pets_release.detect import cli as detect_cli

    src = tmp_path / "export.csv"
    src.write_text("a,b\n1,2\n", encoding="utf-8")

    def boom(*a, **k):
        raise exc

    monkeypatch.setattr(detect_cli.pd, "read_csv", boom)
    assert detect_cli.main([str(src)]) == 2
    err = capsys.readouterr()
    assert PLANTED not in err.out + err.err
    assert type(exc).__name__ in err.err


@pytest.mark.parametrize("header", ["Maija Planted", "x@example.fi", "010190-123A", "+358401234567",
                                    "EMP100123", "", "a.1", "1abc"])
def test_header_cell_validator_rejects_value_shapes(header):
    from pets_release.detect.cli import bad_header_cells

    assert bad_header_cells(["ok_col", header]) == 1


def test_header_cell_validator_accepts_schema_identifiers():
    from pets_release.detect.cli import bad_header_cells

    assert bad_header_cells(["visit_id", "icd10_primary", "floor_area_m2", "c01", "Region", "_x"]) == 0
