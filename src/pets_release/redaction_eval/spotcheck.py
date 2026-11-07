"""Local-only spot-check sheet. Never inside a repo tree unless git-ignored (fails closed)."""
from __future__ import annotations

import csv
import hashlib
import subprocess
from pathlib import Path


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _find_repo(start: Path):
    p = start.resolve()
    for d in (p, *p.parents):
        if (d / ".git").exists():
            return d
    return None


def _git_ignored(path: Path, root: Path) -> bool:
    try:
        r = subprocess.run(["git", "-C", str(root), "check-ignore", "-q", str(path.resolve())],
                           capture_output=True, check=False)
    except OSError:
        return False  # git unavailable = unknown = not ignored
    return r.returncode == 0  # only exit 0 counts


def check_destination(path, repo_root=None) -> None:
    """Refuse a destination inside any repo (detected from the target, the cwd, and an optional
    explicit root; an explicit root never disables detection) unless git ignores it."""
    path = Path(path)
    anchor = path.resolve().parent
    while not anchor.exists() and anchor != anchor.parent:
        anchor = anchor.parent
    roots = {r for r in (_find_repo(anchor), _find_repo(Path.cwd()),
                         Path(repo_root).resolve() if repo_root else None) if r is not None}
    for r in roots:
        if _inside(path, r) and not _git_ignored(path, r):
            raise ValueError("spot-check sheet must be outside the repo tree or in a git-ignored folder")


def redact_text(text: str, spans) -> str:
    out, pos = [], 0
    for s in sorted(spans, key=lambda s: (s["start"], s["end"])):
        if s["start"] < pos:
            continue
        out.append(text[pos:s["start"]])
        out.append(f"[{s['label']}]")
        pos = s["end"]
    out.append(text[pos:])
    return "".join(out)


def export_spot_check(frame, pred: dict, path, n: int = 200, repo_root=None, ids=None) -> int:
    """Write the sheet; returns the number of rows actually written."""
    path = Path(path)
    check_destination(path, repo_root)
    pool = sorted(ids if ids is not None else frame.texts)
    pool.sort(key=lambda t: hashlib.sha256(t.encode()).hexdigest())
    pick = pool[:n]
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["turn_id", "original", "redacted", "missed", "over_redacted"])
        for tid in pick:
            text = frame.texts[tid]
            w.writerow([tid, text, redact_text(text, pred.get(tid, [])), "", ""])
    return len(pick)
