"""Subprocess transport: the only network path of the product, exempt from the offline guard.

The parent process keeps its socket block. The request is sent by a child (`sender.py`) whose environment
lacks the offline flag and hook; nothing else in the product gets that environment.
"""
from __future__ import annotations

import os
import subprocess
import sys

from pets_release.offline import HOOK_DIR


def sender_env(base: dict[str, str] | None = None) -> dict[str, str]:
    """A copy of `base` (default os.environ) without the offline flag and hook. The input is not modified."""
    env = dict(os.environ if base is None else base)
    env.pop("PETS_OFFLINE", None)
    hook = os.path.normcase(str(HOOK_DIR))
    parts = [p for p in env.get("PYTHONPATH", "").split(os.pathsep) if p and os.path.normcase(p) != hook]
    if parts:
        env["PYTHONPATH"] = os.pathsep.join(parts)
    else:
        env.pop("PYTHONPATH", None)
    return env


def subprocess_transport(url: str, body: bytes, api_key: str, timeout: float) -> bytes:
    env = sender_env()
    env["PETS_LLM_SEND_URL"] = url
    env["PETS_LLM_SEND_TIMEOUT"] = str(timeout)
    env["PETS_LLM_API_KEY"] = api_key
    proc = subprocess.run(
        [sys.executable, "-m", "pets_release.llm.sender"],
        input=body,
        capture_output=True,
        env=env,
        timeout=timeout + 15,
        check=False,
    )
    if proc.returncode != 0:
        raise OSError(f"sender exited {proc.returncode}")
    return proc.stdout
