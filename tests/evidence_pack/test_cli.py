"""Evidence pack rules at the real CLI seam; hand-made manifest fixture only."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from html import unescape
from pathlib import Path

import pytest

from pets_release.manifest import canonical_bytes, compute_signature, loads_strict
from pets_release.manifest.value_scan import identifier_shape_counts
from pets_release.pseudonym import MasterKey, manifest_signing_key

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "manifest" / "release" / "privacy_manifest.json"
KEY = "synthetic-evidence-pack-master-key-only"
HEADINGS = (
    "Purpose and recipient", "Legal basis and DPIA", "Method and parameters",
    "Measured re-identification risk against stated attackers", "Utility justification",
    "Residual risks", "Reproducibility and integrity",
)


def write_manifest(release, manifest):
    signing = manifest_signing_key(MasterKey.from_text(KEY))
    manifest["signature"] = {"alg": "HMAC-SHA256", "keyId": signing.key_id(),
                             "value": compute_signature(manifest, signing)}
    (release / "privacy_manifest.json").write_bytes(canonical_bytes(manifest))


@pytest.fixture()
def release(tmp_path):
    release = tmp_path / "release"
    release.mkdir()
    write_manifest(release, loads_strict(FIXTURE.read_bytes()))
    return release


def run_pack(release, out, *, key=KEY, source=None):
    env = dict(os.environ, PETS_HMAC_KEY=key)
    if source is not None:
        env["PYTHONPATH"] = str(source)
    return subprocess.run([sys.executable, "-m", "pets_release", "evidence-pack", str(release), "--out", str(out)],
                          env=env, capture_output=True, text=True, encoding="utf-8", timeout=30, check=False)


def test_every_section_renders_from_signed_manifest_alone(release, tmp_path):
    out = tmp_path / "pack.html"
    result = run_pack(release, out)
    assert result.returncode == 0, result.stderr
    for path in (out, out.with_suffix(".md")):
        text = path.read_text(encoding="utf-8")
        for heading in HEADINGS:
            assert heading in text
        assert "To be supplied by the data controller" in text
        assert "no differential privacy used" in text
        assert "H-U8" in text and "age_band" in text
        assert "verify --full" in text


@pytest.mark.parametrize("measurement", ["privacy", "utility"])
def test_absent_measurement_never_silently_disappears(release, tmp_path, measurement):
    manifest = loads_strict((release / "privacy_manifest.json").read_bytes())
    manifest["measured"][measurement] = {"status": "not_measured", "reason": "synthetic scoring not run"}
    write_manifest(release, manifest)
    out = tmp_path / "pack.html"
    assert run_pack(release, out).returncode == 0
    for path in (out, out.with_suffix(".md")):
        text = path.read_text(encoding="utf-8")
        section = text.split("4. Measured" if measurement == "privacy" else "5. Utility")[1].split("6. Residual")[0]
        assert "not measured: synthetic scoring not run" in section


def test_generic_and_persona_risks_and_missing_k_sets_are_explicit(release, tmp_path):
    manifest = loads_strict((release / "privacy_manifest.json").read_bytes())
    for name, kind in (("linkage-broker", "linkage"), ("linkage-broker-public", "linkage"),
                       ("linkage-insider", "linkage"), ("attribute-inference-insider", "attribute_inference")):
        manifest["residualRisks"].append({"risk": name, "kind": kind, "label": None,
                                        "rate": {"status": "not_measured", "reason": "persona evaluation not run"},
                                        "description": "Synthetic attacker capability statement"})
    manifest["residualRisks"].sort(key=lambda r: r["risk"])
    write_manifest(release, manifest)
    out = tmp_path / "pack.md"
    assert run_pack(release, out).returncode == 0
    section = out.read_text(encoding="utf-8").split("## 4.")[1].split("## 5.")[0]
    for name in ("linkage-broker", "linkage-broker-public", "linkage-insider", "attribute-inference-insider"):
        assert name in section
    assert "not measured: persona evaluation not run" in section
    assert "k on scenario QIs: not measured" in section
    assert "k on all kept catalogued QIs: not measured" in section


@pytest.mark.parametrize("tamper", ["prose", "signature", "contract", "missing-key", "wrong-key"])
def test_tampered_or_unauthenticated_manifest_refuses_even_with_planted_pass(release, tmp_path, tamper):
    manifest = loads_strict((release / "privacy_manifest.json").read_bytes())
    key = KEY
    if tamper == "prose":
        manifest["fitFor"][0]["reason"] = "Changed after signing"
    elif tamper == "signature":
        manifest["signature"]["value"] = "a" * 64
    elif tamper == "contract":
        manifest["bindings"]["contractDigest"] = "b" * 64
    elif tamper == "missing-key":
        key = ""
    else:
        key = "wrong-synthetic-master-key-not-the-signer"
    (release / "privacy_manifest.json").write_bytes(canonical_bytes(manifest))
    (release / "verified.json").write_text('{"pass":true}', encoding="utf-8")
    out = tmp_path / "pack.html"
    result = run_pack(release, out, key=key)
    assert result.returncode != 0
    assert not out.exists() and not out.with_suffix(".md").exists()
    assert "Changed after signing" not in result.stderr


def test_output_passes_production_shape_scan_and_planted_identifier_does_not(release, tmp_path):
    out = tmp_path / "pack.html"
    assert run_pack(release, out).returncode == 0
    for path in (out, out.with_suffix(".md")):
        text = unescape(path.read_text(encoding="utf-8"))
        assert identifier_shape_counts(text) == {}
        assert identifier_shape_counts(text + "\nfixture.person@example.org")


def test_planted_renderer_value_is_refused_by_cli_output_scan(release, tmp_path):
    """Plant in a temporary source copy: the real CLI must actually execute its final scan."""
    source = tmp_path / "src"
    shutil.copytree(Path(__file__).resolve().parents[2] / "src", source)
    renderer = source / "pets_release" / "evidence_pack" / "render.py"
    renderer.write_text(renderer.read_text(encoding="utf-8").replace(
        '</body></html>', 'fixture.person@example.org</body></html>'), encoding="utf-8")
    out = tmp_path / "pack.html"
    result = run_pack(release, out, source=source)
    assert result.returncode == 1
    assert "identifier shape in rendered output" in result.stderr
    assert not out.exists() and not out.with_suffix(".md").exists()


@pytest.mark.parametrize("suffix", [".html", ".md"])
def test_output_cannot_modify_the_release_even_with_planted_destination(release, suffix):
    out = release / ("planted" + suffix)
    out.write_text("Existing audit material", encoding="utf-8")
    result = run_pack(release, out)
    assert result.returncode == 2
    assert out.read_text(encoding="utf-8") == "Existing audit material"


def test_purpose_statuses_and_null_measurements_are_honest(release, tmp_path):
    m = loads_strict((release / "privacy_manifest.json").read_bytes())
    m["measured"]["utility"]["tasks"] = [
        {"task": "H-U2", "status": "ok", "before": 1, "after": .95},
        {"task": "H-U4", "status": "ok", "before": 1, "after": .8},
        {"task": "H-U6", "status": "ok", "before": 1, "after": .2},
        {"task": "H-U7", "status": "ok", "before": None, "after": None},
        {"task": "H-U8", "status": "error", "before": 1, "after": None},
    ]
    m["sacrifices"] = [{"check": "H-U4", "floor": .7, "before": 1, "after": .8, "reason": "Synthetic sacrifice"}]
    write_manifest(release, m)
    out = tmp_path / "pack.md"
    result = run_pack(release, out)
    assert result.returncode == 0, result.stderr
    text = out.read_text(encoding="utf-8")
    for expected in ("H-U2: met", "H-U4: accepted sacrifice", "H-U6: failed", "H-U7: not measured", "H-U8: failed"):
        assert expected in text
    assert "before=not measured:" in text and "after=not measured:" in text
    assert "before=None" not in text and "after=None" not in text


def test_missing_before_score_cannot_be_reported_met(release, tmp_path):
    m = loads_strict((release / "privacy_manifest.json").read_bytes())
    m["measured"]["utility"]["tasks"][0]["before"] = None
    write_manifest(release, m)
    out = tmp_path / "pack.md"
    assert run_pack(release, out).returncode == 0
    task = m["measured"]["utility"]["tasks"][0]["task"]
    assert f"{task}: not measured" in out.read_text(encoding="utf-8")


def test_missing_method_record_and_section_statuses_are_explicit(release, tmp_path):
    m = loads_strict((release / "privacy_manifest.json").read_bytes())
    m["pets"] = [p for p in m["pets"] if p["pet"] != "local_suppression"]
    write_manifest(release, m)
    out = tmp_path / "pack.md"
    result = run_pack(release, out)
    assert result.returncode == 0
    assert "Local suppression: not measured: not recorded in the signed manifest" in out.read_text(encoding="utf-8")
    for heading in HEADINGS:
        assert heading in result.stdout
    assert "Legal basis and DPIA: to be supplied" in result.stdout


def test_residual_risk_prose_is_verbatim_not_json_escaped(release, tmp_path):
    m = loads_strict((release / "privacy_manifest.json").read_bytes())
    description = 'A "quoted" risk & limitation'
    m["residualRisks"][0]["description"] = description
    m["residualRisks"][0]["rate"] = {"status": "not_measured", "reason": "synthetic rate unavailable"}
    write_manifest(release, m)
    out = tmp_path / "pack.html"
    result = run_pack(release, out)
    assert result.returncode == 0, result.stderr
    for path, start, end in ((out, 'id="section-6"', 'id="section-7"'),
                             (out.with_suffix(".md"), "## 6.", "## 7.")):
        section = unescape(path.read_text(encoding="utf-8")).split(start)[1].split(end)[0]
        assert description in section
        assert "not measured: synthetic rate unavailable" in section
