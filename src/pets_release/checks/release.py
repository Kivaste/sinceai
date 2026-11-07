"""Read-only view of a candidate release folder. Every cell is a ``str``; nothing is inferred."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

MANIFEST = "privacy_manifest.json"


class ReleaseError(Exception):
    pass


@dataclass(frozen=True)
class Table:
    header: tuple
    frame: pd.DataFrame  # columns de-duplicated by position: use header for names


class Release:
    def __init__(self, path):
        self.path = Path(path)
        if not self.path.is_dir():
            raise ReleaseError("release folder missing")
        self.entries = tuple(sorted(p.name for p in self.path.iterdir()))
        self.csv_files = tuple(e for e in self.entries if e.endswith(".csv") and (self.path / e).is_file())
        self._tables: dict = {}
        self._factor: dict = {}

    def __bool__(self) -> bool:
        return bool(self.entries)

    def table(self, name: str) -> Table:
        if name not in self._tables:
            self._tables[name] = _read_csv(self.path / name)
        return self._tables[name]

    def factorized(self, name: str, idx: int):
        """(codes, uniques) for the column at position ``idx``; cached across checks."""
        key = (name, idx)
        if key not in self._factor:
            col = self.table(name).frame.iloc[:, idx]
            codes, uniques = pd.factorize(col, sort=False)
            self._factor[key] = (codes, list(uniques))
        return self._factor[key]

    def manifest(self):
        p = self.path / MANIFEST
        if not p.is_file():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def sha256(self, name: str) -> str:
        h = hashlib.sha256()
        with (self.path / name).open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()


def _read_csv(path: Path) -> Table:
    text = path.read_bytes().decode("utf-8")  # strict: undecodable bytes are an error, not a pass
    rows = list(csv.reader(io.StringIO(text, newline="")))
    if not rows:
        return Table(header=(), frame=pd.DataFrame())
    header = tuple(rows[0])
    body = rows[1:]
    width = len(header)
    if any(len(r) != width for r in body):
        raise ReleaseError("ragged csv")
    arr = np.array(body, dtype=object).reshape(len(body), width) if body else np.empty((0, width), dtype=object)
    frame = pd.DataFrame(arr, columns=range(width), dtype=object)
    return Table(header=header, frame=frame)
