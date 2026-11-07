"""Synthetic-only contract for the test CSV parse cache.

Rule: a hit must have the exact source identity, reader options and authenticated
payload. Failure rows: changed bytes/stat/options -> reparse; planted/stale
payload -> reparse; concurrent writers -> complete, independently owned frames.
The public seam is KitCSVCache.read_csv, also used by real-kit test fixtures.
"""

import json
import os
import pickle
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from tests.kit_cache import KitCSVCache, install_kit_cache


def test_cached_frames_equal_csv_and_are_independently_owned(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text("id,empty,word\n001,,NA\n002,x,hello\n", encoding="utf-8")
    calls = []

    def reader(path, **options):
        calls.append(1)
        return pd.read_csv(path, **options)

    options = {"dtype": str, "keep_default_na": False}
    cache = KitCSVCache(tmp_path / "cache", reader=reader)
    expected = pd.read_csv(source, **options)
    assert_frame_equal(cache.read_csv(source, **options), expected)
    fresh_process_cache = KitCSVCache(tmp_path / "cache", reader=reader)
    first_hit = fresh_process_cache.read_csv(source, **options)
    assert_frame_equal(first_hit, expected)
    first_hit.iloc[0, 0] = "mutated"
    assert_frame_equal(fresh_process_cache.read_csv(source, **options), expected)
    assert len(calls) == 1


def test_tuple_reader_options_have_stable_identity(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text("id,word\n001,hello\n", encoding="utf-8")
    calls = []

    def reader(path, **options):
        calls.append(1)
        return pd.read_csv(path, **options)

    cache = KitCSVCache(tmp_path / "cache", reader=reader)
    options = {"dtype": str, "usecols": ("id",)}
    expected = pd.read_csv(source, **options)
    assert_frame_equal(cache.read_csv(source, **options), expected)
    assert_frame_equal(cache.read_csv(source, **options), expected)
    assert len(calls) == 1


@pytest.mark.parametrize("change", ["bytes_same_stat", "size", "mtime", "path", "options", "pandas"])
def test_source_or_reader_identity_change_reparses(tmp_path, monkeypatch, change):
    source = tmp_path / "source.csv"
    source.write_text("id\n001\n", encoding="utf-8")
    calls = []

    def reader(path, **options):
        calls.append(1)
        return pd.read_csv(path, **options)

    cache = KitCSVCache(tmp_path / "cache", reader=reader)
    options = {"dtype": str, "keep_default_na": False}
    cache.read_csv(source, **options)
    stat = source.stat()
    if change == "bytes_same_stat":
        source.write_text("id\n002\n", encoding="utf-8")
        os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    elif change == "size":
        source.write_text("id\n0002\n", encoding="utf-8")
    elif change == "mtime":
        os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    elif change == "path":
        other = tmp_path / "other.csv"
        other.write_bytes(source.read_bytes())
        source = other
    elif change == "options":
        options["keep_default_na"] = True
    elif change == "pandas":
        monkeypatch.setattr(pd, "__version__", "cache-test-version")
    expected = pd.read_csv(source, **options)
    assert_frame_equal(cache.read_csv(source, **options), expected)
    assert len(calls) == 2


@pytest.mark.parametrize("plant", ["payload", "identity", "unknown_key", "stale", "truncated", "executable"])
def test_planted_or_stale_entry_is_rejected_before_deserialization(tmp_path, plant):
    source = tmp_path / "source.csv"
    source.write_text("id\n001\n", encoding="utf-8")
    calls = []

    def reader(path, **options):
        calls.append(1)
        return pd.read_csv(path, **options)

    cache = KitCSVCache(tmp_path / "cache", reader=reader)
    options = {"dtype": str, "keep_default_na": False}
    expected = cache.read_csv(source, **options)
    entry, = cache.directory.glob("*.cache")
    header, payload = entry.read_bytes().split(b"\n", 1)
    record = json.loads(header)
    sentinel = tmp_path / "must-not-exist"
    if plant == "payload":
        payload = pickle.dumps(pd.DataFrame({"id": ["planted"]}))
    elif plant == "identity":
        record["identity"]["size"] += 1
    elif plant == "unknown_key":
        record["extra"] = False
    elif plant == "stale":
        old = entry.read_bytes()
        source.write_text("id\n002\n", encoding="utf-8")
        expected = pd.read_csv(source, **options)
        cache.read_csv(source, **options)
        newest = next(p for p in cache.directory.glob("*.cache") if p != entry)
        newest.write_bytes(old)
        entry = newest
    elif plant == "truncated":
        payload = payload[:7]
    elif plant == "executable":
        class Exploit:
            def __reduce__(self):
                return (os.system, (f'echo unsafe > "{sentinel}"',))
        payload = pickle.dumps(Exploit())
    if plant != "stale":
        entry.write_bytes(json.dumps(record).encode() + b"\n" + payload)
    before = len(calls)
    assert_frame_equal(cache.read_csv(source, **options), expected)
    assert len(calls) == before + 1
    assert not sentinel.exists()


def test_parallel_processes_publish_complete_entries(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text("id\n001\n", encoding="utf-8")
    support = Path(__file__).resolve().parents[1] / "kit_cache.py"
    code = (
        "import importlib.util, sys; "
        "spec=importlib.util.spec_from_file_location('support', sys.argv[1]); "
        "m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); "
        "cache=m.KitCSVCache(sys.argv[3]); "
        "frame=cache.read_csv(sys.argv[2], dtype=str); "
        "assert frame.shape == (1, 1); print('OK')"
    )
    workers = [subprocess.Popen(
        [sys.executable, "-c", code, str(support), str(source), str(tmp_path / "cache")],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    ) for _ in range(4)]
    for worker in workers:
        stdout, stderr = worker.communicate(timeout=60)
        assert worker.returncode == 0, "cache worker failed (output withheld)"
        assert stdout.strip() == "OK"
        assert not stderr
    cache = KitCSVCache(tmp_path / "cache")
    assert_frame_equal(cache.read_csv(source, dtype=str), pd.read_csv(source, dtype=str))
    assert len(list(cache.directory.glob("*.cache"))) == 1
    assert not list(cache.directory.glob(".entry-*"))
    assert not list(cache.directory.glob(".key-*"))


def test_production_reader_never_imports_cache(make_kit):
    root = make_kit()
    code = (
        "import sys; from pets_release.kit import Kit; "
        "Kit(sys.argv[1]).load_dataset('health'); "
        "assert not any('kit_cache' in name for name in sys.modules)"
    )
    proc = subprocess.run([sys.executable, "-c", code, str(root)], capture_output=True, timeout=60, check=False)
    assert proc.returncode == 0, "production reader subprocess failed (output withheld)"


def test_cache_refuses_repository_storage():
    repo = Path(__file__).resolve().parents[2]
    with pytest.raises(ValueError, match="outside"):
        KitCSVCache(repo / "build" / "kit-cache-must-not-be-created")


def test_cache_refuses_storage_in_another_checkout(tmp_path):
    checkout = tmp_path / "another-checkout"
    checkout.mkdir()
    (checkout / ".git").write_text("gitdir: private-worktree\n", encoding="utf-8")
    destination = checkout / "build" / "cache"
    with pytest.raises(ValueError, match="outside"):
        KitCSVCache(destination)
    assert not destination.exists()


def test_non_string_reads_are_refused(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text("id\n001\n", encoding="utf-8")
    with pytest.raises(ValueError, match="dtype=str"):
        KitCSVCache(tmp_path / "cache").read_csv(source)


def test_fixture_caches_only_kit_data_not_protected_or_truth_reads(tmp_path, monkeypatch):
    kit = tmp_path / "kit"
    data = kit / "data" / "health"
    data.mkdir(parents=True)
    source = data / "visits.csv"
    source.write_text("id\n001\n", encoding="utf-8")
    protected = tmp_path / "protected.csv"
    protected.write_text("id\n002\n", encoding="utf-8")
    truth = kit / "truth"
    truth.mkdir()
    (truth / "private.csv").write_text("id\n003\n", encoding="utf-8")
    install_kit_cache(kit, monkeypatch, cache_dir=tmp_path / "cache")
    for path in (source, protected, truth / "private.csv"):
        pd.read_csv(path, dtype=str)
    assert len(list((tmp_path / "cache").glob("*.cache"))) == 1
    pd.read_csv(source, dtype=str, chunksize=1).close()
    pd.read_csv(source, dtype=str, memory_map=True)
    assert len(list((tmp_path / "cache").glob("*.cache"))) == 1
