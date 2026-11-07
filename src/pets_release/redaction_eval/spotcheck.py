"""Local-only spot-check sheet. Never inside the repo tree unless git-ignored."""
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


def _git_ignored(path: Path, root: Path) -> bool:
    r = subprocess.run(["git", "-C", str(root), "check-ignore", "-q", str(path.resolve())],
                       capture_output=True)
    return r.returncode == 0  # only exit 0 counts; anything else is unknown = not ignored


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


def export_spot_check(frame, pred: dict, path, n: int = 200, repo_root=None, ids=None) -> Path:
    path = Path(path)
    if repo_root is not None and _inside(path, Path(repo_root)) and not _git_ignored(path, Path(repo_root)):
        raise ValueError("spot-check sheet must be outside the repo tree or in a git-ignored folder")
    pool = sorted(ids if ids is not None else frame.texts)
    pool.sort(key=lambda t: hashlib.sha256(t.encode()).hexdigest())
    pick = pool[:n]
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["turn_id", "original", "redacted", "missed", "over_redacted"])
        for tid in pick:
            text = frame.texts[tid]
            w.writerow([tid, text, redact_text(text, pred.get(tid, [])), "", ""])
    return path
