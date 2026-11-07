"""Template-held-out split by skeleton hash."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

HELD_OUT_FRACTION = 0.2
_DIGITS = re.compile(r"\d+")
_WS = re.compile(r"\s+")


def skeleton(text: str, spans) -> str:
    """Text with each gold span replaced by its label token, remaining digit runs -> '#',
    lowercased, whitespace collapsed."""
    out, pos = [], 0
    for s in sorted(spans, key=lambda s: (s["start"], s["end"])):
        if s["start"] < pos:
            continue  # overlapping gold span; keep the first
        out.append(text[pos:s["start"]])
        out.append(f"<{s['label']}>")
        pos = s["end"]
    out.append(text[pos:])
    t = _DIGITS.sub("#", "".join(out)).lower()
    return _WS.sub(" ", t).strip()


def skeleton_hash(sk: str) -> str:
    return hashlib.sha256(sk.encode("utf-8")).hexdigest()


def _is_held_hash(h: str, fraction: float, seed: str) -> bool:
    v = int(hashlib.sha256((seed + h).encode("ascii")).hexdigest()[:12], 16) / float(16**12)
    return v < fraction


def assert_zero_overlap(held_out_skeletons, dev_skeletons) -> None:
    both = set(held_out_skeletons) & set(dev_skeletons)
    if both:
        raise ValueError(f"{len(both)} skeleton(s) shared between held-out and development")


@dataclass(frozen=True)
class Split:
    held_out_conversations: tuple
    dev_conversations: tuple
    held_out_turns: tuple
    dev_turns: tuple
    held_out_skeletons: frozenset
    dev_skeletons: frozenset
    unseen_skeleton_share: float  # share of ALL held-out turns whose skeleton never occurs in development
    unseen_span_skeleton_share: float  # same, restricted to turns that carry gold spans (1.0 by construction)
    held_out_turn_share: float

    def summary(self) -> dict:
        return {
            "held_out_conversations": len(self.held_out_conversations),
            "dev_conversations": len(self.dev_conversations),
            "held_out_turns": len(self.held_out_turns),
            "dev_turns": len(self.dev_turns),
            "held_out_turn_share": round(self.held_out_turn_share, 4),
            "unseen_skeleton_share": round(self.unseen_skeleton_share, 4),
            "unseen_span_skeleton_share": round(self.unseen_span_skeleton_share, 4),
            "skeleton_overlap": len(self.held_out_skeletons & self.dev_skeletons),
        }


def split_by_skeleton(frame, fraction: float = HELD_OUT_FRACTION, seed: str = "pets-redaction-split-v1",
                      mode: str = "conversation") -> Split:
    if mode == "turn":
        return _split_turns(frame, fraction, seed)
    if mode != "conversation":
        raise ValueError(mode)
    """Hold out `fraction` of skeleton hashes. A conversation is held out only if all its turns'
    span-bearing skeletons are held out (turns without gold spans carry no template and would make every
    conversation ineligible because of shared boilerplate; they travel with their conversation); held-out hashes that also appear in development are returned to
    development until stable, so the overlap is zero by construction and then asserted."""
    sk = {tid: skeleton_hash(skeleton(frame.texts[tid], frame.gold.get(tid, []))) for tid in sorted(frame.texts)}
    by_conv: dict = {}
    for tid in sorted(sk):
        by_conv.setdefault(frame.conversation_of[tid], []).append(tid)
    has_span = {t for t in sk if frame.gold.get(t)}
    key = {c: [t for t in ts if t in has_span] for c, ts in by_conv.items()}
    held = {h for h in {sk[t] for t in has_span} if _is_held_hash(h, fraction, seed)}
    while True:
        dev_hashes = {sk[t] for c, ts in key.items() if not (ts and all(sk[t] in held for t in ts)) for t in ts}
        shrunk = held - dev_hashes
        if shrunk == held:
            break
        held = shrunk
    held_convs = sorted(c for c, ts in key.items() if ts and all(sk[t] in held for t in ts))
    held_set = set(held_convs)
    dev_convs = sorted(c for c in by_conv if c not in held_set)
    held_turns = tuple(t for c in held_convs for t in by_conv[c])
    dev_turns = tuple(t for c in dev_convs for t in by_conv[c])
    held_sk = frozenset(sk[t] for t in held_turns if t in has_span)
    dev_sk = frozenset(sk[t] for t in dev_turns if t in has_span)
    assert_zero_overlap(held_sk, dev_sk)
    dev_all = {sk[t] for t in dev_turns}
    unseen = sum(1 for t in held_turns if sk[t] not in dev_all)
    return Split(
        held_out_conversations=tuple(held_convs),
        dev_conversations=tuple(dev_convs),
        held_out_turns=held_turns,
        dev_turns=dev_turns,
        held_out_skeletons=held_sk,
        dev_skeletons=dev_sk,
        unseen_skeleton_share=(unseen / len(held_turns)) if held_turns else 0.0,
        unseen_span_skeleton_share=1.0 if held_sk else 0.0,
        held_out_turn_share=len(held_turns) / len(sk) if sk else 0.0,
    )


def _split_turns(frame, fraction: float, seed: str) -> Split:
    """Turn-level variant: a turn is held out iff its skeleton hash is held out (all turns, incl.
    gold-absent). Zero overlap is by identity of the hash. Needed because on the real kit the strict
    conversation rule holds out nothing (every conversation contains a skeleton shared with another).
    `held_out_conversations` lists only conversations whose every turn is held out (informational)."""
    sk = {tid: skeleton_hash(skeleton(frame.texts[tid], frame.gold.get(tid, []))) for tid in sorted(frame.texts)}
    held = {h for h in set(sk.values()) if _is_held_hash(h, fraction, seed)}
    held_turns = tuple(t for t in sorted(sk) if sk[t] in held)
    dev_turns = tuple(t for t in sorted(sk) if sk[t] not in held)
    held_sk = frozenset(sk[t] for t in held_turns)
    dev_sk = frozenset(sk[t] for t in dev_turns)
    assert_zero_overlap(held_sk, dev_sk)
    by_conv: dict = {}
    for t in sorted(sk):
        by_conv.setdefault(frame.conversation_of[t], []).append(t)
    full = sorted(c for c, ts in by_conv.items() if all(sk[t] in held for t in ts))
    rest = sorted(c for c in by_conv if c not in set(full))
    return Split(
        held_out_conversations=tuple(full), dev_conversations=tuple(rest),
        held_out_turns=held_turns, dev_turns=dev_turns,
        held_out_skeletons=held_sk, dev_skeletons=dev_sk,
        unseen_skeleton_share=(1.0 if held_turns else 0.0),
        unseen_span_skeleton_share=(1.0 if held_turns else 0.0),
        held_out_turn_share=len(held_turns) / len(sk) if sk else 0.0,
    )
