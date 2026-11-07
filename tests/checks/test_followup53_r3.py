"""Follow-up #53 round 3: any copula in the clause re-arms a plain-word value; a credential-shaped
token counts anywhere up to the sentence end (bounded); punctuation and separator runs are skipped;
a value glued to a placeholder is still a value; dates agree across cells and text. All through
``run_checks`` for both checks. Synthetic phrases only."""
import csv
import json
import shutil
from pathlib import Path

import pytest

from pets_release.checks import all_checks, run_checks

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "refusals"
CONTRACT = json.loads((FIX / "contract.json").read_text(encoding="utf-8"))
BOTH = ("rescan.secrets", "text.secrets")


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
    rec = run_checks(out, CONTRACT, {"phase": "gate"}, checks=own).records[0]
    assert rec.status in ("pass", "fail"), rec.status
    return sum(v.count for v in rec.violations if v.severity == "high")


MUST_REFUSE = [
    # 1: a later copula re-arms a plain word after skipped function/prose words
    "password for the router is kissakala",
    "password for my bank is kissakala",
    "salasana kotiin on kissakala",
    # 2: a credential-shaped value beyond six tokens, still in the sentence
    "password for the home office router is Talvi2031",
    "the password for the old home office wifi router upstairs is Talvi2031",
    "pin for the card that I got last week is 4821",
    # 3: punctuation/separator runs between cue and value
    "password / Talvi2031",
    "password -- Talvi2031",
    "pin - 4821",
    "password - Talvi2031",
    "password · Talvi2031",
    "password # : Talvi2031",
    # DeepSeek: a value glued to a placeholder; a date after a copula
    "password is [SECRET_1]hunterxyz",
    "password is 12/03/2021",
]


@pytest.mark.parametrize("check", BOTH)
@pytest.mark.parametrize("text", MUST_REFUSE)
def test_round3_values_refuse(tmp_path, check, text):
    assert _hits(tmp_path, text, check) >= 1


MUST_PASS = [
    "password for the router is in the drawer",
    "password for the account is locked",
    "password - see above",
    "password is [SECRET_1] hunterxyz",
    "password is [SECRET_1]. Kiitos",
    "password reset. Call me at noon tomorrow please, the router is fine",
]


@pytest.mark.parametrize("check", BOTH)
@pytest.mark.parametrize("text", MUST_PASS)
def test_round3_everyday_phrases_pass(tmp_path, check, text):
    assert _hits(tmp_path, text, check) == 0


def test_sentence_end_bounds_the_scan(tmp_path):
    for check in BOTH:
        assert _hits(tmp_path, "password reset. Ticket 4821 closed", check) == 0
