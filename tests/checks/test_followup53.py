"""Follow-up #53: cued everyday words are not secrets/usernames; credential-shaped values and copula-cued
passwords still refuse. Synthetic phrases only."""
import csv
import json
import shutil
from pathlib import Path

import pytest

from pets_release.checks import all_checks, run_checks
from pets_release.checks.text import _detectors as d

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "refusals"
CONTRACT = json.loads((FIX / "contract.json").read_text(encoding="utf-8"))


def _hits(tmp_path, text, check):
    out = tmp_path / "out"
    shutil.copytree(FIX / "valid" / "release", out)
    p = out / "notes.csv"
    with p.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    rows[2][2] = text
    with p.open("w", encoding="utf-8", newline="") as fh:
        csv.writer(fh, lineterminator="\n").writerows(rows)
    own = [c for c in all_checks() if c.name == check]
    res = run_checks(out, CONTRACT, {"phase": "gate"}, checks=own)
    rec = res.records[0]
    return sum(v.count for v in rec.violations if v.severity == "high")


FALSE_POSITIVES = [
    ("rescan.secrets", "Telia password for the router is ok"),
    ("rescan.secrets", "I forgot my password and cannot log in"),
    ("rescan.secrets", "password reset link did not arrive"),
    ("rescan.secrets", "the password should be changed"),
    ("rescan.secrets", "salasana kaikille palveluille"),
    ("rescan.secrets", "password is the same everywhere"),
    ("rescan.secrets", "my password is probably the old one"),
    ("rescan.secrets", "l\u00f6senordet \u00e4r inte r\u00e4tt"),
    ("rescan.secrets", "password is not working"),
    ("rescan.usernames", "username for the account"),
    ("rescan.usernames", "username is the same as before"),
    ("rescan.usernames", "login page does not open"),
    ("rescan.usernames", "login is not working"),
]

STILL_REFUSED = [
    ("rescan.secrets", "salasana on kissakala muista", 1),
    ("rescan.secrets", "password: hunterxyz", 1),
    ("rescan.secrets", "my password is probably hunterxyz", 1),
    ("rescan.secrets", "password Talvi2031 works", 1),
    ("rescan.secrets", "password Kissa!kala works", 1),
    ("rescan.secrets", "pin 4821 please", 1),
    ("rescan.secrets", "password a1b2c3d4e5f6a7b8c9d0e1f2 here", 1),
    ("rescan.usernames", "username is mattikoski", 1),
    ("rescan.usernames", "username mattik77 locked", 1),
]


@pytest.mark.parametrize("check,text", FALSE_POSITIVES)
def test_cued_everyday_words_pass_in_cells(tmp_path, check, text):
    assert _hits(tmp_path, text, check) == 0


@pytest.mark.parametrize("check,text,n", STILL_REFUSED)
def test_cued_credentials_still_refuse_in_cells(tmp_path, check, text, n):
    assert _hits(tmp_path, text, check) == n


@pytest.mark.parametrize("text", [t for c, t in FALSE_POSITIVES if c == "rescan.secrets"])
def test_text_secrets_agree_on_everyday_words(text):
    assert d.secrets(text) == []


@pytest.mark.parametrize("text", [
    "my password is Kissa123!", "password: hunterxyz!", "pin 4821 please", "password Talvi2031 works"])
def test_text_secrets_still_refuse(text):
    assert d.secrets(text) != []


def test_text_non_copula_alpha_with_trailing_punct_is_not_a_secret():
    assert d.secrets("password reset? yes") == []
    assert d.secrets("what is the password?") == []


@pytest.mark.parametrize("check,text", [
    ("rescan.secrets", "your password is [SECRET_1] ok"),
    ("rescan.secrets", "salasana: [SECRET_2]"),
    ("rescan.secrets", "PIN [SECRET_3]"),
    ("rescan.usernames", "k\u00e4ytt\u00e4j\u00e4tunnus on [USERNAME_1]"),
])
def test_redacted_placeholders_after_a_cue_are_not_hits(tmp_path, check, text):
    assert _hits(tmp_path, text, check) == 0


@pytest.mark.parametrize("text", ["your password is [SECRET_1] ok", "salasana: [SECRET_2]", "PIN [SECRET_3]."])
def test_text_secrets_ignore_placeholders(text):
    assert d.secrets(text) == []


def test_hedge_then_placeholder_is_not_a_hit(tmp_path):
    assert _hits(tmp_path, "salasana on nyt [SECRET_1]", "rescan.secrets") == 0


def test_label_with_colon_after_cue_is_a_text_secret():
    # round 3 (review): a trailing ":" is a copula and re-arms a plain-word value (fail closed)
    assert d.secrets("salasana vaihtoehto: kokeile") != []
    assert d.secrets("password policy: strong") != []
    assert d.secrets("password: Kissa!") != []
