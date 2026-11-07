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


def test_cli_never_reads_catalog_or_truth(tmp_path, cli, make_kit):
    kit = make_kit()
    (kit / "metadata" / "field_catalog.csv").write_text("dataset,table,column,privacy_role\n", encoding="utf-8")
    p = cli("detect", "health", "--kit", str(kit), "--out", str(tmp_path / "o.csv"))
    assert p.returncode == 0, p.stderr
    import pets_release.detect as pkg
    for f in Path(pkg.__file__).parent.glob("*.py"):
        text = f.read_text(encoding="utf-8")
        assert "field_catalog" not in text.replace("field_catalog is never read", ""), f.name
        assert "truth" not in text.replace("truth/", ""), f.name
