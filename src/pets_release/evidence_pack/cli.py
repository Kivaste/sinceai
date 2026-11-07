"""Evidence-pack CLI. Only privacy_manifest.json is ever read."""
from __future__ import annotations

import argparse
import sys
from html import unescape
from pathlib import Path

from pets_release.evidence_pack.render import render
from pets_release.manifest import canonical_bytes, loads_strict, validate_manifest
from pets_release.manifest.value_scan import identifier_shape_counts
from pets_release.offline import entry_point
from pets_release.pseudonym import KeyConfigError, MasterKey
from pets_release.verify.core import _signature_problems


@entry_point
def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="pets-release evidence-pack")
    parser.add_argument("release")
    parser.add_argument("--out", required=True, help=".html or .md output; both formats are written alongside")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 2
    out = Path(args.out)
    if out.suffix.lower() not in (".html", ".md"):
        print("evidence-pack: --out must end in .html or .md", file=sys.stderr)
        return 2
    outputs = (out.with_suffix(".html"), out.with_suffix(".md"))
    release = Path(args.release).resolve()
    if any(p.resolve().is_relative_to(release) for p in outputs):
        print("evidence-pack: --out must be outside the release folder", file=sys.stderr)
        return 2
    try:
        key = MasterKey.from_env()
    except KeyConfigError:
        print("evidence-pack: PETS_HMAC_KEY is required to authenticate the manifest", file=sys.stderr)
        return 2
    try:
        path = Path(args.release) / "privacy_manifest.json"
        raw = path.read_bytes()
        manifest = loads_strict(raw)
        if validate_manifest(manifest) or canonical_bytes(manifest) != raw:
            print("evidence-pack: invalid manifest; nothing written", file=sys.stderr)
            return 1
        if _signature_problems(manifest, key):
            print("evidence-pack: manifest signature failed; nothing written", file=sys.stderr)
            return 1
        html, markdown = render(manifest)
        if any(identifier_shape_counts(unescape(text)) for text in (html, markdown)):
            print("evidence-pack: identifier shape in rendered output; nothing written", file=sys.stderr)
            return 1
        out.parent.mkdir(parents=True, exist_ok=True)
        out.with_suffix(".html").write_text(html, encoding="utf-8", newline="\n")
        out.with_suffix(".md").write_text(markdown, encoding="utf-8", newline="\n")
    except (OSError, ValueError):
        print("evidence-pack: unreadable input or unwritable output; nothing certified", file=sys.stderr)
        return 1
    print("evidence-pack: rendered HTML and Markdown (manifest only)")
    return 0
