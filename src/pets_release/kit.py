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
FORBIDDEN_DATASETS = frozenset({"truth"})
FORBIDDEN_TABLES = frozenset({"field_catalog"})


class KitError(Exception):
    """Bad kit path, scenario, dataset or table name."""


def _check_name(kind: str, name: str, forbidden: frozenset[str]) -> str:
    if not isinstance(name, str) or not _NAME.match(name) or ".." in name:
        raise KitError(f"invalid {kind} name: {name!r}")
    if name.lower() in forbidden:
        raise KitError(f"{kind} {name!r} is not accessible through kit access")
    return name


class Kit:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        if not self.root.is_dir():
            raise KitError(f"kit path is not a directory: {self.root}")

    # scenarios
    def scenarios(self) -> list[dict]:
        path = self.root / "metadata" / "scenarios.json"
        if not path.is_file():
            raise KitError("kit has no metadata/scenarios.json")
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
        d = self.root / "data" / dataset
        if not d.is_dir():
            raise KitError(f"unknown dataset: {dataset!r}")
        return d

    def table_names(self, dataset: str) -> list[str]:
        return sorted(p.stem for p in self._dataset_dir(dataset).glob("*.csv"))

    def _table_path(self, dataset: str, table: str) -> Path:
        _check_name("table", table, FORBIDDEN_TABLES)
        path = self._dataset_dir(dataset) / f"{table}.csv"
        if not path.is_file():
            raise KitError(f"unknown table: {dataset}/{table}")
        return path

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
        return path.read_text(encoding="utf-8")
