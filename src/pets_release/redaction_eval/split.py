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
    return _split_conversations(frame, fraction, seed)


def _components(sk: dict, conversation_of: dict) -> list:
    """Connected components of the conversation <-> skeleton graph: conversations that share any
    skeleton (any turn, gold-absent included) must land on the same side."""
    parent: dict = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for t in sorted(sk):
        a, b = find(("c", conversation_of[t])), find(("h", sk[t]))
        if a != b:
            parent[max(a, b)] = min(a, b)
    comps: dict = {}
    for t in sorted(sk):
        r = find(("c", conversation_of[t]))
        convs, hashes = comps.setdefault(r, (set(), set()))
        convs.add(conversation_of[t])
        hashes.add(sk[t])
    return [(sorted(c), h) for c, h in comps.values()]


def _split_conversations(frame, fraction: float, seed: str) -> Split:
    """Spec rule: a conversation is held out only if all its turns' skeletons are held out, and no held-out
    skeleton occurs in development. Hash-by-hash sampling holds out nothing when templates are shared
    widely, so whole skeleton components are held out instead: components in a seeded order, each taken
    while the held-out share of skeleton hashes stays <= `fraction`. Empty when no component fits."""
    sk = {tid: skeleton_hash(skeleton(frame.texts[tid], frame.gold.get(tid, []))) for tid in sorted(frame.texts)}
    n_hash = len(set(sk.values()))
    comps = sorted(_components(sk, frame.conversation_of),
                   key=lambda ch: (hashlib.sha256((seed + ch[0][0]).encode("utf-8")).hexdigest(), ch[0][0]))
    held_convs: set = set()
    held_hashes: set = set()
    for convs, hashes in comps:
        if (len(held_hashes) + len(hashes)) <= fraction * n_hash:
            held_convs.update(convs)
            held_hashes.update(hashes)
    held_turns = tuple(t for t in sorted(sk) if frame.conversation_of[t] in held_convs)
    dev_turns = tuple(t for t in sorted(sk) if frame.conversation_of[t] not in held_convs)
    held_sk = frozenset(sk[t] for t in held_turns)
    dev_sk = frozenset(sk[t] for t in dev_turns)
    assert_zero_overlap(held_sk, dev_sk)
    if set(frame.conversation_of[t] for t in held_turns) & set(frame.conversation_of[t] for t in dev_turns):
        raise ValueError("a conversation straddles held-out and development")
    return Split(
        held_out_conversations=tuple(sorted(held_convs)),
        dev_conversations=tuple(sorted({frame.conversation_of[t] for t in dev_turns})),
        held_out_turns=held_turns,
        dev_turns=dev_turns,
        held_out_skeletons=held_sk,
        dev_skeletons=dev_sk,
        unseen_skeleton_share=1.0 if held_turns else 0.0,  # by construction: no held-out skeleton is in dev
        unseen_span_skeleton_share=1.0 if held_turns else 0.0,
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
