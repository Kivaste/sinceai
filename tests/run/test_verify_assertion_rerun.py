"""Verify re-applies the writer's assertion-evidence rule to every fresh record (issue #59).

Rule: an export assertion ``false`` is verified only if its named check's fresh record is ``pass`` with
``hits == 0``, no violations and ``n >= 1`` (the writer's own ``assertion_reason``), and that fresh record equals
the attested ``assertionEvidence`` entry. A ``pass`` with low-severity hits is not absence.

Rows (trigger -> result), real CLI on a real-CLI synthetic release, synthetic rows only:
  private-use IP planted in a released text cell, digests rebound, re-signed with the test key
      (fresh rescan.ip-addresses: pass, hits=1)        -> limited verify exit 1, names ipAddresses
                                                       -> full verify exit 1, names ipAddresses
  unmodified release                                   -> both tiers exit 0 (the rule does not over-trigger)
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import shutil

from run_helpers import TEST_KEY, cli

from pets_release.manifest import canonical_bytes, compute_signature
from pets_release.pseudonym import MasterKey, manifest_signing_key

MANIFEST = "privacy_manifest.json"
PLANTED_IP = "10.0.0.7"  # private-use: low severity for rescan.ip-addresses / text.ip-addresses


def resign(release) -> None:
    """Rebind every file digest and re-sign with the published test key (isolates verify from the signature)."""
    m = json.loads((release / MANIFEST).read_text(encoding="utf-8"))
    m["bindings"]["files"] = {f: hashlib.sha256((release / f).read_bytes()).hexdigest()
                              for f in sorted(m["bindings"]["files"])}
    sk = manifest_signing_key(MasterKey.from_text(TEST_KEY))
    m["signature"]["value"] = "0" * 64
    m["signature"]["value"] = compute_signature(m, sk)
    (release / MANIFEST).write_bytes(canonical_bytes(m))


def set_cell(release, name: str, column: str, value: str, row: int = 0) -> None:
    text = (release / name).read_text(encoding="utf-8")
    rows = list(csv.reader(io.StringIO(text, newline="")))
    rows[row + 1][rows[0].index(column)] = value
    out = io.StringIO(newline="")
    csv.writer(out, lineterminator="\n").writerows(rows)
    (release / name).write_bytes(out.getvalue().encode("utf-8"))


def copy_release(released, tmp_path):
    kit, out, proc = released
    assert proc.returncode == 0, proc.stdout + proc.stderr
    rel = tmp_path / "rel"
    shutil.copytree(out, rel)
    return kit, rel


def test_unmodified_release_verifies_in_both_tiers(released, tmp_path):
    kit, rel = copy_release(released, tmp_path)
    assert cli("verify", str(rel)).returncode == 0
    full = cli("verify", "--full", "--kit", str(kit), str(rel))
    assert full.returncode == 0, full.stdout


def test_pass_with_low_hit_cannot_back_assertion_in_either_tier(released, tmp_path):
    kit, rel = copy_release(released, tmp_path)
    set_cell(rel, "lab_results.csv", "unit", PLANTED_IP)  # a released text column (test_name is withheld, #106)
    resign(rel)
    m = json.loads((rel / MANIFEST).read_text(encoding="utf-8"))
    assert m["exportAssertions"]["ipAddresses"] is False and m["assertionEvidence"]["ipAddresses"]["hits"] == 0

    lim = cli("verify", str(rel))
    assert lim.returncode == 1, lim.stdout
    assert "ipAddresses" in lim.stdout, lim.stdout
    assert PLANTED_IP not in lim.stdout + lim.stderr

    full = cli("verify", "--full", "--kit", str(kit), str(rel))
    assert full.returncode == 1, full.stdout
    assert "ipAddresses" in full.stdout, full.stdout
    assert "VERIFIED" not in full.stdout.replace("VERIFY FAILED", "")
