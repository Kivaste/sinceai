import copy
import importlib.util
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "manifest"
RELEASE_DIR = FIXTURE_DIR / "release"


def _load_builder():
    spec = importlib.util.spec_from_file_location("manifest_fixture_builder", FIXTURE_DIR / "build_fixture.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def builder():
    return _load_builder()


@pytest.fixture(scope="session")
def _base(builder):
    return builder.manifest(builder.tables())


@pytest.fixture
def m(_base):
    """A fresh, valid HEALTH-S1 manifest dict (deep copy of the fixture)."""
    return copy.deepcopy(_base)
