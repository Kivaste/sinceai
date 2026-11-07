"""Guards: where the submission may be written, what may go into it, and what must never be in it.

Every guard fails closed: a git answer that cannot be obtained is a refusal, never a pass.
"""
from __future__ import annotations

import base64
import csv
import io
import json
import os
import re
import subprocess
from collections.abc import Iterable
from pathlib import Path

from pets_release.kit import FORBIDDEN_DATASETS
from pets_release.pseudonym import MasterKey, manifest_signing_key
from pets_release.submission.errors import SubmissionRefused

FORBIDDEN_PARTS = frozenset({*FORBIDDEN_DATASETS, "briefs"})  # compared lower-case; the kit module names the forbidden dir
FORBIDDEN_SUFFIXES = (".key", ".pem", ".p12", ".pfx")
PUBLIC_REPO_ENV = "PETS_PUBLIC_REPO"  # extra public-repo roots, os.pathsep-separated
_GIT_TIMEOUT = 30


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, encoding="utf-8",
                              timeout=_GIT_TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError):
        raise SubmissionRefused("public_repo_unknown") from None


def _normalise_url(url: str) -> str:
    """``git@github.com:Org/repo.git`` and ``https://github.com/org/repo`` name the same repository."""
    u = url.strip().lower()
    u = re.sub(r"^[a-z+]+://", "", u)
    u = re.sub(r"^[^@/]+@", "", u)
    u = u.replace(":", "/", 1) if re.match(r"^[^/]+:[^/]", u) else u
    u = re.sub(r"\.git$", "", u).rstrip("/")
    return u


def _remote_urls(repo: Path) -> set[str]:
    r = _git(repo, "config", "--get-regexp", r"^remote\..*\.url$")
    if r.returncode == 1 and not r.stdout.strip():
        return set()  # no remotes configured
    if r.returncode != 0:
        raise SubmissionRefused("public_repo_unknown")
    return {_normalise_url(line.split(None, 1)[1]) for line in r.stdout.splitlines() if " " in line}


def _package_checkout() -> Path:
    return Path(__file__).resolve().parents[3]


def public_repo(checkout: Path | None = None) -> tuple[list[Path], str]:
    """(every work tree of the public repo, normalised origin URL), asked of git; unknown refuses."""
    start = Path(checkout) if checkout is not None else _package_checkout()
    top = _git(start, "rev-parse", "--show-toplevel")
    if top.returncode != 0 or not top.stdout.strip():
        raise SubmissionRefused("public_repo_unknown")
    roots = {Path(top.stdout.strip()).resolve()}
    wt = _git(start, "worktree", "list", "--porcelain")
    if wt.returncode != 0:
        raise SubmissionRefused("public_repo_unknown")
    roots |= {Path(line[len("worktree "):]).resolve() for line in wt.stdout.splitlines()
              if line.startswith("worktree ")}
    roots |= {Path(p).resolve() for p in os.environ.get(PUBLIC_REPO_ENV, "").split(os.pathsep) if p}
    origin = _git(start, "config", "--get", "remote.origin.url")
    if origin.returncode != 0 or not origin.stdout.strip():
        raise SubmissionRefused("public_repo_unknown")
    return sorted(roots), _normalise_url(origin.stdout)


def _enclosing_repos(path: Path) -> list[Path]:
    """Every directory from ``path`` (or its nearest existing ancestor) up to the filesystem root that holds a
    ``.git`` entry: a nested repository must not hide an outer public clone."""
    p = path
    while not p.exists():
        if p.parent == p:
            return []
        p = p.parent
    return [d for d in (p, *p.parents) if (d / ".git").exists()]


def refuse_inside_public_repo(out: Path, checkout: Path | None = None) -> None:
    """Refuse ``out`` inside any work tree of the public repo, or inside any repository (at any nesting level)
    whose remote is the public repo's origin (a clone elsewhere). Nothing is created."""
    roots, origin = public_repo(checkout)
    real = Path(out).resolve()
    if any(real == r or r in real.parents for r in roots):
        raise SubmissionRefused("out_in_public_repo")
    for repo in _enclosing_repos(real):
        if origin in _remote_urls(repo):
            raise SubmissionRefused("out_in_public_repo")


def refuse_forbidden_source(path: Path) -> Path:
    """A release (or its scoring folder) must not come from under a ``Briefs`` or forbidden kit directory."""
    try:
        real = Path(path).resolve(strict=True)
    except (OSError, RuntimeError):
        raise SubmissionRefused("release_missing") from None
    if any(x.lower() in FORBIDDEN_PARTS for x in real.parts):
        raise SubmissionRefused("forbidden_source_path")
    return real


def _is_link(p: Path) -> bool:
    return p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction())


def check_layout(root: Path, expected: Iterable[str]) -> None:
    """The built tree is exactly the ``expected`` files (posix paths relative to ``root``): no other file,
    empty directory or link, and nothing named like a forbidden kit folder (`FORBIDDEN_PARTS`), a key or an env file. Row maps are
    allowed only at the expected paths."""
    root = Path(root)
    want = set(expected)
    seen: set[str] = set()
    dirs_ok = {""} | {p for f in want for p in _ancestors(f)}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        here = Path(dirpath)
        rel_dir = here.relative_to(root).as_posix()
        rel_dir = "" if rel_dir == "." else rel_dir
        for d in dirnames:
            sub = here / d
            rel = f"{rel_dir}/{d}" if rel_dir else d
            if _is_link(sub) or rel not in dirs_ok or d.lower() in FORBIDDEN_PARTS:
                raise SubmissionRefused("layout")
        for f in filenames:
            p = here / f
            rel = f"{rel_dir}/{f}" if rel_dir else f
            low = f.lower()
            if _is_link(p) or rel not in want or low.startswith(".env") or low.endswith(FORBIDDEN_SUFFIXES):
                raise SubmissionRefused("layout")
            seen.add(rel)
    if seen != want:
        raise SubmissionRefused("layout")


def _ancestors(rel: str) -> list[str]:
    parts = rel.split("/")[:-1]
    return ["/".join(parts[:i + 1]) for i in range(len(parts))]


def key_needles(master: MasterKey) -> list[bytes]:
    out = []
    for k in (master._k, manifest_signing_key(master)._k):
        out += [k, k.hex().encode(), k.hex().upper().encode(), base64.b64encode(k), base64.urlsafe_b64encode(k)]
    return sorted(set(out))


def _squash(s: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", s)


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _strings(k)
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def _decoded_strings(p: Path, data: bytes):
    """Every string a reader of the file would recover: CSV cells, JSON(L) strings, or text lines."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    suffix = p.suffix.lower()
    if suffix == ".csv":
        csv.field_size_limit(1 << 30)
        for row in csv.reader(io.StringIO(text, newline="")):
            yield from row
    elif suffix in (".json", ".jsonl"):
        for line in ([text] if suffix == ".json" else text.splitlines()):
            if not line.strip():
                continue
            try:
                yield from _strings(json.loads(line))
            except ValueError:
                yield line
    else:
        yield from text.splitlines()


def scan_key_material(root: Path, master: MasterKey) -> None:
    """No file under ``root`` may contain the master or manifest-signing key, in any encoding: raw bytes, hex or
    base64, and also in the decoded cells/strings (CSV and JSON escaping cannot hide it) with separators and
    quotes ignored."""
    needles = key_needles(master)
    texts = []
    for n in needles:
        try:
            texts.append(n.decode("ascii"))
        except UnicodeDecodeError:
            continue
    squashed = sorted({q for q in (_squash(t) for t in texts) if len(q) >= 16})
    shortest = min((len(q) for q in squashed), default=0)
    for p in sorted(Path(root).rglob("*")):
        if not p.is_file():
            continue
        data = p.read_bytes()
        if any(n in data for n in needles):
            raise SubmissionRefused("key_material")
        for s in _decoded_strings(p, data):
            if len(s) >= shortest and any(q in _squash(s) for q in squashed):
                raise SubmissionRefused("key_material")