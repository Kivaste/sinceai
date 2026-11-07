"""Shared helpers for cell checks: contract lookups and the per-cell scan loop."""
from __future__ import annotations

import numpy as np

from pets_release.checks.cells._validators import HEX64_TOKEN
from pets_release.checks.records import Violation, locations
from pets_release.checks.release import MANIFEST


def table_file(table: str) -> str:
    return table if table.endswith(".csv") else f"{table}.csv"


def token_columns(contract) -> set:
    return {(table_file(t["table"]), t["column"]) for t in contract.get("tokens", [])}


def contract_files(contract) -> dict:
    files = contract["files"]
    if not isinstance(files, dict):
        raise TypeError("contract.files must be a mapping")
    return files


def file_label(release, contract, name: str) -> str:
    """Contract-listed names (and the manifest) are reported as-is; any other release-derived
    file name is replaced by a content-free marker (its position in the sorted folder listing)."""
    if name == MANIFEST or name in contract_files(contract):
        return name
    return f"unlisted-file#{release.entries.index(name)}"


def column_label(contract, file: str, idx: int, col: str) -> str:
    """Contract-declared column names are reported as-is; others become ``unlisted-column#<pos>``."""
    spec = contract_files(contract).get(file)
    if spec is not None and col in spec["columns"]:
        return col
    return f"unlisted-column#{idx}"


def scan_cells(release, contract, check: str, label: str, finder):
    """Run ``finder(cell) -> (high, low)`` over every cell of every CSV table.

    Valid 64-hex values in declared token columns are skipped (contract-aware token handling).
    Returns (cells_scanned, violations) with one violation per (file, column, severity).
    """
    tokens = token_columns(contract)
    n = 0
    out = []
    for f in release.csv_files:
        t = release.table(f)
        nrows = len(t.frame)
        for idx, col in enumerate(t.header):
            n += nrows
            if not nrows:
                continue
            codes, uniques = release.factorized(f, idx)
            is_tok = (f, col) in tokens
            hi = np.zeros(len(uniques), dtype=bool)
            lo = np.zeros(len(uniques), dtype=bool)
            for i, u in enumerate(uniques):
                if not u or (is_tok and HEX64_TOKEN.fullmatch(u)):
                    continue
                h, low = finder(u)
                hi[i] = h > 0
                lo[i] = low > 0
            for sev, mask in (("high", hi), ("low", lo)):
                if mask.any():
                    rows = np.nonzero(mask[codes])[0]
                    out.append(Violation(check, label, sev, file_label(release, contract, f),
                                         column_label(contract, f, idx, col), len(rows), locations(rows)))
    return n, tuple(out)
