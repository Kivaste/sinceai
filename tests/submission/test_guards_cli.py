"""Guards on the built tree (planted files) and the real CLI.

Failure rows (trigger -> result):
  built tree has an unlisted file / dir / link          -> layout refused
  built tree has a truth/, Briefs/, .env, *.key entry   -> layout refused
  a packaged file contains key material                 -> refused
  CLI: no --out / no key / no kit / no --release        -> exit 2
  CLI: out inside the public repo                       -> exit 1, nothing written
  CLI: tampered release                                 -> exit 1, nothing written
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from sub_helpers import TEST_KEY, submission

from pets_release.pseudonym import MasterKey
from pets_release.submission import SubmissionRefused
from pets_release.submission.guards import check_layout, scan_key_material

REPO = Path(__file__).resolve().parents[2]
EXPECTED = {"a.csv", "d/b.csv", "d/rowmap_b.csv"}


def _tree(root: Path, files=EXPECTED):
    for f in files:
        p = root / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x\n", encoding="utf-8")
    return root


def test_layout_accepts_exactly_the_expected_files(tmp_path):
    check_layout(_tree(tmp_path / "t"), EXPECTED)


@pytest.mark.parametrize("planted", ["truth/id.csv", "d/truth/x.csv", "Briefs/x.csv", ".env", "d/k.key", "d/k.pem",
                                     "rowmap_stray.csv", "d/extra.csv", "d/rowmap_other.csv", "empty/"])
def test_layout_refuses_planted_entries(tmp_path, planted):
    root = _tree(tmp_path / "t")
    if planted.endswith("/"):
        (root / planted).mkdir()
    else:
        (root / planted).parent.mkdir(parents=True, exist_ok=True)
        (root / planted).write_text("x\n", encoding="utf-8")
    with pytest.raises(SubmissionRefused) as e:
        check_layout(root, EXPECTED)
    assert e.value.code == "layout"


def test_layout_refuses_a_missing_expected_file(tmp_path):
    root = _tree(tmp_path / "t", EXPECTED - {"a.csv"})
    with pytest.raises(SubmissionRefused):
        check_layout(root, EXPECTED)


def test_layout_refuses_a_symlink(tmp_path):
    root = _tree(tmp_path / "t")
    (root / "a.csv").unlink()
    target = tmp_path / "elsewhere.csv"
    target.write_text("x\n", encoding="utf-8")
    try:
        os.symlink(target, root / "a.csv")
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(SubmissionRefused):
        check_layout(root, EXPECTED)


def test_key_material_scan_finds_the_key_in_any_packaged_file(tmp_path):
    root = _tree(tmp_path / "t")
    master = MasterKey.from_text(TEST_KEY)
    scan_key_material(root, master)  # clean tree passes
    (root / "d" / "b.csv").write_bytes(b"a,b\n1," + TEST_KEY.encode() + b"\n")
    with pytest.raises(SubmissionRefused) as e:
        scan_key_material(root, master)
    assert e.value.code == "key_material"


def test_key_material_scan_finds_hex_encoded_key(tmp_path):
    root = _tree(tmp_path / "t")
    master = MasterKey.from_text(TEST_KEY)
    (root / "a.csv").write_text(master._k.hex(), encoding="utf-8")
    with pytest.raises(SubmissionRefused):
        scan_key_material(root, master)


@pytest.mark.parametrize("form", ["signing-raw", "master-hex-upper", "signing-b64url-unpadded"])
def test_key_material_scan_finds_every_planted_form(tmp_path, form):
    """The scan reads keys only through the keys module (scannable_forms / occurs_in); every form still trips it."""
    import base64

    from pets_release.pseudonym import manifest_signing_key

    master = MasterKey.from_text(TEST_KEY)
    sk = manifest_signing_key(master)._k  # tests may read raw bytes; src may not (test_context_keys)
    data = {"signing-raw": b"x" + sk + b"y",
            "master-hex-upper": master._k.hex().upper().encode(),
            "signing-b64url-unpadded": base64.urlsafe_b64encode(sk).rstrip(b"=")}[form]
    root = _tree(tmp_path / "t")
    (root / "d" / "leak.bin").write_bytes(data)
    with pytest.raises(SubmissionRefused) as e:
        scan_key_material(root, master)
    assert e.value.code == "key_material"


# ---------- real CLI ----------

def test_cli_usage_errors_exit_2(world, tmp_path):
    kit, rel = world
    out = str(tmp_path / "s")
    assert submission("--release", str(rel), "--kit", str(kit)).returncode == 2           # no --out
    assert submission("--out", out, "--release", str(rel), "--kit", str(kit),
                      extra={"PETS_HMAC_KEY": ""}).returncode == 2                      # no key
    assert submission("--out", out, "--release", str(rel)).returncode == 2              # no kit
    # no --release is not a usage error: it refuses as incomplete (D46; test_completeness_cli)
    assert not Path(out).exists()


def test_cli_refuses_out_inside_the_public_repo(world):
    kit, rel = world
    out = REPO / "out" / "cli_submission_must_not_exist"
    p = submission("--out", str(out), "--release", str(rel), "--kit", str(kit))
    assert p.returncode == 1 and "out_in_public_repo" in p.stdout
    assert not out.exists()


def test_cli_refuses_a_tampered_release(fresh, tmp_path):
    kit, rel = fresh
    (rel / "ed_visits.csv").write_bytes((rel / "ed_visits.csv").read_bytes() + b"x")
    p = submission("--out", str(tmp_path / "s"), "--release", str(rel), "--kit", str(kit))
    assert p.returncode == 1 and "release_not_verified" in p.stdout
    assert not (tmp_path / "s").exists()
