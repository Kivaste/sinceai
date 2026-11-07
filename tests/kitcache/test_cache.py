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


@pytest.mark.parametrize("change", ["bytes_same_stat", "size", "options", "pandas"])
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
    elif change == "options":
        options["keep_default_na"] = True
    elif change == "pandas":
        monkeypatch.setattr(pd, "__version__", "cache-test-version")
    expected = pd.read_csv(source, **options)
    assert_frame_equal(cache.read_csv(source, **options), expected)
    assert len(calls) == 2


def test_identical_content_in_different_worktrees_and_mtimes_shares_entry(tmp_path):
    """Cache-reader seam: copying/touching unchanged input must not reparse."""
    sources = [tmp_path / name / "data.csv" for name in ("worktree-a", "worktree-b")]
    for index, source in enumerate(sources):
        source.parent.mkdir()
        source.write_text("id\n001\n", encoding="utf-8")
        os.utime(source, ns=(1_000_000_000, (index + 1) * 1_000_000_000))
    parses = []

    def reader(path, **options):
        parses.append(1)
        return pd.read_csv(path, **options)

    options = {"dtype": str, "keep_default_na": False}
    expected = pd.read_csv(sources[0], **options)
    for source in sources:
        cache = KitCSVCache(tmp_path / "shared-cache", reader=reader)
        assert_frame_equal(cache.read_csv(source, **options), expected)
    assert len(parses) == 1
    assert len(list((tmp_path / "shared-cache").glob("*.cache"))) == 1


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
        record["identity"]["sha256"] = "0" * 64
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


@pytest.mark.parametrize("setting", ["0", "1"])
def test_production_reader_never_imports_cache(make_kit, tmp_path, setting):
    root = make_kit()
    code = """
import importlib.abc
import sys
class RefuseTestCache(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if 'kit_cache' in fullname:
            raise AssertionError('production attempted to import test cache')
sys.meta_path.insert(0, RefuseTestCache())
from pets_release.kit import Kit
frames = Kit(sys.argv[1]).load_dataset('health')
assert set(frames) == {'ed_visits', 'lab_results'}
assert frames['ed_visits'].shape == (2, 3)
assert not any('kit_cache' in name for name in sys.modules)
"""
    local = tmp_path / "local-appdata"
    env = {**os.environ, "PETS_TEST_KIT_CACHE": setting, "LOCALAPPDATA": str(local)}
    proc = subprocess.run([sys.executable, "-c", code, str(root)], env=env,
                          capture_output=True, timeout=60, check=False)
    assert proc.returncode == 0, "production reader subprocess failed (output withheld)"
    assert not (local / "sinceai-kitcache").exists()


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


@pytest.mark.parametrize("setting", [None, "0", "true", "1"])
def test_fixture_is_disabled_unless_explicitly_enabled(tmp_path, monkeypatch, setting):
    """Fixture seam: an absent/unrecognised toggle must leave pandas unchanged."""
    if setting is None:
        monkeypatch.delenv("PETS_TEST_KIT_CACHE", raising=False)
    else:
        monkeypatch.setenv("PETS_TEST_KIT_CACHE", setting)
    original = pd.read_csv
    destination = tmp_path / "cache"
    install_kit_cache(tmp_path / "kit", monkeypatch, cache_dir=destination)
    assert (pd.read_csv is not original) is (setting == "1")
    assert destination.exists() is (setting == "1")


@pytest.mark.parametrize("truth_name", ["truth", "TrUtH"])
def test_fixture_caches_only_kit_data_not_protected_or_truth_reads(tmp_path, monkeypatch, truth_name):
    monkeypatch.setenv("PETS_TEST_KIT_CACHE", "1")
    kit = tmp_path / "kit"
    data = kit / "data" / "health"
    data.mkdir(parents=True)
    source = data / "visits.csv"
    source.write_text("id\n001\n", encoding="utf-8")
    protected = tmp_path / "protected.csv"
    protected.write_text("id\n002\n", encoding="utf-8")
    # Must be *inside* data: an outside-data fixture cannot exercise the truth guard.
    truth = data / truth_name
    truth.mkdir()
    (truth / "private.csv").write_text("id\n003\n", encoding="utf-8")
    install_kit_cache(kit, monkeypatch, cache_dir=tmp_path / "cache")
    for path in (source, protected, truth / "private.csv"):
        pd.read_csv(path, dtype=str)
    assert len(list((tmp_path / "cache").glob("*.cache"))) == 1
    pd.read_csv(source, dtype=str, chunksize=1).close()
    pd.read_csv(source, dtype=str, memory_map=True)
    assert len(list((tmp_path / "cache").glob("*.cache"))) == 1


@pytest.mark.parametrize("name", [".authentication-key", "private.cache", ".key-synthetic", ".entry-synthetic"])
def test_git_ignores_private_cache_material(name):
    """Git CLI seam: accidentally placed cache material is never addable by default."""
    repo = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["git", "-C", str(repo), "check-ignore", "--no-index", "--", name],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0
