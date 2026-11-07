"""Follow-up #53 round 2: the cue scan looks past function words and exact redactor placeholders
within a short window; brackets are value characters; text and cells agree. All through the
production checks (``run_checks``). Synthetic phrases only."""
import csv
import json
import shutil
from pathlib import Path

import pytest

from pets_release.checks import all_checks, run_checks
from pets_release.checks import _cues

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "refusals"
CONTRACT = json.loads((FIX / "contract.json").read_text(encoding="utf-8"))
SECRET_CHECKS = ("rescan.secrets", "text.secrets")


def _hits(tmp_path, text, check):
    out = tmp_path / check.replace(".", "_")
    shutil.copytree(FIX / "valid" / "release", out)
    p = out / "notes.csv"
    with p.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    rows[2][2] = text
    with p.open("w", encoding="utf-8", newline="") as fh:
        csv.writer(fh, lineterminator="\n").writerows(rows)
    own = [c for c in all_checks() if c.name == check]
    assert len(own) == 1
    res = run_checks(out, CONTRACT, {"phase": "gate"}, checks=own)
    rec = res.records[0]
    assert rec.status in ("pass", "fail"), rec.status
    return sum(v.count for v in rec.violations if v.severity == "high")


# value after skipped function/prose words or an exact placeholder: must refuse in cells and text
HIDDEN_SECRETS = [
    "password is the Talvi2031",
    "password for Talvi2031",
    "password for the router is Talvi2031",
    "pin is not 4821",
    "the password is not 4821",
    "password is [SECRET_1]Talvi2031",
    "password is [SECRET_1] Talvi2031",
    "password:[SECRET_1]Talvi2031",
    "password: [A_1]",
    "password: [Hunter2!]",
    "salasana on kissakala",
    "password: hunterxyz",
]


@pytest.mark.parametrize("check", SECRET_CHECKS)
@pytest.mark.parametrize("text", HIDDEN_SECRETS)
def test_cued_secret_past_skipped_words_refuses(tmp_path, check, text):
    assert _hits(tmp_path, text, check) >= 1


# a placeholder is the (already redacted) value; the word before it, or prose after it, is not
REDACTED = [
    "salasana on edelleen [SECRET_1]",
    "password:[SECRET_1]",
    "password: [SECRET_1].",
    "salasana on [SECRET_1] muista",
    "your password is [SECRET_1] ok",
]


@pytest.mark.parametrize("check", SECRET_CHECKS)
@pytest.mark.parametrize("text", REDACTED)
def test_exact_placeholder_is_skipped(tmp_path, check, text):
    assert _hits(tmp_path, text, check) == 0


def test_username_placeholder_after_copula_is_not_a_hit(tmp_path):
    assert _hits(tmp_path, "käyttäjätunnus oli [USERNAME_1]", "rescan.usernames") == 0


@pytest.mark.parametrize("check", ["rescan.usernames", "text.usernames"])
def test_bracketed_username_value_refuses(tmp_path, check):
    assert _hits(tmp_path, "username is [mattikoski]", check) >= 1


# the round-1 false positives stay passes through the production text check as well
TEXT_FALSE_POSITIVES = [
    "Telia password for the router is ok",
    "I forgot my password and cannot log in",
    "password reset link did not arrive",
    "the password should be changed",
    "salasana kaikille palveluille",
    "password is the same everywhere",
    "my password is probably the old one",
    "lösenordet är inte rätt",
    "password is not working",
    "password policy: strong",
    "what is the password?",
]


@pytest.mark.parametrize("check", SECRET_CHECKS)
@pytest.mark.parametrize("text", TEXT_FALSE_POSITIVES)
def test_everyday_words_pass_in_cells_and_text(tmp_path, check, text):
    assert _hits(tmp_path, text, check) == 0


# measured on the CS-S1 dry run: a word after an article or intensifier describes, it is not a value;
# only a hedge ("probably", "still", "nyt") keeps a plain word after the copula a value
DESCRIPTIONS = [
    "the password is a pain",
    "password is really annoying",
    "salasana on ei toimiva",
    "password is not kissakala",
]


@pytest.mark.parametrize("check", SECRET_CHECKS)
@pytest.mark.parametrize("text", DESCRIPTIONS)
def test_word_after_article_or_intensifier_is_not_a_value(tmp_path, check, text):
    assert _hits(tmp_path, text, check) == 0


@pytest.mark.parametrize("check", SECRET_CHECKS)
@pytest.mark.parametrize("text", ["my password is probably hunterxyz", "salasana on edelleen kissakala",
                                  "password is a Talvi2031"])
def test_hedged_word_or_credential_after_article_still_refuses(tmp_path, check, text):
    assert _hits(tmp_path, text, check) >= 1


@pytest.mark.parametrize("text", ["asiakas antoi [USERNAME_1].", "ok [USERNAME_12], kiitos", "[USERNAME_1]"])
def test_cue_inside_a_placeholder_is_not_a_cue(tmp_path, text):
    assert _hits(tmp_path, text, "rescan.usernames") == 0


def test_placeholder_labels_are_the_redactors():
    from pets_release.redactor.labels import LABELS, placeholder
    assert tuple(_cues.PLACEHOLDER_LABELS) == tuple(LABELS)
    for lab in LABELS:
        assert _cues.is_placeholder(placeholder(lab, 7))
    for tag in ("[A_1]", "[SECRET_0]", "[SECRET_1]x", "[Secret_1]", "[HUNTER]", "[SECRET_01]"):
        assert not _cues.is_placeholder(tag)
