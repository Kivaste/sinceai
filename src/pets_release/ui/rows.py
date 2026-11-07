"""Protected previews: fresh CLI verification, manifest membership and exact-byte snapshots.

No source-data path is accepted here. The caller supplies only its current published release.
"""
from __future__ import annotations

import hashlib
import io
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

from pets_release.manifest import loads_strict, validate_manifest_file

LABEL = "Synthetic kit data © Since AI ry, CC BY 4.0. In a real deployment only the recipient sees this view."


def _verify(release, env):
    result = subprocess.run([sys.executable, "-m", "pets_release", "verify", str(release)],
                            env=env, capture_output=True, timeout=120, check=False)
    if result.returncode != 0:
        raise ValueError("Preview verification failed")


def protected_rows(release: Path, root: Path, env: dict, *, name=None, limit=10):
    """Return first N rows in release order, or raise. Unknown/error/timeout never serves rows."""
    if not 1 <= limit <= 25 or release.is_symlink() or release.is_junction():
        raise ValueError("Preview unavailable")
    release = release.resolve(strict=True)
    if release.parent != root or release == root:
        raise ValueError("Preview outside release root")
    manifest_path = release / "privacy_manifest.json"
    if manifest_path.is_symlink() or manifest_path.resolve(strict=True).parent != release:
        raise ValueError("Manifest outside release")
    if validate_manifest_file(release):
        raise ValueError("Invalid manifest")
    manifest_bytes = manifest_path.read_bytes()
    manifest = loads_strict(manifest_bytes)
    files = manifest["bindings"]["files"]
    if name is not None and name not in files:
        raise ValueError("Unlisted preview file")
    # Reject aliases and prohibited names even if a planted manifest lists one.
    for filename in files:
        if (not re.fullmatch(r"[A-Za-z0-9_]{1,64}\.csv", filename)
                or filename.lower().startswith("rowmap_") or filename.lower() == "truth.csv"):
            raise ValueError("Prohibited preview file")
        path = release / filename
        if path.is_symlink() or path.resolve(strict=True).parent != release:
            raise ValueError("Preview file outside release")
    _verify(release, env)
    # Verify the exact immutable bytes we will parse, too: a writer cannot swap a table
    # between the live verify and the read. No check result is cached or manufactured.
    payloads = {}
    with tempfile.TemporaryDirectory(prefix="pets-ui-preview-") as temporary:
        snapshot = Path(temporary)
        (snapshot / "privacy_manifest.json").write_bytes(manifest_bytes)
        for filename, digest in sorted(files.items()):
            payload = (release / filename).read_bytes()
            if hashlib.sha256(payload).hexdigest() != digest:
                raise ValueError("Preview digest mismatch")
            (snapshot / filename).write_bytes(payload)
            payloads[filename] = payload
        if manifest_path.read_bytes() != manifest_bytes:
            raise ValueError("Manifest changed during preview")
        _verify(snapshot, env)
    tables = []
    for filename in sorted(files) if name is None else [name]:
        frame = pd.read_csv(io.BytesIO(payloads[filename]), dtype=str, keep_default_na=False,
                            na_filter=False, nrows=limit)
        tables.append({"file": filename, "columns": list(frame.columns), "rows": frame.values.tolist()})
    return {"label": LABEL, "tables": tables}
