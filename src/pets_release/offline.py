"""Offline guard: block network sockets in this process and every subprocess it starts.

Guarantee: this process, and any plain `python ...` child (which honours PYTHONPATH and so loads the
`sitecustomize` hook), cannot create sockets. Residual risk: a child started with `python -I` or `-S`
ignores PYTHONPATH/site hooks and is NOT blocked. Our own launches (e.g. the scorecard subprocess)
must therefore never use -I or -S. Non-Python children are out of scope for this guard.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent / "_offline_hook"


def install() -> None:
    """Block sockets now; export the flag plus a start-up hook so child interpreters inherit the block."""
    os.environ["PETS_OFFLINE"] = "1"
    parts = [p for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p]
    if str(HOOK_DIR) not in parts:
        os.environ["PYTHONPATH"] = os.pathsep.join([str(HOOK_DIR), *parts])
    if str(HOOK_DIR) not in sys.path:
        sys.path.insert(0, str(HOOK_DIR))
    import runpy

    runpy.run_path(str(HOOK_DIR / "sitecustomize.py"))
