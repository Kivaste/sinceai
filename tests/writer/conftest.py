"""Put ``tests/writer`` on sys.path so tests import ``writer_helpers`` (a uniquely named helper module)."""
import sys
from pathlib import Path

import pytest

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from writer_helpers import install_producer_standins, make_kit


@pytest.fixture(autouse=True)
def producer_standins(monkeypatch):
    """Registry stand-ins for unregistered producer checks only (ticket 11 not merged); restored after each test."""
    return install_producer_standins(lambda d, k, v: monkeypatch.setitem(d, k, v))


@pytest.fixture
def kit(tmp_path):
    return make_kit(tmp_path / "kit")
