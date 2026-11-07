"""Kit access: string tables, strict scenario IDs, input digests.

Never opens `truth/` or `metadata/field_catalog.csv` (the latter belongs to the detector's scoring path only).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pandas as pd

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
FORBIDDEN_DATASETS = frozenset({"truth", "pii_spans"})  # gold span labels are scorer-side data, never pipeline input
FORBIDDEN_TABLES = frozenset({"field_catalog"})


class KitError(Exception):
    """Bad kit path, scenario, dataset or table name."""


def _check_name(kind: str, name: str, forbidden: frozenset[str]) -> str:
    if not isinstance(name, str) or not _NAME.match(name) or ".." in name:
        raise KitError(f"invalid {kind} name: {name!r}")
    if name.lower() in forbidden:
        raise KitError(f"{kind} {name!r} is not accessible through kit access")
    return name


def refuse_forbidden_path(path: str | Path) -> Path:
    """Resolve ``path`` and refuse one that passes through a ``truth/``
    directory or is a field catalog. For callers reading a file directly
    (not through :class:`Kit`). Returns the resolved path."""
    try:
        real = Path(path).resolve(strict=True)
    except (OSError, RuntimeError) as e:
        raise KitError(f"cannot resolve {Path(path).name!r}") from e
    if any(x.lower() in FORBIDDEN_DATASETS or Path(x).stem.lower() in FORBIDDEN_TABLES for x in real.parts):
        raise KitError(f"{real.name!r} resolves into a forbidden location")
    return real


class Kit:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        if not self.root.is_dir():
            raise KitError(f"kit path is not a directory: {self.root}")
        self._real_root = self.root.resolve(strict=True)

    def _resolve(self, path: Path, base: Path | None = None) -> Path:
        """Resolve links/junctions, then require the destination to sit under `base` (default: the kit)
        and to pass through no `truth/` directory and no field catalog."""
        try:
            real = path.resolve(strict=True)
        except (OSError, RuntimeError) as e:
            raise KitError(f"cannot resolve {path.name!r}") from e
        base = base if base is not None else self._real_root
        try:
            real.relative_to(base)
            parts = [x.lower() for x in real.relative_to(self._real_root).parts]
        except ValueError as e:
            raise KitError(f"{path.name!r} resolves outside {base.name!r}") from e
        if any(x in FORBIDDEN_DATASETS or Path(x).stem in FORBIDDEN_TABLES for x in parts):
            raise KitError(f"{path.name!r} resolves into a forbidden location")
        return real

    # scenarios
    def scenarios(self) -> list[dict]:
        path = self.root / "metadata" / "scenarios.json"
        if not path.is_file():
            raise KitError("kit has no metadata/scenarios.json")
        path = self._resolve(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise KitError("scenarios.json is not a list")
        return sorted(data, key=lambda s: str(s.get("id", "")))

    def scenario(self, scenario_id: str) -> dict:
        """Exact, case-sensitive match; anything else is an error."""
        for s in self.scenarios():
            if s.get("id") == scenario_id:
                return s
        raise KitError(f"unknown scenario ID: {scenario_id!r}")

    # tables
    def _dataset_dir(self, dataset: str) -> Path:
        _check_name("dataset", dataset, FORBIDDEN_DATASETS)
        data = self._resolve(self.root / "data")
        if data != self._real_root / "data":
            raise KitError("data/ must be a real directory inside the kit")
        d = data / dataset
        if not d.is_dir():
            raise KitError(f"unknown dataset: {dataset!r}")
        if self._resolve(d, data) != d:
            raise KitError(f"dataset {dataset!r} must be a real directory under data/")
        return d

    def table_names(self, dataset: str) -> list[str]:
        return sorted(
            p.stem for p in self._dataset_dir(dataset).glob("*.csv") if p.stem.lower() not in FORBIDDEN_TABLES
        )

    def _table_path(self, dataset: str, table: str) -> Path:
        _check_name("table", table, FORBIDDEN_TABLES)
        d = self._dataset_dir(dataset)
        path = d / f"{table}.csv"
        if not path.is_file():
            raise KitError(f"unknown table: {dataset}/{table}")
        return self._resolve(path, d)

    def load_table(self, dataset: str, table: str) -> pd.DataFrame:
        """All columns are strings; empty cells stay '' (no NaN, no type inference)."""
        return pd.read_csv(
            self._table_path(dataset, table), dtype=str, keep_default_na=False, na_filter=False, encoding="utf-8"
        )

    def load_dataset(self, dataset: str) -> dict[str, pd.DataFrame]:
        return {t: self.load_table(dataset, t) for t in self.table_names(dataset)}

    def input_digest(self, dataset: str, table: str) -> str:
        return hashlib.sha256(self._table_path(dataset, table).read_bytes()).hexdigest()

    def input_digests(self, dataset: str) -> dict[str, str]:
        return {t: self.input_digest(dataset, t) for t in self.table_names(dataset)}

    def data_dictionary(self) -> str:
        path = self.root / "docs" / "DATA_DICTIONARY.md"
        if not path.is_file():
            raise KitError("kit has no docs/DATA_DICTIONARY.md")
        return self._resolve(path).read_text(encoding="utf-8")
