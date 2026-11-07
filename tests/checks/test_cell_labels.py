"""Per-label cell rescans, raw timestamps and file digests, through the registry (synthetic values only)."""
import csv
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from pets_release.checks import all_checks, run_checks

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
    ("rescan.national-ids", "hetu 131052-308T kirjattu", 1),
    ("rescan.national-ids", "hetu 131052-308U kirjattu", 0),  # bad check character
    ("rescan.payment-cards", "card 5555-5555-5555-4444", 1),
    ("rescan.payment-cards", "card 4111 1111 1111 1112", 0),  # Luhn fails
    ("rescan.ibans", "tili FI21 1234 5600 0007 85", 1),
    ("rescan.ibans", "tili FI21 1234 5600 0007 86", 0),  # mod-97 fails
    ("rescan.account-numbers", "asiakasnumero 70451239 ok", 1),
    ("rescan.emails", "mail matti.m@example.fi now", 1),
    ("rescan.phones", "soita 040 123 4567 heti", 1),
    ("rescan.phones", "call +358 50 765 4321", 1),
    ("rescan.phones", "hetu 040577-9150 only", 0),  # a valid HETU with a digit check char is not a phone
    ("rescan.national-ids", "hetu 040577-9150 only", 1),
    ("rescan.ip-addresses", "from 81.17.24.5 today", 1),
    ("rescan.ip-addresses", "from 2a00:1450:4010::1 today", 1),
    ("rescan.ip-addresses", "version 999.1.2.3 build", 0),
    ("rescan.device-ids", "imei 490154203237518 found", 1),
    ("rescan.device-ids", "mac 00:1A:2B:3C:4D:5E found", 1),
    ("rescan.usernames", "käyttäjätunnus mattik77 lukittu", 1),
    ("rescan.property-ids", "kiinteistö 091-404-12-5 myyty", 1),
    ("rescan.plates", "auto ABC-123 pihalla", 1),
    ("rescan.secrets", "salasana on Talvi2031 muista", 1),
    ("rescan.secrets", "key AKIAABCDEFGHIJKLMNOP leaked", 1),
    ("rescan.urls-with-tokens", "see https://portal.example/reset?token=abc123XYZ", 1),
    ("rescan.urls-with-tokens", "see https://www.example.fi/ohjeet", 0),
    ("rescan.raw-timestamps", "seen 2025-03-04T14:37:12 at desk", 1),
    ("rescan.raw-timestamps", "seen 4.3.2025 klo 14.37 at desk", 1),
    ("rescan.raw-timestamps", "seen 2025-03-01T14:00 at desk", 0),
    # review regressions (a47edff)
    ("rescan.ibans", "konto PT74 0035 1234 0567 8912 3457 2 ok", 1),  # PT is 25 chars (ISO 13616)
    ("rescan.ibans", "konto PT74003512340567891234572 ok", 1),
    ("rescan.usernames", "käyttäjätunnus mattikoski lukittu", 1),  # cued, purely alphabetic
    ("rescan.secrets", "salasana on kissakala muista", 1),  # cued, purely alphabetic
    ("rescan.secrets", "password: hunterxyz", 1),
    ("rescan.raw-timestamps", "seen 2025-03-01T14:00:00.250 at desk", 1),  # non-zero fraction
    ("rescan.raw-timestamps", "seen 2025-03-01T14:00:00,5 at desk", 1),
    ("rescan.raw-timestamps", "seen 2025-03-01T14:00:00.000 at desk", 0),
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
    rec, _ = _rec(tmp_path, "gateway 192.168.1.1 down", "rescan.ip-addresses")
    assert rec.status == "pass"
    assert [v.severity for v in rec.violations] == ["low"]


def test_placeholders_are_not_hits(tmp_path):
    own = [c for c in all_checks() if c.run.__module__.startswith("pets_release.checks.cells.")]
    res = run_checks(_plant(tmp_path, "[PHONE_1] [EMAIL_1] [PAYMENT_CARD_1] [SECRET_1]"), CONTRACT, GATE, checks=own)
    assert {r.check: r.status for r in res.records if r.status != "pass"} == {}
    assert not res.refused


def _manifest(out, files):
    (out / "privacy_manifest.json").write_text(json.dumps({"bindings": {"files": files}}), encoding="utf-8")


def _sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_digests_match_in_verify_phase(tmp_path):
    out = tmp_path / "out"
    shutil.copytree(FIX / "valid" / "release", out)
    _manifest(out, {f: _sha(out / f) for f in ("notes.csv", "visits.csv")})
    rec = {r.check: r for r in run_checks(out, CONTRACT, {"phase": "verify"}).records}["release.file-digests"]
    assert rec.status == "pass" and rec.denominator == {"unit": "files", "n": 2}


def test_changed_file_fails_digest_check(tmp_path):
    out = tmp_path / "out"
    shutil.copytree(FIX / "valid" / "release", out)
    _manifest(out, {f: _sha(out / f) for f in ("notes.csv", "visits.csv")})
    with (out / "visits.csv").open("a", encoding="utf-8", newline="") as fh:
        fh.write("")
    (out / "visits.csv").write_bytes((out / "visits.csv").read_bytes().replace(b"125", b"126"))
    res = run_checks(out, CONTRACT, {"phase": "verify"})
    rec = {r.check: r for r in res.records}["release.file-digests"]
    assert rec.status == "fail" and [v.file for v in rec.violations] == ["visits.csv"]
    assert res.refused


def test_verify_without_manifest_fails_digest_check(tmp_path):
    out = tmp_path / "out"
    shutil.copytree(FIX / "valid" / "release", out)
    rec = {r.check: r for r in run_checks(out, CONTRACT, {}).records}["release.file-digests"]
    assert rec.status == "fail"


def test_manifest_binding_missing_a_file_fails(tmp_path):
    out = tmp_path / "out"
    shutil.copytree(FIX / "valid" / "release", out)
    _manifest(out, {"visits.csv": _sha(out / "visits.csv")})
    rec = {r.check: r for r in run_checks(out, CONTRACT, {"phase": "verify"}).records}["release.file-digests"]
    assert rec.status == "fail" and [v.file for v in rec.violations] == ["notes.csv"]
