"""CSV writers emit LF on every platform and the same bytes on every run (follow-up #83).

Rows (trigger -> result):
  measure.core identity row maps   -> no CR byte, byte-identical on two runs
  spotcheck sheet                  -> no CR byte, byte-identical on two runs
"""
from __future__ import annotations

from pathlib import Path

from pets_release.measure.core import _identity_inputs
from pets_release.redaction_eval.frame import build_frame
from pets_release.redaction_eval.spotcheck import export_spot_check


def test_identity_row_maps_are_lf_and_stable(tmp_path):
    orig = tmp_path / "orig"
    orig.mkdir()
    (orig / "t.csv").write_bytes(b"rid,v\nr1,a\nr2,b\n")
    outs = []
    for i in (1, 2):
        _, maps, _ = _identity_inputs(orig, ["t"], {"t": "rid"}, tmp_path / f"o{i}")
        outs.append(maps["t"].read_bytes())
    assert outs[0] == outs[1] and b"\r" not in outs[0]


def test_spot_check_sheet_is_lf_and_stable(tmp_path):
    fr = build_frame([{"turn_id": "t1", "conversation_id": "c1", "text": "hello"},
                      {"turn_id": "t2", "conversation_id": "c1", "text": "world"}],
                     [{"conversation_id": "c1", "split": "train"}], {})
    data = []
    for i in (1, 2):
        p = tmp_path / f"s{i}.csv"
        export_spot_check(fr, {}, p, n=2, repo_root=Path(__file__).resolve().parents[2])
        data.append(p.read_bytes())
    assert data[0] == data[1] and b"\r" not in data[0]
