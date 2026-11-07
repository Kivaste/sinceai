"""Follow-up #53 round 5 (Grok r4 review, two fail-opens). Through ``run_checks`` and once through the
real checks CLI. Synthetic phrases only.

(a) A bare wifi/wlan/wi-fi cue + copula + a date/time is the value even when a placeholder follows it,
    is glued to it, or another word follows it (only a plain word mid-clause is prose there).
(b) A hedge glued to its value with ":" or "=" ("<cue> probably:<value>") arms the remainder, which is
    judged as the value, in the cell and text walkers alike; prose remainders stay prose.
"""
import csv
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from pets_release.checks import all_checks, run_checks

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "refusals"
SRC = Path(__file__).resolve().parents[2] / "src"
CONTRACT = json.loads((FIX / "contract.json").read_text(encoding="utf-8"))


def _release(tmp_path, text, name):
    out = tmp_path / name
    shutil.copytree(FIX / "valid" / "release", out)
    p = out / "notes.csv"
    with p.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    rows[2][2] = text
    with p.open("w", encoding="utf-8", newline="") as fh:
        csv.writer(fh, lineterminator="\n").writerows(rows)
    return out


def _hits(tmp_path, text, check):
    out = _release(tmp_path, text, check.replace(".", "_"))
    own = [c for c in all_checks() if c.name == check]
    assert len(own) == 1
    rec = run_checks(out, CONTRACT, {"phase": "gate"}, checks=own).records[0]
    assert rec.status in ("pass", "fail"), rec.status
    return sum(v.count for v in rec.violations if v.severity == "high")


SECRETS = ("rescan.secrets", "text.secrets")
USERS = ("rescan.usernames", "text.usernames")

# (a) bare network cue + copula + date/time: before a placeholder, glued to one, or mid-clause
WIFI_DATES = ["wifi is 12:30 [SECRET_1]", "wifi is 12:30[SECRET_1]", "wlan on 12.03.2021 tomorrow",
              "wi-fi is 12/03 again today", "wifi: 12:30 [SECRET_1] ok"]


@pytest.mark.parametrize("text", WIFI_DATES)
def test_bare_wifi_copula_date_refuses(tmp_path, text):
    assert _hits(tmp_path, text, "rescan.secrets") >= 1


# the plain-word exclusion stays: a plain word mid-clause after a bare network cue is prose
@pytest.mark.parametrize("text", ["wifi is terrible [SECRET_1]", "wlan on hidas tänään"])
def test_bare_wifi_plain_word_mid_clause_stays_prose(tmp_path, text):
    assert _hits(tmp_path, text, "rescan.secrets") == 0


# (b) hedge glued to its value
GLUED_SECRETS = [f"{pre}{d}kissakala" for pre in ("password probably", "salasana nyt",
                                                  "password for the router still")
                 for d in (":", "=")]
GLUED_USERS = [f"{pre}{d}mattikoski" for pre in ("username probably", "login nyt",
                                                 "username for the shop still")
               for d in (":", "=")]


@pytest.mark.parametrize("check", SECRETS)
@pytest.mark.parametrize("text", GLUED_SECRETS)
def test_hedge_glued_secret_value_refuses(tmp_path, check, text):
    assert _hits(tmp_path, text, check) >= 1


@pytest.mark.parametrize("check", USERS)
@pytest.mark.parametrize("text", GLUED_USERS)
def test_hedge_glued_username_value_refuses(tmp_path, check, text):
    assert _hits(tmp_path, text, check) >= 1


# the remainder is judged, not flagged blindly: an everyday word glued to a hedge is still prose
@pytest.mark.parametrize("check", USERS)
@pytest.mark.parametrize("text", ["username probably:unknown", "login still=broken"])
def test_hedge_glued_prose_remainder_passes(tmp_path, check, text):
    assert _hits(tmp_path, text, check) == 0


# a time is never split at its ":" (it is not a hedge + delimiter)
@pytest.mark.parametrize("check", SECRETS)
def test_uncued_time_is_not_split(tmp_path, check):
    assert _hits(tmp_path, "password reset at 12:30 tomorrow", check) == 0


def test_cli_refuses_hedge_glued_username(tmp_path):
    c = tmp_path / "contract.json"
    shutil.copy(FIX / "contract.json", c)
    env = dict(os.environ, PYTHONPATH=str(SRC), PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    for check in USERS:
        out = _release(tmp_path, "username for the shop still:mattikoski", check.replace(".", "_"))
        r = subprocess.run([sys.executable, "-m", "pets_release.checks", "--contract", str(c),
                            "--phase", "gate", "--check", check, str(out)],
                           check=False, capture_output=True, text=True, env=env)
        assert r.returncode == 1, (check, r.stderr)
        summary = json.loads(r.stdout)
        assert summary["refused"] is True
        assert {x["check"]: x["status"] for x in summary["records"]}[check] == "fail"
        assert "mattikoski" not in r.stdout
