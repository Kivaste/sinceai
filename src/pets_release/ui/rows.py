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
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

from pets_release.manifest import loads_strict, validate_manifest_file

LABEL = "Synthetic kit data © Since AI ry, CC BY 4.0. In a real deployment only the recipient sees this view."


VERIFY_TIMEOUT = 900


def _verify_full(release, env, kit):
    """The signature-checking tier (D18/D20): limited verify accepts a re-bound digest with a
    stale signature, so it is never the display gate. Only exit 0 passes; anything else raises."""
    if not env.get("PETS_HMAC_KEY") or kit is None:
        raise ValueError("Full verification unavailable")
    result = subprocess.run([sys.executable, "-m", "pets_release", "verify", "--full", "--kit", str(kit),
                             str(release)], env=env, capture_output=True, timeout=VERIFY_TIMEOUT, check=False)
    if result.returncode != 0:
        raise ValueError("Display verification failed")


def verified_snapshot(release: Path, root: Path, env: dict, kit):
    """Copy the manifest and its listed files, full-verify that copy, return its exact bytes.

    The bytes returned are the bytes that passed ``verify --full`` with the server key, so a
    writer cannot swap a table or the manifest between the verify and the read.
    """
    with snapshot(release, root) as (copy, manifest_bytes, payloads):
        _verify_full(copy, env, kit)
    return manifest_bytes, payloads


@contextmanager
def snapshot(release: Path, root: Path):
    """Yield ``(folder, manifest_bytes, payloads)``: a private copy of the manifest and exactly
    its listed files, read once from the live release. Callers verify and project only this copy;
    the live folder is never re-read, so an A->B->A writer cannot change what was verified."""
    if release.is_symlink() or release.is_junction():
        raise ValueError("Release unavailable")
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
    # Reject aliases and prohibited names even if a planted manifest lists one.
    for filename in files:
        if (not re.fullmatch(r"[A-Za-z0-9_]{1,64}\.csv", filename)
                or filename.lower().startswith("rowmap_") or filename.lower() == "truth.csv"):
            raise ValueError("Prohibited preview file")
        path = release / filename
        if path.is_symlink() or path.resolve(strict=True).parent != release:
            raise ValueError("Preview file outside release")
    # The live folder must be exactly the manifest plus its listed files: a planted extra file
    # (row map, truth, anything) means this folder is not the verified release.
    if sorted(p.name for p in release.iterdir()) != sorted({"privacy_manifest.json", *files}):
        raise ValueError("Release folder has unlisted entries")
    # Verify the exact immutable bytes we will parse. No check result is cached or manufactured.
    payloads = {}
    with tempfile.TemporaryDirectory(prefix="pets-ui-verify-") as temporary:
        copy = Path(temporary)
        (copy / "privacy_manifest.json").write_bytes(manifest_bytes)
        for filename, digest in sorted(files.items()):
            payload = (release / filename).read_bytes()
            if hashlib.sha256(payload).hexdigest() != digest:
                raise ValueError("Preview digest mismatch")
            (copy / filename).write_bytes(payload)
            payloads[filename] = payload
        yield copy, manifest_bytes, payloads


def protected_rows(release: Path, root: Path, env: dict, kit, *, name=None, limit=10):
    """Return first N rows in release order, or raise. Unknown/error/timeout never serves rows."""
    if not 1 <= limit <= 25:
        raise ValueError("Preview unavailable")
    manifest_bytes, payloads = verified_snapshot(release, root, env, kit)
    files = loads_strict(manifest_bytes)["bindings"]["files"]
    if name is not None and name not in files:
        raise ValueError("Unlisted preview file")
    tables = []
    for filename in sorted(files) if name is None else [name]:
        frame = pd.read_csv(io.BytesIO(payloads[filename]), dtype=str, keep_default_na=False,
                            na_filter=False, nrows=limit)
        tables.append({"file": filename, "columns": list(frame.columns), "rows": frame.values.tolist()})
    return {"label": LABEL, "tables": tables}
