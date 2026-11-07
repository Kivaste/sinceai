"""#68: the held-out frame holds out whole conversations (spec: a conversation is held out only if all its
turns' skeletons are). Turn-level numbers are separately labelled and never satisfy the floor.
Fixtures are small hand-made synthetic rows."""
from __future__ import annotations

from pets_release.redaction_eval import build_frame, split_by_skeleton
from pets_release.redaction_eval.frame import Frame
from pets_release.redaction_eval.harness import evaluate_frames
from pets_release.redaction_eval.split import skeleton, skeleton_hash


def sp(s, e, lab):
    return {"start": s, "end": e, "label": lab}


def _grouped_frame(groups=60, per=4):
    """Each group: `per` conversations of two turns whose two skeletons occur only inside the group."""
    turns, convs, gold = [], [], {}
    for g in range(groups):
        w = chr(97 + g % 26) + chr(97 + g // 26)
        for i in range(per):
            cid = f"C{g}_{i}"
            convs.append({"conversation_id": cid, "split": "train"})
            for j, stem in enumerate((f"hi {w} I am ", f"bye {w} from ")):
                text = stem + f"Anna{i}"
                tid = f"T{g}_{i}_{j}"
                turns.append({"turn_id": tid, "conversation_id": cid, "seq": str(j + 1), "speaker": "c", "text": text})
                gold[tid] = [sp(len(stem), len(text), "PERSON")]
    return build_frame(turns, convs, gold)


def _notes():
    return Frame(texts={"N1": "x a@b.fi"}, gold={"N1": [sp(2, 8, "EMAIL")]}, conversation_of={"N1": "N1"})


def _name_pred(t):
    i = t.find("Anna")
    return [sp(i, len(t), "PERSON")] if i >= 0 else []


def test_held_out_frame_is_whole_conversations_never_seen_in_development():
    fr = _grouped_frame()
    seen = []

    def factory(dev):
        seen.append(dev)
        return _name_pred

    rep = evaluate_frames(fr, _notes(), factory)
    assert rep["split_mode"] == "conversation"
    held_convs = {c for c in set(fr.conversation_of.values())
                  if all(fr.conversation_of[t] != c or t not in seen[0].texts for t in fr.texts)}
    assert held_convs, "strict frame must not be empty on a frame with independent templates"
    dev_convs = set(seen[0].conversation_of.values())
    assert not (held_convs & dev_convs)  # no turn of a held-out conversation reaches development
    held_turns = [t for t in fr.texts if fr.conversation_of[t] in held_convs]
    assert rep["held_out"]["n_records"] == len(held_turns)
    assert rep["split"]["conversations_in_both_partitions"] == 0
    # spec rule: every skeleton of a held-out conversation is unseen in development
    dev_sk = {skeleton_hash(skeleton(seen[0].texts[t], seen[0].gold[t])) for t in seen[0].texts}
    assert all(skeleton_hash(skeleton(fr.texts[t], fr.gold[t])) not in dev_sk for t in held_turns)


def test_strict_split_packs_whole_template_components():
    fr = _grouped_frame()
    s = split_by_skeleton(fr)
    assert s.held_out_conversations and s.dev_conversations
    assert len(s.held_out_turns) == 2 * len(s.held_out_conversations)
    assert not (s.held_out_skeletons & s.dev_skeletons)
    # whole template families are held out, close to the 20% target (hash sampling alone gets ~4% here)
    assert 0.15 <= s.held_out_turn_share <= 0.2 + 1e-9
    assert s == split_by_skeleton(fr)  # deterministic


def test_turn_level_numbers_are_separately_labelled():
    fr = _grouped_frame()
    rep = evaluate_frames(fr, _notes(), lambda d: _name_pred)
    t = rep["turn_held_out"]
    assert t["satisfies_spec_conversation_boundary"] is False
    assert t["split_mode"] == "turn" and "scores" in t and isinstance(t["conversations_in_both_partitions"], int)


def _shared_frame():
    # every conversation shares the "hello" skeleton -> one component, nothing can be held out strictly
    turns, convs, gold = [], [], {}
    for i in range(200):
        cid = f"C{i}"
        convs.append({"conversation_id": cid, "split": "train"})
        for j, w in enumerate(("hello", "x" + chr(97 + i % 26) + chr(97 + i // 26))):
            tid = f"T{i}_{j}"
            turns.append({"turn_id": tid, "conversation_id": cid, "text": f"{w} Anna"})
            gold[tid] = [sp(len(w) + 1, len(w) + 5, "PERSON")]
    return build_frame(turns, convs, gold)


def test_empty_strict_frame_is_unavailable_and_fails_the_floor():
    fr = _shared_frame()
    rep = evaluate_frames(fr, _notes(), lambda d: _name_pred, precision_floor=0.1)
    assert rep["held_out"] == {"status": "unavailable", "reason": rep["held_out"]["reason"]}
    assert rep["precision_floor"]["status"] == "unavailable"
    assert rep["passed"] is False  # turn-level precision is 1.0 here but must not satisfy the floor
    assert rep["turn_held_out"]["scores"]["micro_f2_all"]["precision"] == 1.0
    assert rep["person_twice_held_out"]["status"] == "not_measured"

