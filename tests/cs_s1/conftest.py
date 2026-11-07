from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from pets_release.ladders import PseudonymKeys
from pets_release.pseudonym import MasterKey, Scope, pseudonymiser_for

MINIKIT = Path(__file__).resolve().parents[1] / "fixtures" / "minikit" / "customer_service"
TEST_KEY = "test-only-master-key-0123456789abcdef"  # synthetic test key, not a secret


def load_minikit() -> dict:
    return {p.stem: pd.read_csv(p, dtype=str, keep_default_na=False, na_filter=False)
            for p in sorted(MINIKIT.glob("*.csv"))}


def _make_keys(rsid: str = "0123456789abcdef"):
    return PseudonymKeys(pseudonymiser_for(MasterKey.from_text(TEST_KEY)), Scope.release(rsid))


@pytest.fixture(scope="session")
def minikit():
    return load_minikit()


@pytest.fixture(scope="session")
def prepared(minikit):
    from pets_release.cs_s1 import prepare

    return prepare(minikit, _make_keys())


@pytest.fixture(scope="session")
def kept(minikit):
    """Minikit with turn IDs shuffled across conversations: a synthetic key that passes."""
    import random

    from pets_release.cs_s1 import prepare

    src = {k: v.copy() for k, v in minikit.items()}
    n = len(src["turns"])
    perm = list(range(1, n + 1))
    random.Random(23).shuffle(perm)
    src["turns"]["turn_id"] = [f"SYNT-{i:07d}" for i in perm]
    return prepare(src, _make_keys())


@pytest.fixture(scope="session")
def make_keys():
    return _make_keys
