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
    assert "pending #138" not in section


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


@pytest.mark.parametrize("reason", ["Synthetic approved purpose", "Approved purpose; risk not measured"])
def test_purpose_and_recipient_are_rendered_statements_not_measurements(release, tmp_path, reason):
    """CLI seam: a policy statement must not acquire a measurement verdict from prose."""
    m = loads_strict((release / "privacy_manifest.json").read_bytes())
    m["fitFor"][0]["reason"] = reason
    write_manifest(release, m)
    out = tmp_path / "pack.md"
    result = run_pack(release, out)
    assert result.returncode == 0, result.stderr
    assert "Purpose and recipient: rendered" in result.stdout
    section = unescape(out.read_text(encoding="utf-8")).split("## 1.")[1].split("## 2.")[0]
    assert m["release"]["recipient"] in section
    assert "fitFor:" in section and "notFitFor:" in section
    assert reason in section
    assert "Trust level: not supplied in the signed manifest" in section
    assert "Trust level: not measured" not in section


def test_section_statuses_use_structured_fields_not_planted_prose(release, tmp_path):
    m = loads_strict((release / "privacy_manifest.json").read_bytes())
    m["fieldJustifications"][0]["reason"] = "Purpose retained; other risk not measured"
    m["measured"]["utility"]["source"] = "Purpose checks measured; unrelated risk not measured"
    m["measured"]["privacy"]["source"] = "Privacy scored; unrelated risk not measured"
    m["residualRisks"][0]["description"] = "Other risk not measured"
    m["residualRisks"][0]["rate"] = {"status": "not_measured", "reason": "synthetic rate unavailable"}
    write_manifest(release, m)
    out = tmp_path / "pack.md"
    result = run_pack(release, out)
    assert result.returncode == 0, result.stderr
    for heading in ("Method and parameters", "Measured re-identification risk against stated attackers",
                    "Utility justification", "Residual risks"):
        assert f"{heading}: rendered" in result.stdout
    section = unescape(out.read_text(encoding="utf-8")).split("## 6.")[1].split("## 7.")[0]
    assert "Other risk not measured" in section
    assert "not measured: synthetic rate unavailable" in section


def test_absent_per_persona_attackers_are_explicitly_pending(release, tmp_path):
    out = tmp_path / "pack.md"
    result = run_pack(release, out)
    assert result.returncode == 0, result.stderr
    section = out.read_text(encoding="utf-8").split("## 4.")[1].split("## 5.")[0]
    assert "attacker personas: not measured (pending #138)" in section


def test_no_differential_privacy_is_labelled_as_a_product_statement(release, tmp_path):
    out = tmp_path / "pack.md"
    result = run_pack(release, out)
    assert result.returncode == 0, result.stderr
    section = unescape(out.read_text(encoding="utf-8")).split("## 3.")[1].split("## 4.")[0]
    assert "ε (product statement, not recorded in the manifest): no differential privacy used by this tool" in section


@pytest.mark.parametrize("name,section,label,aggregate,expected", [
    ("search", 3, "Measured search", {"candidates": 3, "accepted": 1, "boundReached": False,
                                    "points": [{"step": 0, "risk": .2, "utility": .95, "accepted": True}]},
     '"candidates":3'),
    ("baselines", 5, "Published baselines", {"rows": [{"baseline": "B0", "metric": "utility_mean", "value": .8}]},
     '"baseline":"B0"'),
    ("redaction", 4, "Redaction evaluation", {"mode": "exact", "frame": "synthetic frame", "split": "synthetic split",
                                            "labels": [{"label": "PERSON", "support": 3, "tp": 2, "fp": 1, "fn": 1,
                                                        "precision": .5, "recall": .5}], "summary": []},
     '"support":3'),
])
@pytest.mark.parametrize("status", ["measured", "not_measured"])
def test_every_measurement_block_renders_its_status_and_aggregates(
        release, tmp_path, name, section, label, aggregate, expected, status):
    m = loads_strict((release / "privacy_manifest.json").read_bytes())
    m["measured"][name] = ({"status": status, "source": "synthetic " + name, **aggregate} if status == "measured"
                            else {"status": status, "reason": "synthetic " + name + " unavailable"})
    write_manifest(release, m)
    out = tmp_path / "pack.md"
    result = run_pack(release, out)
    assert result.returncode == 0, result.stderr
    text = unescape(out.read_text(encoding="utf-8")).split(f"## {section}.")[1].split(f"## {section + 1}.")[0]
    assert label + ":" in text
    if status == "measured":
        assert '"status":"measured"' in text and expected in text
        assert "synthetic " + name in text
    else:
        assert "not measured: synthetic " + name + " unavailable" in text


def test_fractional_aggregates_render_safely_without_rounding_nonzero_to_zero(release, tmp_path):
    m = loads_strict((release / "privacy_manifest.json").read_bytes())
    m["measured"]["baselines"] = {"status": "measured", "source": "synthetic aggregate precision",
                                  "rows": [{"baseline": "B0", "metric": "linkage", "value": .4111111111111111},
                                           {"baseline": "B2", "metric": "linkage", "value": .00000001}]}
    m["measured"]["utility"]["tasks"][0]["before"] = .4111111111111111
    write_manifest(release, m)
    out = tmp_path / "pack.md"
    result = run_pack(release, out)
    assert result.returncode == 0, result.stderr
    text = unescape(out.read_text(encoding="utf-8"))
    assert "0.4111" in text and "0.4111111111111111" not in text
    assert "<0.0001" in text
    assert "Numeric aggregates use four decimal places" in text
    assert identifier_shape_counts(text) == {}
