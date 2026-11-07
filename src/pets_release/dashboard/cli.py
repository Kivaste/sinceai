"""``pets-release dashboard <release_dir> [--out <html>]``.

Reads only ``privacy_manifest.json`` (validated first; an invalid manifest exits 1 and writes nothing), never the
release tables. Writes the HTML and a before/after CSV next to it (same stem, ``.csv``). Exit 0 ok, 1 invalid
manifest, 2 usage error.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from pets_release.dashboard.render import render_csv, render_html
from pets_release.manifest import loads_strict, validate_manifest_file
from pets_release.offline import entry_point

MANIFEST = "privacy_manifest.json"


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: error: {message}\n")


@entry_point
def main(argv: list[str]) -> int:
    p = _Parser(prog="pets-release dashboard", description="render the judge dashboard from the manifest")
    p.add_argument("release_dir")
    p.add_argument("--out", help="HTML output path (default: ./dashboard.html); the CSV goes next to it")
    try:
        a = p.parse_args(argv)
    except SystemExit as e:
        return 0 if e.code == 0 else 2  # --help exits 0; anything else, including None, is a usage error
    release = Path(a.release_dir)
    manifest_path = release / MANIFEST
    if not manifest_path.is_file():
        print(f"pets-release dashboard: no {MANIFEST} in {release}", file=sys.stderr)
        return 2
    errors = validate_manifest_file(release)
    if errors:
        print("pets-release dashboard: manifest is invalid; nothing written", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1
    manifest = loads_strict(manifest_path.read_bytes())
    out = Path(a.out) if a.out else Path("dashboard.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        base = os.path.relpath(release.resolve(), out.parent.resolve()).replace("\\", "/")
    except ValueError:  # different drive on Windows: fall back to an absolute file link
        base = release.resolve().as_uri()
    html = render_html(manifest, files_base=base)
    csv_path = out.with_suffix(".csv")
    out.write_text(html, encoding="utf-8", newline="\n")
    csv_path.write_text(render_csv(manifest), encoding="utf-8", newline="\n")
    print(f"dashboard: wrote {out} and {csv_path}")
    return 0
