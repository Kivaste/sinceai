"""Subprocess transport: the only network path of the product, exempt from the offline guard.

The parent process keeps its socket block. The request is sent by a child (`sender.py`) whose environment
lacks the offline flag and hook; nothing else in the product gets that environment.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def sender_env(base: dict[str, str] | None = None) -> dict[str, str]:
    """Minimal sender environment; never inherit application secrets or Python hooks.

    The sender uses only the standard library. Its package path comes from this
    module's identity, not the parent's PYTHONPATH. Request settings and the API
    key are supplied explicitly by the transport, not copied from the parent.
    """
    source = os.environ if base is None else base
    required = ("PATH", "SYSTEMROOT", "TEMP") if os.name == "nt" else ("PATH",)
    if any(not source.get(name) for name in required):
        raise OSError("sender environment is missing a required OS variable")
    env = {name: source[name] for name in ("PATH", "SYSTEMROOT", "TEMP", "TMP") if name in source}
    env.update({
        "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
        "PYTHONUTF8": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "TZ": "UTC",
    })
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
