"""Harness self-tests on synthetic folders: the comparison must see every kind of difference."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from e2e_harness import diff_trees, digest_lines, tree_digest


def make(root: Path, files: dict[str, bytes], dirs=()):
    root.mkdir(parents=True)
    for rel, data in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    for d in dirs:
        (root / d).mkdir(parents=True, exist_ok=True)
    return root


BASE = {"manifest.json": b'{"a":1}\n', "data/t.csv": b"x,y\n1,2\n"}


def test_identical_folders(tmp_path):
    a = make(tmp_path / "a", BASE)
    b = make(tmp_path / "b", BASE)
    assert diff_trees(a, b) == []


def test_one_byte_difference(tmp_path):
    a = make(tmp_path / "a", BASE)
    b = make(tmp_path / "b", {**BASE, "data/t.csv": b"x,y\n1,3\n"})
    d = diff_trees(a, b)
    assert len(d) == 1 and d[0].startswith("differs: data/t.csv")


def test_line_ending_difference_is_seen(tmp_path):
    a = make(tmp_path / "a", {"m": b"a\nb\n"})
    b = make(tmp_path / "b", {"m": b"a\r\nb\r\n"})
    assert len(diff_trees(a, b)) == 1


def test_extra_and_missing_files(tmp_path):
    a = make(tmp_path / "a", {**BASE, "extra.txt": b"e"})
    b = make(tmp_path / "b", BASE)
    assert diff_trees(a, b) == ["only in A: extra.txt"]
    assert diff_trees(b, a) == ["only in B: extra.txt"]


def test_empty_directory_difference_is_seen(tmp_path):
    a = make(tmp_path / "a", BASE, dirs=["empty"])
    b = make(tmp_path / "b", BASE)
    assert diff_trees(a, b) == ["only in A: empty"]


def test_file_vs_dir_with_same_name(tmp_path):
    a = make(tmp_path / "a", {"x": b""})
    b = make(tmp_path / "b", {}, dirs=["x"])
    assert len(diff_trees(a, b)) == 1


def test_digest_is_independent_of_creation_order_and_mtime(tmp_path):
    a = make(tmp_path / "a", {"b": b"2", "a": b"1"})
    b = make(tmp_path / "b", {"a": b"1", "b": b"2"})
    import os

    os.utime(b / "a", (1, 1))
    assert diff_trees(a, b) == []
    assert list(tree_digest(a)) == ["a", "b"]


def test_digest_lines_known_value(tmp_path):
    a = make(tmp_path / "a", {"f": b"abc"})
    # sha256("abc"), independent known literal
    assert digest_lines(a) == ["ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad  f"]


def test_missing_folder_raises(tmp_path):
    with pytest.raises(NotADirectoryError):
        tree_digest(tmp_path / "nope")
