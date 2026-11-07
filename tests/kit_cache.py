"""Test-only, process-shared CSV parse cache. Never imported by production.

Cache files contain private kit rows: keep them outside every checkout. Each
read hashes the actual source bytes (stat alone is insufficient). Pickles are
authenticated with a local, cache-specific random key BEFORE deserialization;
an invalid entry is a miss, never a source of test data or executable pickle.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import pickle
import sys
import tempfile
from pathlib import Path

import pandas as pd
import pytest


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


class KitCSVCache:
    """Read CSVs as strings, returning a fresh frame even on a cache hit."""

    def __init__(self, cache_dir: Path | None = None, *, reader=None):
        if cache_dir is None:
            base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".cache")
            cache_dir = base / "sinceai-kitcache"
        self.directory = Path(cache_dir).resolve()
        repo = Path(__file__).resolve().parents[1]
        if self.directory.is_relative_to(repo) or any(
            (parent / ".git").exists() for parent in (self.directory, *self.directory.parents)
        ):
            raise ValueError("kit cache must live outside the repository")
        self.directory.mkdir(parents=True, exist_ok=True)
        self.reader = reader or pd.read_csv
        self._key = self._local_key()

    def _local_key(self) -> bytes:
        path = self.directory / ".authentication-key"
        if not path.exists():
            fd, name = tempfile.mkstemp(dir=self.directory, prefix=".key-")
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(os.urandom(32))
                try:
                    # Publish a complete key without replacing a concurrent winner.
                    os.link(name, path)
                except FileExistsError:
                    pass
            finally:
                Path(name).unlink(missing_ok=True)
        if path.is_symlink():
            raise ValueError("invalid cache authentication key")
        key = path.read_bytes()
        if len(key) != 32:
            raise ValueError("invalid cache authentication key")
        return key

    def read_csv(self, path, **options) -> pd.DataFrame:
        if options.get("dtype") is not str:
            raise ValueError("kit CSV reads require dtype=str")
        source = Path(path).resolve(strict=True)
        before = source.stat()
        content = source.read_bytes()
        after = source.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError("kit CSV changed during read")
        identity = {
            "format": 1,
            "path": str(source),
            "size": after.st_size,
            "mtime_ns": after.st_mtime_ns,
            "sha256": hashlib.sha256(content).hexdigest(),
            "pandas": pd.__version__,
            "python": list(sys.version_info[:2]),
            "options": {**options, "dtype": "str"},
        }
        encoded = _canonical(identity)
        # JSON normalizes sequence options such as tuple usecols to lists.
        identity = json.loads(encoded)
        entry = self.directory / (hashlib.sha256(encoded).hexdigest() + ".cache")
        try:
            if entry.is_symlink():
                raise ValueError("cache entry is a link")
            header, payload = entry.read_bytes().split(b"\n", 1)
            record = json.loads(header)
            if set(record) != {"identity", "signature"} or record["identity"] != identity:
                raise ValueError("cache identity mismatch")
            signature = hmac.new(self._key, encoded + b"\n" + payload, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(record["signature"], signature):
                raise ValueError("cache authentication mismatch")
            frame = pickle.loads(payload)
            if not isinstance(frame, pd.DataFrame):
                raise TypeError("cache payload is not a frame")
            return frame
        except (OSError, ValueError, TypeError, KeyError, pickle.UnpicklingError, EOFError):
            pass
        # Parse the bytes that were hashed, not a second (possibly changed) read.
        frame = self.reader(io.BytesIO(content), **options)
        payload = pickle.dumps(frame, protocol=pickle.HIGHEST_PROTOCOL)
        header = _canonical({
            "identity": identity,
            "signature": hmac.new(self._key, encoded + b"\n" + payload, hashlib.sha256).hexdigest(),
        })
        fd, name = tempfile.mkstemp(dir=self.directory, prefix=".entry-")
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(header + b"\n" + payload)
            try:
                os.replace(name, entry)
            except PermissionError:
                # On Windows another reader can briefly hold the destination
                # open. Return our freshly parsed frame, never a stale entry.
                pass
        finally:
            Path(name).unlink(missing_ok=True)
        return frame


def install_kit_cache(kit_root: Path, monkeypatch, *, cache_dir=None):
    """Opt in within a test process; only source CSVs below this kit's data/."""
    if os.environ.get("PETS_TEST_KIT_CACHE") == "0":
        return
    data = (Path(kit_root) / "data").resolve()
    original = pd.read_csv
    cache = KitCSVCache(cache_dir, reader=original)

    def read_csv(path, *args, **options):
        eligible = (
            isinstance(path, (str, Path)) and not args
            and options.get("dtype") is str
            and not options.get("chunksize") and not options.get("iterator")
            and not options.get("memory_map")
        )
        if eligible:
            resolved = Path(path).resolve()
            eligible = (
                resolved.is_relative_to(data) and resolved.suffix.lower() == ".csv"
                and "truth" not in (part.lower() for part in resolved.relative_to(data).parts)
            )
        if eligible:
            try:
                _canonical({**options, "dtype": "str"})
            except (TypeError, ValueError):
                eligible = False
        return cache.read_csv(path, **options) if eligible else original(path, *args, **options)

    monkeypatch.setattr(pd, "read_csv", read_csv)


@pytest.fixture
def kit_parse_cache(kit_root, monkeypatch):
    """Explicit opt-in fixture; CLI children never install this test-only hook."""
    install_kit_cache(kit_root, monkeypatch)
