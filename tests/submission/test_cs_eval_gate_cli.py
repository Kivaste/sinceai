"""The CS eval exports go through the production text checks (D37), through the real CLI.

Rule: before publication the packager runs the gate's ``text.*`` checks on the exact bytes of
``customer_service_eval_redacted.csv`` (stitched per conversation) and ``customer_service_eval_spans.jsonl``.
A turn with a high-severity hit is masked whole with one typed placeholder, keeping the format: same rows, and that
turn's spans become one whole-turn span with the placeholder's label. The masked-turn count goes into ``submission_index.json``. A successful
redactor run is not proof. A hit the packager cannot mask (in the spans file) or a check that cannot run refuses.

Failure rows (trigger -> result):
  planted miss: an eval turn the redactor leaves but text.ip-addresses flags -> that turn masked whole with one
                typed placeholder [IP_ADDRESS_<next n>] and one whole-turn IP_ADDRESS span, counted 1,
                index checkerIndependence reducedForTurns 1 (D29/D37 note)
  no miss                                                                   -> maskedTurns 0, texts unchanged
  a raw timestamp / unkeyed hash / 64-hex / original value in a turn (the cell-level production checks
  rescan.raw-timestamps, producer.unkeyed-hashes, release.token-hex64, producer.original-values) (#148)
                                                                            -> that turn masked whole, typed
  an original value as a turn id (producer.original-values) (#148)          -> exit 1 cs_eval_id_flagged
  a USERNAME span (raw JSON line looks like a username to the cell rescan)  -> built, not refused: the cell
                                                                               checks read decoded values
  an identifier in an exported turn id (CSV turn_id / JSON record_id)       -> exit 1 cs_eval_id_flagged
  the same, hidden by JSON escaping (tab -> \\t, U+001F -> \\u001f) (#148)    -> exit 1 cs_eval_id_flagged
  a text check missing from the registry                                    -> refused cs_eval_checks_unavailable
  a text check that errors                                                  -> refused cs_eval_check_error
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import shutil
from dataclasses import replace
from pathlib import Path

import pytest
from sub_helpers import TEST_KEY, submission

from pets_release.kit import Kit
from pets_release.pseudonym import MasterKey
from pets_release.submission import SubmissionRefused, build_submission

# The redactor misses this spaced-out public IP; the gate's ip-addresses check finds it (synthetic).
MISS = "ip 8 . 8 . 8 . 8 is down again"
# D29/D37: the bundle index states the reduced checker independence for masked turns (content-free, fixed text).
INDEPENDENCE_NOTE = ("reduced for masked turns: the production checks that flagged a turn also decided its masking, "
                     "so no independent check confirms those turns (D29/D37)")


def _kit_with_turn(world, tmp_path, turn_id, text):
    kit, rel = world
    k2 = tmp_path / "kit"
    shutil.copytree(kit, k2)
    p = k2 / "data" / "customer_service" / "turns.csv"
    with p.open("a", encoding="utf-8", newline="") as fh:
        csv.writer(fh, lineterminator="\n").writerow([turn_id, "c2", "3", "customer", "2025-01-02T10:02:00Z", text])
    return k2, rel


def _bundle(kit, rel, out):
    p = submission("--out", str(out), "--release", str(rel), "--kit", str(kit), "--partial")
    assert p.returncode == 0, p.stdout + p.stderr
    texts = {r["turn_id"]: r["text"] for r in
             csv.DictReader(io.StringIO((out / "customer_service_eval_redacted.csv").read_text("utf-8"), newline=""))}
    spans = {r["record_id"]: r["spans"] for r in
             map(json.loads, (out / "customer_service_eval_spans.jsonl").read_text("utf-8").splitlines())}
    idx = json.loads((out / "submission_index.json").read_text("utf-8"))
    return p, texts, spans, idx


PLACEHOLDER = re.compile(r"\[([A-Z_]+)_([1-9][0-9]*)\]")


def test_a_planted_miss_is_masked_whole_and_counted(world, tmp_path):
    kit, rel = _kit_with_turn(world, tmp_path, "t6", MISS)
    p, texts, spans, idx = _bundle(kit, rel, tmp_path / "pets_submission")
    # one typed placeholder, numbered after the conversation's own IP_ADDRESS placeholders, and one whole-turn
    # span with the same label (the placeholder<->label table: they cannot drift)
    used = [int(n) for lab, n in PLACEHOLDER.findall(texts["t3"]) if lab == "IP_ADDRESS"]
    assert texts["t6"] == f"[IP_ADDRESS_{max(used, default=0) + 1}]"
    assert spans["t6"] == [{"start": 0, "end": len(MISS), "label": "IP_ADDRESS"}]
    assert idx["customerServiceEval"]["maskedTurns"] == 1
    assert sorted(texts) == ["t1", "t2", "t3", "t4", "t6"]  # same rows
    assert texts["t2"] == "Thanks for contacting us"  # other turns untouched
    assert "masked turns=1" in p.stdout
    assert idx["customerServiceEval"]["checkerIndependence"] == {"reducedForTurns": 1, "note": INDEPENDENCE_NOTE}


def test_without_a_miss_nothing_is_masked(world, tmp_path):
    kit, rel = world
    _p, texts, _spans, idx = _bundle(kit, rel, tmp_path / "pets_submission")
    assert idx["customerServiceEval"]["maskedTurns"] == 0
    assert "[REDACTED]" not in texts.values()
    assert idx["customerServiceEval"]["checkerIndependence"] == {"reducedForTurns": 0, "note": INDEPENDENCE_NOTE}


# ---------- #148 (Gemini 3): the remaining production checks run on the export bytes too ----------
# Each plant is synthetic, missed by the redactor, and found only by the named cell-level check.

ORIGINAL_NAME = "Zorblax Quindarius"  # a synthetic customers.full_name
ORIGINAL_HANDLE = "ADMIN_77"  # a synthetic customers.customer_number, shaped like a placeholder


def _with_customers(kit):
    (kit / "data" / "customer_service" / "customers.csv").write_text(
        f"customer_id,customer_number,full_name\nu1,{ORIGINAL_HANDLE},{ORIGINAL_NAME}\n", encoding="utf-8",
        newline="")


@pytest.mark.parametrize(("text", "label"), [
    ("seen it at 2025-13-45 10:37 again", "DATE"),                                  # rescan.raw-timestamps
    ("ref " + hashlib.md5(b"u1").hexdigest() + " please", "SECRET"),                 # producer.unkeyed-hashes
    ("commit " + "0123456789abcdef" * 4 + " broke it", "SECRET"),                    # release.token-hex64
    (f"please tell {ORIGINAL_NAME} thanks", "PERSON"),                               # producer.original-values
], ids=["raw-timestamp", "unkeyed-hash", "token-hex64", "original-value"])
def test_a_cell_check_hit_in_a_turn_is_masked_whole(world, tmp_path, text, label):
    kit, rel = _kit_with_turn(world, tmp_path, "t6", text)
    _with_customers(kit)
    _p, texts, spans, idx = _bundle(kit, rel, tmp_path / "pets_submission")
    m = PLACEHOLDER.fullmatch(texts["t6"])
    assert m and m.group(1) == label, "the turn must be masked whole with a typed placeholder"
    assert spans["t6"] == [{"start": 0, "end": len(text), "label": label}]
    assert idx["customerServiceEval"]["maskedTurns"] == 1
    assert texts["t2"] == "Thanks for contacting us"


def test_the_cell_checks_read_decoded_span_values_not_json_syntax(world, tmp_path):
    # a redacted USERNAME span: its raw JSON line ("label":"USERNAME","start":...) reads as a username to the
    # cell-level rescan; the decoded values (turn id, labels) are what the export carries, and they are clean
    kit, rel = _kit_with_turn(world, tmp_path, "t6", "my username is zorb_77 thanks")
    _p, texts, spans, idx = _bundle(kit, rel, tmp_path / "pets_submission")
    assert texts["t6"] == "my username is [USERNAME_1] thanks"
    assert [s["label"] for s in spans["t6"]] == ["USERNAME"]
    assert idx["customerServiceEval"]["maskedTurns"] == 0


# Round 2 (Sol Standards r1): only recognised placeholders [<LABEL>_<n>] (LABEL in the fixed table, n >= 1) are
# hidden from the cell rescans; any other bracketed shape stays visible, so an original value inside it is caught.
@pytest.mark.parametrize(("shape", "label"), [
    ("[ZORBLAX_QUINDARIUS]", "PERSON"),            # an original value written as a bracketed word
    ("[ZORBLAX_QUINDARIUS_7]", "PERSON"),          # invented label with a number
    ("[ZORBLAXQUINDARIUS]", "PERSON"),             # bare bracketed word
    ("[ZORBLAX_QUINDARIUS_0]", "PERSON"),          # bad numbering
    (f"[{ORIGINAL_HANDLE}]", "ACCOUNT_NUMBER"),    # a real-looking handle in placeholder shape (Grok r1)
], ids=["bracketed-original", "invented-label", "bare-word", "bad-numbering", "handle"])
def test_an_unrecognised_bracketed_identifier_is_caught(world, tmp_path, shape, label):
    text = f"ask {shape} now"
    kit, rel = _kit_with_turn(world, tmp_path, "t6", text)
    _with_customers(kit)
    _p, texts, spans, idx = _bundle(kit, rel, tmp_path / "pets_submission")
    assert shape not in texts["t6"], "an original value inside an unrecognised bracket shape shipped"
    assert spans["t6"] == [{"start": 0, "end": len(text), "label": label}]
    assert idx["customerServiceEval"]["maskedTurns"] == 1


def test_a_duplicate_key_spans_line_refuses(world, tmp_path, monkeypatch):
    """Both eval files are read back with the repo's strict readers; a duplicate key (which json.loads silently
    collapses) refuses. The packager never writes one, so the serialiser is wrapped (build seam)."""
    from pets_release.submission import cs_eval

    real = cs_eval._serialise

    def duplicated(texts, spans):
        csv_bytes, jsonl = real(texts, spans)
        lines = jsonl.decode("utf-8").splitlines(keepends=True)
        lines[0] = lines[0].replace('{"record_id":', '{"record_id":"x","record_id":', 1)
        return csv_bytes, "".join(lines).encode("utf-8")

    monkeypatch.setattr(cs_eval, "_serialise", duplicated)
    kit, rel = world
    out = tmp_path / "s"
    with pytest.raises(SubmissionRefused) as e:
        build_submission(kit=Kit(kit), releases=[rel], out=out, master=MasterKey.from_text(TEST_KEY), partial=True,
                         scorecard=lambda *a, **k: pytest.fail("must refuse before scoring"))
    assert e.value.code == "cs_eval_format"
    assert not out.exists()


def test_an_original_value_as_a_turn_id_refuses(world, tmp_path):
    kit, rel = _kit_with_turn(world, tmp_path, ORIGINAL_NAME, "fine thanks")
    _with_customers(kit)
    out = tmp_path / "pets_submission"
    p = submission("--out", str(out), "--release", str(rel), "--kit", str(kit), "--partial")
    assert (p.returncode, p.stdout.strip()) == (1, "REFUSED: cs_eval_id_flagged"), p.stdout + p.stderr
    assert not out.exists()


def test_an_identifier_in_an_exported_turn_id_refuses(world, tmp_path):
    kit, rel = _kit_with_turn(world, tmp_path, "t-8 . 8 . 8 . 8", "fine thanks")
    out = tmp_path / "pets_submission"
    p = submission("--out", str(out), "--release", str(rel), "--kit", str(kit), "--partial")
    assert p.returncode == 1 and "cs_eval_id_flagged" in p.stdout
    assert not out.exists()


# #148: JSON escaping hid an identifier in the turn id from the spans-line scan, and the staged CSV dropped turn_id.
# A Luhn-valid synthetic test card split by tabs (JSON writes "\t"), and one glued to a unit separator (JSON writes
# "\u001f4111...", so the raw line shows no card boundary).
@pytest.mark.parametrize("turn_id", ["4111\t1111\t1111\t1111", "\x1f4111111111111111"],
                         ids=["json-escaped-tab", "unicode-escaped"])
def test_an_escaped_identifier_in_a_turn_id_refuses(world, tmp_path, turn_id):
    kit, rel = _kit_with_turn(world, tmp_path, turn_id, "fine thanks")
    out = tmp_path / "pets_submission"
    p = submission("--out", str(out), "--release", str(rel), "--kit", str(kit), "--partial")
    assert (p.returncode, p.stdout.strip()) == (1, "REFUSED: cs_eval_id_flagged"), p.stdout + p.stderr
    assert not out.exists()


# ---------- the checks must actually run (build seam: the registry is the boundary) ----------

def _refused(world, tmp_path, monkeypatch, checks):
    import pets_release.checks.registry as reg

    monkeypatch.setattr(reg, "all_checks", lambda scope=None: checks)
    kit, rel = world
    out = tmp_path / "s"
    with pytest.raises(SubmissionRefused) as e:
        build_submission(kit=Kit(kit), releases=[rel], out=out, master=MasterKey.from_text(TEST_KEY), partial=True,
                         scorecard=lambda *a, **k: pytest.fail("must refuse before scoring"))
    assert not out.exists() and not Path(str(out) + ".scoring").exists()
    return e.value.code


def test_a_text_check_missing_from_the_registry_refuses(world, tmp_path, monkeypatch):
    from pets_release.checks.registry import all_checks

    kept = tuple(c for c in all_checks() if c.name != "text.ip-addresses")
    assert _refused(world, tmp_path, monkeypatch, kept) == "cs_eval_checks_unavailable"


@pytest.mark.parametrize("label", ["crc32:customers.full_name", "md5:customers.no_such_column", "md5:"],
                         ids=["unknown-algorithm", "unknown-column", "empty"])
def test_an_unmapped_checker_label_refuses(world, tmp_path, monkeypatch, label):
    """A hit whose label has no span-label mapping refuses (never guessed as SECRET, Grok r1). The production
    unkeyed-hashes check only emits mapped labels, so it is replaced at the registry by one that flags the first
    eval turn with ``label``."""
    from pets_release.checks.records import Outcome, Violation
    from pets_release.checks.registry import all_checks

    def flag(release, contract, context):
        return Outcome(n=1, violations=(Violation("producer.unkeyed-hashes", label, "high",
                                                  "customer_service_eval_redacted.csv", "text", 1, (0,)),))

    patched = tuple(replace(c, run=flag) if c.name == "producer.unkeyed-hashes" else c for c in all_checks())
    assert _refused(world, tmp_path, monkeypatch, patched) == "cs_eval_unlabelled_hit"


def test_a_text_check_that_errors_refuses(world, tmp_path, monkeypatch):
    from pets_release.checks.registry import all_checks

    def boom(*a, **k):
        raise RuntimeError("check crashed")

    broken = tuple(replace(c, run=boom) if c.name == "text.emails" else c for c in all_checks())
    assert _refused(world, tmp_path, monkeypatch, broken) == "cs_eval_check_error"
