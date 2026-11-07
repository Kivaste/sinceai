"""Must-fix #56: the 05 text checks fail open (Sol retro review). Production checks via the real runner.

Rows (trigger -> result):
  multiword health term split across two adjacent turns, required  -> text.health fail, 1 high hit on both rows
  phone with comma separators in one turn                          -> text.phones and rescan.phones hit
  phone with a newline separator in one turn                       -> text.phones and rescan.phones hit
  no text-form column; short cells under a permissive regex form   -> every text check error (never not_applicable)
  tight regex / validator forms with short cells                   -> text checks stay not_applicable
  token in a URL fragment (scheme and www.)                        -> text.urls-with-tokens and rescan hit
  token-bearing www. URL without a scheme                          -> rescan.urls-with-tokens hits
  contract without healthInTextRequired                            -> treated as required: fail, high severity
All rows are hand-made synthetic text (textbook test values), never kit rows.
"""
from __future__ import annotations

import csv

import pytest

from pets_release.checks import all_checks, run_checks

C = "customer"


def _rec(name, folder, contract, ctx=None):
    chk = {c.name: c for c in all_checks()}[name]
    (rec,) = run_checks(folder, contract, ctx or {"phase": "gate"}, checks=[chk]).records
    return rec.to_dict()


def _high(rec):
    return sum(v["count"] for v in rec["violations"] if v["severity"] == "high")


# --- 1. health term split across a conversation join ---------------------------------------------------

def test_health_term_split_across_adjacent_turns_is_a_hit(release, contract):
    folder = release([[(C, "last year I had a heart"), (C, "attack and could not pay")]])
    rec = _rec("text.health", folder, contract(health_required=True))
    assert rec["status"] == "fail" and _high(rec) == 1, rec
    (v,) = rec["violations"]
    assert len(v["locations"]) == 2


def test_health_term_in_one_turn_still_counts_once(release, contract):
    folder = release([[(C, "I had a heart attack"), (C, "attack of what")]])
    rec = _rec("text.health", folder, contract(health_required=True))
    assert _high(rec) == 1, rec


# --- 2. comma and newline phone separators -------------------------------------------------------------

@pytest.mark.parametrize("text", ["call me on 040,123,4567 tomorrow", "call me on 040, 123, 4567 tomorrow",
                                  "call me on 040\n123 4567 tomorrow", "call me on\n040\n1234567"])
@pytest.mark.parametrize("check", ["text.phones", "rescan.phones"])
def test_comma_or_newline_separated_phone_is_a_hit(release, contract, text, check):
    folder = release([[(C, text)]])
    rec = _rec(check, folder, contract())
    assert rec["status"] == "fail" and _high(rec) >= 1, rec


def test_spaced_phone_baseline_still_a_hit(release, contract):
    folder = release([[(C, "call me on 040 123 4567")]])
    assert _high(_rec("text.phones", folder, contract())) == 1


# --- 3. applicability must not rest on the word-count heuristic ------------------------------------------

def _short_release(tmp_path, form):
    folder = tmp_path / "r"
    folder.mkdir()
    with open(folder / "notes.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["note_id", "note"])
        w.writerows([["N1", "call me"], ["N2", "040 123"], ["N3", "4567 ok"]])
    contract = {"files": {"notes.csv": {"required": ["note_id", "note"], "columns": {
        "note_id": {"form": "^N[0-9]+$", "params": {}}, "note": {"form": form, "params": {}}}}},
        "qi": [], "tokens": [], "healthInTextRequired": True}
    return folder, contract


@pytest.mark.parametrize("form", ["^.*$", "^.+$", "^[A-Za-z0-9 ]+$", "^[\\w\\s]{1,40}$"])
@pytest.mark.parametrize("check", ["text.phones", "text.health", "text.secrets"])
def test_permissive_form_with_short_cells_is_not_not_applicable(tmp_path, form, check):
    folder, contract = _short_release(tmp_path, form)
    rec = _rec(check, folder, contract)
    assert rec["status"] == "error", rec


@pytest.mark.parametrize("form", ["^[A-Z][0-9]{2}$", "^[0-9]+$", "^(call me|ok)$"])
def test_tight_forms_stay_not_applicable(tmp_path, form):
    folder = tmp_path / "r"
    folder.mkdir()
    with open(folder / "notes.csv", "w", encoding="utf-8", newline="") as fh:
        csv.writer(fh).writerows([["note_id", "note"], ["N1", "A12" if "A-Z" in form else "12"]])
    contract = {"files": {"notes.csv": {"required": ["note_id", "note"], "columns": {
        "note_id": {"form": "^N[0-9]+$", "params": {}}, "note": {"form": form, "params": {}}}}},
        "qi": [], "tokens": [], "healthInTextRequired": True}
    assert _rec("text.phones", folder, contract)["status"] == "not_applicable"


# --- 4. URL fragments and scheme-less www. URLs ------------------------------------------------------------

TOKEN = "Zx9" + "q" * 21 + "7k"  # synthetic opaque 26-char token


@pytest.mark.parametrize("url", [f"www.example.test/r#token={TOKEN}", f"https://example.test/cb#access_token={TOKEN}",
                                 f"https://example.test/app#/reset/{TOKEN}"])
@pytest.mark.parametrize("check", ["text.urls-with-tokens", "rescan.urls-with-tokens"])
def test_token_in_url_fragment_is_a_hit(release, contract, url, check):
    folder = release([[(C, f"open {url} please")]])
    rec = _rec(check, folder, contract())
    assert rec["status"] == "fail" and _high(rec) >= 1, rec


@pytest.mark.parametrize("url", [f"www.example.test/x?token={TOKEN}", f"www.example.test/u/{TOKEN}"])
def test_scheme_less_www_url_is_a_cell_rescan_hit(release, contract, url):
    folder = release([[(C, f"open {url} please")]])
    rec = _rec("rescan.urls-with-tokens", folder, contract())
    assert rec["status"] == "fail" and _high(rec) >= 1, rec


def test_plain_fragment_is_not_a_hit(release, contract):
    folder = release([[(C, "see https://example.test/help#billing and www.example.test/faq#top")]])
    for check in ("text.urls-with-tokens", "rescan.urls-with-tokens"):
        assert _rec(check, folder, contract())["status"] == "pass"


# --- 5. healthInTextRequired missing fails closed ------------------------------------------------------------

def test_missing_health_requirement_is_treated_as_required(release, contract):
    folder = release([[(C, "because of my diabetes")]])
    c = contract()
    del c["healthInTextRequired"]
    rec = _rec("text.health", folder, c)
    assert rec["status"] == "fail" and _high(rec) == 1, rec
