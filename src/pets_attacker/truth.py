"""The only reader of the kit's truth/ directory. Loads id maps as DataFrames of str.\n\nResidual risk (follow-up #44 item 6): the runtime guard that keeps other code away from truth/ covers\nimport-time reads only. A call-time read with a runtime-composed path is not caught; review for it.\n"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def _read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def load_identity(kit_root: Path, domain: str, table: str) -> pd.DataFrame:
    """record_id -> person_id for an original table."""
    return _read(Path(kit_root) / "truth" / f"{domain}__{table}.csv")


def load_adversary_truth(kit_root: Path, adversary: str) -> pd.DataFrame:
    """adv_row_id -> person_id for an adversary file."""
    return _read(Path(kit_root) / "truth" / f"adversary__{adversary}.csv")


def load_rowmap(path: Path) -> pd.DataFrame:
    """protected_row -> original_record_id, as written next to a release by the baselines."""
    return _read(Path(path))
