"""Per-label cell rescans, raw timestamps and file digests, through the registry (synthetic values only)."""
import csv
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from pets_release.checks import run_checks

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "refusals"
CONTRACT = json.loads((FIX / "contract.json").read_text(encoding="utf-8"))
GATE = {"phase": "gate"}


def _plant(tmp_path, text):
    out = tmp_path / "out"
    shutil.copytree(FIX / "valid" / "release", out)
    p = out / "notes.csv"
    with p.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    rows[2][2] = text  # data row 1
    with p.open("w", encoding="utf-8", newline="") as fh:
        csv.writer(fh, lineterminator="\n").writerows(rows)
    return out


def _rec(tmp_path, text, check):
    res = run_checks(_plant(tmp_path, text), CONTRACT, GATE)
    return {r.check: r for r in res.records}[check], res


# (check, planted text, expected high hits). Near misses expect 0.
CASES = [
    ("nationalIds", "hetu 131052-308T kirjattu", 1),
    ("nationalIds", "hetu 131052-308U kirjattu", 0),  # bad check character
    ("paymentCards", "card 5555-5555-5555-4444", 1),
    ("paymentCards", "card 4111 1111 1111 1112", 0),  # Luhn fails
    ("ibans", "tili FI21 1234 5600 0007 85", 1),
    ("ibans", "tili FI21 1234 5600 0007 86", 0),  # mod-97 fails
    ("accountNumbers", "asiakasnumero 70451239 ok", 1),
    ("emails", "mail matti.m@example.fi now", 1),
    ("phones", "soita 040 123 4567 heti", 1),
    ("phones", "call +358 50 765 4321", 1),
    ("phones", "hetu 040577-9150 only", 0),  # a valid HETU with a digit check char is not a phone
    ("nationalIds", "hetu 040577-9150 only", 1),
    ("ipAddresses", "from 81.17.24.5 today", 1),
    ("ipAddresses", "from 2a00:1450:4010::1 today", 1),
    ("ipAddresses", "version 999.1.2.3 build", 0),
    ("deviceIds", "imei 490154203237518 found", 1),
    ("deviceIds", "mac 00:1A:2B:3C:4D:5E found", 1),
    ("usernames", "käyttäjätunnus mattik77 lukittu", 1),
    ("propertyIds", "kiinteistö 091-404-12-5 myyty", 1),
    ("plates", "auto ABC-123 pihalla", 1),
    ("secrets", "salasana on Talvi2031 muista", 1),
    ("secrets", "key AKIAABCDEFGHIJKLMNOP leaked", 1),
    ("urlsWithTokens", "see https://portal.example/reset?token=abc123XYZ", 1),
    ("urlsWithTokens", "see https://www.example.fi/ohjeet", 0),
    ("rawTimestamps", "seen 2025-03-04T14:37:12 at desk", 1),
    ("rawTimestamps", "seen 4.3.2025 klo 14.37 at desk", 1),
    ("rawTimestamps", "seen 2025-03-01T14:00 at desk", 0),
]


@pytest.mark.parametrize("check,text,hits", CASES)
def test_label_rescan(tmp_path, check, text, hits):
    rec, res = _rec(tmp_path, text, check)
    high = [v for v in rec.violations if v.severity == "high"]
    assert sum(v.count for v in high) == hits
    assert rec.denominator["unit"] == "cells" and rec.denominator["n"] > 0
    if hits:
        assert rec.status == "fail" and res.refused
        assert [(v.file, v.column, list(v.locations)) for v in high] == [("notes.csv", "note_text", [1])]
        planted = max(text.split(), key=lambda w: (any(ch.isdigit() or ch == "@" for ch in w), len(w)))
        assert planted not in json.dumps(res.to_dict())
    else:
        assert rec.status == "pass"


def test_private_ip_is_low_severity_not_refusal(tmp_path):
    rec, _ = _rec(tmp_path, "gateway 192.168.1.1 down", "ipAddresses")
    assert rec.status == "pass"
    assert [v.severity for v in rec.violations] == ["low"]


def test_placeholders_are_not_hits(tmp_path):
    res = run_checks(_plant(tmp_path, "[PHONE_1] [EMAIL_1] [PAYMENT_CARD_1] [SECRET_1]"), CONTRACT, GATE)
    assert not res.refused


def _manifest(out, files):
    (out / "privacy_manifest.json").write_text(json.dumps({"bindings": {"files": files}}), encoding="utf-8")


def _sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_digests_match_in_verify_phase(tmp_path):
    out = tmp_path / "out"
    shutil.copytree(FIX / "valid" / "release", out)
    _manifest(out, {f: _sha(out / f) for f in ("notes.csv", "visits.csv")})
    rec = {r.check: r for r in run_checks(out, CONTRACT, {"phase": "verify"}).records}["fileDigests"]
    assert rec.status == "pass" and rec.denominator == {"unit": "files", "n": 2}


def test_changed_file_fails_digest_check(tmp_path):
    out = tmp_path / "out"
    shutil.copytree(FIX / "valid" / "release", out)
    _manifest(out, {f: _sha(out / f) for f in ("notes.csv", "visits.csv")})
    with (out / "visits.csv").open("a", encoding="utf-8", newline="") as fh:
        fh.write("")
    (out / "visits.csv").write_bytes((out / "visits.csv").read_bytes().replace(b"125", b"126"))
    res = run_checks(out, CONTRACT, {"phase": "verify"})
    rec = {r.check: r for r in res.records}["fileDigests"]
    assert rec.status == "fail" and [v.file for v in rec.violations] == ["visits.csv"]
    assert res.refused


def test_verify_without_manifest_fails_digest_check(tmp_path):
    out = tmp_path / "out"
    shutil.copytree(FIX / "valid" / "release", out)
    rec = {r.check: r for r in run_checks(out, CONTRACT, {}).records}["fileDigests"]
    assert rec.status == "fail"


def test_manifest_binding_missing_a_file_fails(tmp_path):
    out = tmp_path / "out"
    shutil.copytree(FIX / "valid" / "release", out)
    _manifest(out, {"visits.csv": _sha(out / "visits.csv")})
    rec = {r.check: r for r in run_checks(out, CONTRACT, {"phase": "verify"}).records}["fileDigests"]
    assert rec.status == "fail" and [v.file for v in rec.violations] == ["notes.csv"]
