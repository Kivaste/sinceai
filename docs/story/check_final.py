"""Check submission text readiness, not the truth of its claims (review + proof do that)."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


REQUIRED = (
    "name.txt", "tagline.txt", "description.md", "built-with.txt",
    "pitch-4min.md", "video-script.md", "SOURCES.md",
)
LIMITS = {"name.txt": 80, "tagline.txt": 140, "description.md": 5000}


def problems(folder: Path) -> list[str]:
    """Content-free diagnostics for a final submission folder."""
    if not folder.is_dir():
        return ["missing final folder"]
    errors = [f"missing file: {name}" for name in REQUIRED if not (folder / name).is_file()]
    for path in sorted(folder.rglob("*")):
        if not path.is_file() or path.suffix not in (".md", ".txt"):
            continue
        name = path.relative_to(folder).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            errors.append(f"{name}: unreadable text")
            continue
        if not text.strip():
            errors.append(f"{name}: empty file")
        if "{{" in text or "}}" in text:
            errors.append(f"{name}: unresolved placeholder")
        if "<!--" in text or "-->" in text:
            errors.append(f"{name}: comment marker")
        if re.search(r"\b(?:IF\s+#\d+|END\s+IF)\b", text):
            errors.append(f"{name}: claim marker")
        if re.search(r"\b(?:TODO|TBD|FIXME)\b", text, re.IGNORECASE):
            errors.append(f"{name}: editorial note")
        if name == "description.md" and re.search(r"^\s*#{1,6}\s|^.+\n[=-]{3,}\s*$", text, re.MULTILINE):
            errors.append(f"{name}: description heading")
        if name in LIMITS and len(text) > LIMITS[name]:
            errors.append(f"{name}: over limit ({len(text)} > {LIMITS[name]})")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", nargs="?", type=Path, default=Path(__file__).resolve().parent / "final")
    args = parser.parse_args()
    errors = problems(args.folder)
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
