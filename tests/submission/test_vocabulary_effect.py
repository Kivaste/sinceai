"""CS-U5 in the masking effect is scored per input: no vocabulary computed for one frame is reused for another (#148 r3).

The pinned scorer (pets_eval u5_vocab) caches the common vocabulary under ("u5", id(frame), len(frame)). A frame freed
after one call lets the next frame of the same length get the same id and silently consume the old vocabulary.
Seam: ``cs_eval.vocabulary_effect`` in one process (the CLI runs it once per process, so the defect only shows here).

Rows (trigger -> result):
  frame A (common vocabulary {alpha, bravo}, all retained), then frame B of the same length (common {alpha, bravo,
  charlie, delta}, half retained), alternating many times in one process -> A before 1.0, B before 0.5, every time
"""
from __future__ import annotations

import pandas as pd

from pets_release.submission.cs_eval import vocabulary_effect

N = 25  # CS-U5's common vocabulary: tokens used in >= 25 conversations


def _frame(text: str) -> pd.DataFrame:
    return pd.DataFrame({"turn_id": [f"t{i}" for i in range(N)], "conversation_id": [f"c{i}" for i in range(N)],
                         "text": [text] * N}, dtype=str)


KEPT = {f"t{i}": "alpha bravo" for i in range(N)}  # for frame B: charlie and delta dropped, half the common tokens
MASKED = {f"t{i}": "[PERSON_1]" for i in range(N)}


def test_a_reused_frame_id_never_reuses_another_frames_vocabulary(monkeypatch):
    """Deterministic: every frame gets the same id in the pinned scorer (the id reuse the defect depends on)."""
    import pets_eval.utility.customer_service as cs

    monkeypatch.setattr(cs, "id", lambda _obj: 1, raising=False)
    a = vocabulary_effect(_frame("alpha bravo"), KEPT, MASKED)
    b = vocabulary_effect(_frame("alpha bravo charlie delta"), KEPT, MASKED)
    assert (a["status"], a["before"], a["after"]) == ("measured", 1.0, 0.0)
    assert (b["status"], b["before"], b["after"]) == ("measured", 0.5, 0.0), "another frame's vocabulary reused"


def test_each_frame_is_scored_with_its_own_vocabulary():
    """The natural case: frames freed between calls, ids reused by the allocator (seen within ~10 rounds)."""
    kept_a, kept_b, masked = KEPT, KEPT, MASKED
    for _ in range(300):
        a = vocabulary_effect(_frame("alpha bravo"), kept_a, masked)  # the frame is freed when the call returns
        b = vocabulary_effect(_frame("alpha bravo charlie delta"), kept_b, masked)
        assert (a["status"], a["before"], a["after"]) == ("measured", 1.0, 0.0)
        assert (b["status"], b["before"], b["after"]) == ("measured", 0.5, 0.0), "another frame's vocabulary reused"
