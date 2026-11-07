"""#67: the redaction-evaluation CLI evaluates the shipped conversation-level redactor.
Fixtures are small hand-made synthetic rows written to a temp kit."""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"


def _w(path: Path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def _spans(text, *vals):
    out = []
    for v, lab in vals:
        s = text.index(v)
        out.append({"start": s, "end": s + len(v), "label": lab})
    return out


def make_kit(root: Path, n_conv: int = 40) -> Path:
    turns, convs, gold, custs = [], [], [], []
    for c in range(n_conv):
        cid = f"CV{c:03d}"
        convs.append([cid, f"CU{c:03d}", "A1", "Agent Smithson", "chat", "fi", "2026-01-01", "x", "", "", "", "",
                      "3", "train", ""])
        custs.append([f"CU{c:03d}", "", f"Testi Asiakas{c}", "", "Testikatu 1", "00100", "Testila", "", "", "fi",
                      "", "", "", "", "", "", "", ""])
        word = "variant" + "abcdefghij"[c % 10]  # 10 template families (digits would collapse to #)
        rows = [
            (f"my email is user{c}@example.fi {word}", [(f"user{c}@example.fi", "EMAIL")]),
            (f"ok noted {word}", []),
            (f"call me 040 {1000000 + c} {word}", [(f"040 {1000000 + c}", "PHONE")]),
        ]
        for j, (text, vals) in enumerate(rows):
            tid = f"{cid}-{j}"
            turns.append([tid, cid, str(j + 1), "customer" if j != 1 else "agent", "", text])
            gold.append({"record_id": tid, "spans": _spans(text, *vals)})
    _w(root / "data/customer_service/turns.csv", ["turn_id", "conversation_id", "seq", "speaker", "ts", "text"], turns)
    _w(root / "data/customer_service/conversations.csv",
       ["conversation_id", "customer_id", "agent_id", "agent_name", "channel", "language", "started_ts", "intent",
        "sentiment", "csat", "resolved", "handle_time_s", "n_turns", "split", "agent_note"], convs)
    _w(root / "data/customer_service/customers.csv",
       ["customer_id", "customer_number", "full_name", "hetu", "street_address", "postcode", "city", "email", "phone",
        "preferred_language", "customer_since", "products", "contract_number", "payment_method", "iban",
        "marketing_consent", "payment_default_flag", "accessibility_needs"], custs)
    note = "contact a@b.fi"
    _w(root / "data/health/clinical_notes.csv", ["note_id", "note_text"], [["N1", note]])
    sp = root / "metadata/pii_spans"
    sp.mkdir(parents=True, exist_ok=True)
    with open(sp / "customer_service__turns__text.jsonl", "w", encoding="utf-8") as f:
        for g in gold:
            f.write(json.dumps(g) + "\n")
    with open(sp / "health__clinical_notes__note_text.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps({"record_id": "N1", "spans": _spans(note, ("a@b.fi", "EMAIL"))}) + "\n")
    return root


def _cli(kit, *extra):
    env = dict(os.environ, PYTHONPATH=str(SRC), PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1", TZ="UTC")
    p = subprocess.run([sys.executable, "-m", "pets_release.redaction_eval", "--kit", str(kit), "--report-only",
                        *extra], capture_output=True, text=True, env=env, timeout=600)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def test_real_cli_default_is_the_shipped_redactor(tmp_path):
    from pets_release.redactor import default_passes

    out = _cli(make_kit(tmp_path / "kit"))
    assert out["predictor"]["mode"] == "production"
    assert out["predictor"]["entry_point"] == "pets_release.redactor.redact_conversation"
    assert out["predictor"]["passes"] == [p.name for p in default_passes(require_lexicon=True)]
    # the structured pass finds the synthetic emails and phones: recall well above zero
    assert out["headline"]["full_train"]["micro_f2_all"]["recall"] > 0.5


def test_real_cli_regex_is_only_a_labelled_baseline(tmp_path):
    out = _cli(make_kit(tmp_path / "kit"), "--predictor", "regex-baseline")
    assert out["predictor"]["mode"] == "regex-baseline"
    assert "baseline" in out["predictor"]["note"].lower()


def test_cli_metrics_change_when_the_production_redactor_changes(monkeypatch, tmp_path):
    """Integration: disabling the shipped structured pass must change the CLI's numbers."""
    import pets_release.redaction_eval.__main__ as m
    from pets_release.redactor.structured import StructuredPass

    import contextlib
    import io

    kit = make_kit(tmp_path / "kit")

    def once():
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            assert m.main(["--kit", str(kit), "--report-only"]) == 0
        return json.loads(buf.getvalue())["headline"]

    before = once()
    monkeypatch.setattr(StructuredPass, "run", lambda self, view: iter(()))
    after = once()
    assert before["full_train"]["micro_f2_all"]["recall"] > after["full_train"]["micro_f2_all"]["recall"]


def test_production_predictor_redacts_whole_conversations_in_order():
    """Cross-turn behaviour: the predictor sees each conversation as one unit, in seq order."""
    from pets_release.redaction_eval.frame import build_frame
    from pets_release.redaction_eval.harness import predict_all
    from pets_release.redaction_eval import production

    seen = []

    class Spy:
        name = "spy"
        labels = frozenset({"PERSON"})

        def run(self, view):
            seen.append((view.conversation_id, [(t.turn_id, t.speaker) for t in view.turns]))
            return iter(())

    turns = [
        {"turn_id": "b", "conversation_id": "C1", "seq": "10", "speaker": "agent", "text": "y"},
        {"turn_id": "a", "conversation_id": "C1", "seq": "2", "speaker": "customer", "text": "x"},
        {"turn_id": "c", "conversation_id": "C2", "seq": "1", "speaker": "customer", "text": "z"},
    ]
    fr = build_frame(turns, [{"conversation_id": "C1", "split": "train"},
                             {"conversation_id": "C2", "split": "train"}], {})
    pred = predict_all(fr, production.ConversationPredictor([Spy()]))
    assert sorted(pred) == ["a", "b", "c"]
    assert seen == [("C1", [("a", "customer"), ("b", "agent")]), ("C2", [("c", "customer")])]


def test_dev_lexicon_factory_is_fitted_on_development_names_only():
    from pets_release.redaction_eval.frame import Frame
    from pets_release.redaction_eval import production

    dev = Frame(texts={"t1": "terve Zorbas Quenzel"}, gold={"t1": [{"start": 6, "end": 20, "label": "PERSON"}]},
                conversation_of={"t1": "C1"})
    gz = production.dev_gazetteer(dev)
    assert gz.family == frozenset({"Quenzel"}) and gz.given == frozenset({"Zorbas"})


def test_real_cli_reports_conversation_held_out(tmp_path):
    """#68 through the real CLI."""
    out = _cli(make_kit(tmp_path / "kit"), "--predictor", "regex-baseline")
    assert out["split_mode"] == "conversation"
    assert out["split"]["held_out_conversations"] > 0
    assert out["split"]["conversations_in_both_partitions"] == 0
    assert out["turn_held_out"]["satisfies_spec_conversation_boundary"] is False
    assert "held_out" in out["headline"]
