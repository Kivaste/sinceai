"""CLI-level harness for end-to-end determinism and offline tests. Synthetic data only.

Runs `python -m pets_release ...` in a subprocess with a pinned environment and compares whole
folders byte-for-byte. Nothing here imports product code.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
PYTHON = sys.executable
CREATED = "2026-11-07T00:00:00Z"
TEST_KEY = "e2e-test-key-" + "k" * 32  # test key; never a real one
SCENARIO = "HEALTH-S1"

_INHERIT = (
    "PATH", "SYSTEMROOT", "PATHEXT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "APPDATA",
    "LOCALAPPDATA", "HOMEDRIVE", "HOMEPATH", "COMSPEC", "VIRTUAL_ENV",
)


def pinned_env(extra: dict[str, str] | None = None, hashseed: str = "0") -> dict[str, str]:
    """Minimal environment: no inherited PETS_*/SOURCE_DATE_EPOCH, fixed UTF-8/TZ/bytecode flags."""
    import os

    env = {k: os.environ[k] for k in _INHERIT if k in os.environ}
    env.update(
        PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1", TZ="UTC", PYTHONIOENCODING="utf-8",
        PYTHONPATH=str(SRC), PYTHONHASHSEED=hashseed, PETS_HMAC_KEY=TEST_KEY,
    )
    if extra:
        env.update(extra)
    return env


def run_cli(args: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None,
            hashseed: str = "0") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [PYTHON, "-m", "pets_release", *args],
        cwd=cwd or ROOT, env=pinned_env(env, hashseed), capture_output=True, text=True,
        encoding="utf-8", check=False,
    )


def run_release(kit: Path, out: Path, *, created: str = CREATED, scenario: str = SCENARIO,
                key: str | None = None, cwd: Path | None = None, hashseed: str = "0",
                extra_args: list[str] | None = None) -> subprocess.CompletedProcess[str]:
    """`pets-release run` with a fixed --created and test key."""
    env = {"PETS_HMAC_KEY": key} if key is not None else None
    args = ["run", "--scenario", scenario, "--plan", "hand", "--kit", str(kit), "--out", str(out),
            "--created", created]
    return run_cli(args + (extra_args or []), cwd=cwd, env=env, hashseed=hashseed)


def run_python(code: str, *args: str, env: dict[str, str] | None = None,
               cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run a snippet in a child with the pinned environment (used for planted network calls)."""
    return subprocess.run(
        [PYTHON, "-c", code, *args], cwd=cwd or ROOT, env=pinned_env(env), capture_output=True,
        text=True, encoding="utf-8", check=False,
    )


# ---- folder comparison -------------------------------------------------------------------------

@dataclass(frozen=True)
class Entry:
    kind: str  # "file" or "dir"
    sha256: str  # "" for dirs


def tree_digest(folder: Path) -> dict[str, Entry]:
    """Relative POSIX path -> Entry for every file and directory under `folder`, sorted."""
    folder = Path(folder)
    if not folder.is_dir():
        raise NotADirectoryError(str(folder))
    out: dict[str, Entry] = {}
    for p in sorted(folder.rglob("*"), key=lambda q: q.relative_to(folder).as_posix()):
        rel = p.relative_to(folder).as_posix()
        if p.is_symlink():
            raise ValueError(f"symlink in release folder: {rel}")
        if p.is_dir():
            out[rel] = Entry("dir", "")
        else:
            out[rel] = Entry("file", hashlib.sha256(p.read_bytes()).hexdigest())
    return out


def diff_trees(a: Path, b: Path) -> list[str]:
    """Human-readable differences (names and digests only, no content). Empty list = byte-identical."""
    da, db = tree_digest(a), tree_digest(b)
    diffs = [f"only in A: {k}" for k in sorted(da.keys() - db.keys())]
    diffs += [f"only in B: {k}" for k in sorted(db.keys() - da.keys())]
    for k in sorted(da.keys() & db.keys()):
        if da[k] != db[k]:
            diffs.append(f"differs: {k} ({da[k].kind} {da[k].sha256[:12]} vs {db[k].kind} {db[k].sha256[:12]})")
    return diffs


def digest_lines(folder: Path) -> list[str]:
    """`sha256  path` lines for the evidence report."""
    return [f"{e.sha256}  {k}" for k, e in tree_digest(folder).items() if e.kind == "file"]
