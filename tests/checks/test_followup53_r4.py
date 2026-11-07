"""Follow-up #53 round 4 (review, fail-open): a hedge carrying a trailing ":" or "=" arms the next word,
like any other word does ("<cue> probably: <value>"). Cells and text, secrets and usernames, through
``run_checks`` and once through the real checks CLI. Synthetic phrases only."""
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

HEDGED_SECRETS = [f"{pre}{d} kissakala" for pre in ("password probably", "salasana nyt",
                                                   "password for the router still")
                  for d in (":", "=")]
HEDGED_USERS = [f"{pre}{d} mattikoski" for pre in ("username probably", "login nyt",
                                                  "username for the shop still")
                for d in (":", "=")]


@pytest.mark.parametrize("check", SECRETS)
@pytest.mark.parametrize("text", HEDGED_SECRETS)
def test_hedge_with_trailing_delimiter_arms_secret_value(tmp_path, check, text):
    assert _hits(tmp_path, text, check) >= 1


@pytest.mark.parametrize("check", USERS)
@pytest.mark.parametrize("text", HEDGED_USERS)
def test_hedge_with_trailing_delimiter_arms_username_value(tmp_path, check, text):
    assert _hits(tmp_path, text, check) >= 1


@pytest.mark.parametrize("check", SECRETS + USERS)
@pytest.mark.parametrize("text", ["password probably works", "username probably unknown",
                                  "password probably."])
def test_plain_hedge_without_delimiter_stays_prose(tmp_path, check, text):
    assert _hits(tmp_path, text, check) == 0


# a short date right after a copula is the value in text as in cells (length gate ran first in text)
@pytest.mark.parametrize("check", SECRETS)
@pytest.mark.parametrize("text", ["password is 1.5", "salasana on 3/7"])
def test_three_character_date_after_copula_refuses(tmp_path, check, text):
    assert _hits(tmp_path, text, check) >= 1


@pytest.mark.parametrize("delim", [":", "="])
def test_cli_refuses_hedged_values(tmp_path, delim):
    c = tmp_path / "contract.json"
    shutil.copy(FIX / "contract.json", c)
    env = dict(os.environ, PYTHONPATH=str(SRC), PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    for check, text in (("rescan.secrets", f"password probably{delim} kissakala"),
                        ("text.secrets", f"password probably{delim} kissakala"),
                        ("rescan.usernames", f"username probably{delim} mattikoski"),
                        ("text.usernames", f"username probably{delim} mattikoski")):
        out = _release(tmp_path, text, check.replace(".", "_"))
        r = subprocess.run([sys.executable, "-m", "pets_release.checks", "--contract", str(c),
                            "--phase", "gate", "--check", check, str(out)],
                           check=False, capture_output=True, text=True, env=env)
        assert r.returncode == 1, (check, r.stderr)
        summary = json.loads(r.stdout)
        assert summary["refused"] is True
        assert {x["check"]: x["status"] for x in summary["records"]}[check] == "fail"
        assert "kissakala" not in r.stdout and "mattikoski" not in r.stdout
