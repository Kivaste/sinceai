"""Follow-up #53 round 3, #54 shape audit: (a) text.usernames uses the shared cue rule and prose list;
(b) a plain word directly before a placeholder is not the value (the placeholder is); (c) a bare
wifi/wlan cue + copula + a plain word mid-clause is prose. Credential-shaped tokens always count.
Through ``run_checks``. Synthetic phrases only."""
import csv
import json
import shutil
from pathlib import Path

import pytest

from pets_release.checks import all_checks, run_checks

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "refusals"
CONTRACT = json.loads((FIX / "contract.json").read_text(encoding="utf-8"))


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


USERS = ("rescan.usernames", "text.usernames")

# (a) prose after a username cue
USER_PROSE = ["username for the account", "login is broken", "username unknown, please help",
              "login page does not open", "username is the same as before", "login service is down"]


@pytest.mark.parametrize("check", USERS)
@pytest.mark.parametrize("text", USER_PROSE)
def test_prose_after_username_cue_passes(tmp_path, check, text):
    assert _hits(tmp_path, text, check) == 0


USER_VALUES = ["username is mattikoski", "username mattik77 locked", "username is [mattikoski]",
               "login: matti.koski", "username for the shop is mattikoski", "username - mattik77"]


@pytest.mark.parametrize("check", USERS)
@pytest.mark.parametrize("text", USER_VALUES)
def test_username_values_refuse(tmp_path, check, text):
    assert _hits(tmp_path, text, check) >= 1


# (b) a plain word directly before a placeholder is not the value
BEFORE_PLACEHOLDER = [
    ("rescan.secrets", "salasana on kissakala [SECRET_1]"),
    ("text.secrets", "salasana on kissakala [SECRET_1]"),
    ("rescan.secrets", "password is hunterxyz [SECRET_1] ok"),
    ("text.secrets", "password is hunterxyz [SECRET_1] ok"),
    ("rescan.usernames", "username is mattikoski [USERNAME_1]"),
    ("text.usernames", "username is mattikoski [USERNAME_1]"),
]


@pytest.mark.parametrize("check,text", BEFORE_PLACEHOLDER)
def test_plain_word_before_placeholder_is_not_the_value(tmp_path, check, text):
    assert _hits(tmp_path, text, check) == 0


@pytest.mark.parametrize("check", ["rescan.secrets", "text.secrets"])
@pytest.mark.parametrize("text", ["password is Talvi2031 [SECRET_1]", "password is [SECRET_1]hunterxyz",
                                  "password is kissakala"])
def test_credential_before_placeholder_or_glued_value_still_refuses(tmp_path, check, text):
    assert _hits(tmp_path, text, check) >= 1


# (c) bare wifi/wlan cue: a plain word mid-clause is prose; credential-shaped or clause-final still counts
@pytest.mark.parametrize("text", ["wifi is terrible again today", "wifi on kehno tänään",
                                  "wlan is unusable for now"])
def test_bare_wifi_prose_passes(tmp_path, text):
    assert _hits(tmp_path, text, "rescan.secrets") == 0


@pytest.mark.parametrize("text", ["wifi is Talvi2031 here", "wifi password is kissakala today", "wifi: kissakala",
                                  "wifi-avain on kissakala nyt", "wlan on kissakala."])
def test_wifi_values_still_refuse(tmp_path, text):
    assert _hits(tmp_path, text, "rescan.secrets") >= 1
