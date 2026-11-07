"""Put ``tests/writer`` on sys.path so tests import ``writer_helpers`` (a uniquely named helper module)."""
import sys
from pathlib import Path

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
