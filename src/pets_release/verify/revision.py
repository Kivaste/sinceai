"""The tool revision this checkout runs at (bound as ``bindings.toolRevision``)."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_SHA1 = re.compile(r"^[0-9a-f]{40}$")


def current_tool_revision() -> str | None:
    """Git HEAD of the source tree holding this package, or None when it cannot be determined.

    Read from git itself, never from an environment variable or a file someone could plant. None means
    "unavailable", which ``verify --full`` treats as a failure.
    """
    root = Path(__file__).resolve().parents[3]
    try:
        out = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True,
                             encoding="utf-8", timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    rev = out.stdout.strip()
    return rev if out.returncode == 0 and _SHA1.match(rev) else None
