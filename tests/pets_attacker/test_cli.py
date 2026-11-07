"""CLI on a synthetic mini-kit: aggregate-only JSON, exact key set."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from pets_attacker.cli import main
from pets_attacker.personas import AGGREGATE_KEYS
from pets_attacker.redteam import LINK_KEYS

RUNGS = {"ed_visits": {"arrival_ts": "ts.exact", "municipality": "keep"}}


def _rungs_file(root: Path) -> list:
    p = root / "rungs.json"
    p.write_text(json.dumps(RUNGS), encoding="utf-8")
    return ["--rungs", str(p)]


def _mini_kit(root: Path) -> Path:
    kit, rel = root / "kit", root / "rel"
    for d in ("data/health", "adversary", "truth", "metadata"):
        (kit / d).mkdir(parents=True)
    rel.mkdir()
    orig = pd.DataFrame({"visit_id": ["v0", "v1", "v2"], "patient_name": ["Anna Virtanen", "Pekka Korhonen", "Mari Nieminen"],
                         "municipality": ["Turku", "Raisio", "Turku"], "arrival_ts": ["2025-01-01T09:00:00", "2025-01-02T09:00:00", "2025-01-03T09:00:00"],
                         "icd10_primary": ["J10", "S72", "I21"]})
    orig.to_csv(kit / "data/health/ed_visits.csv", index=False)
    orig.drop(columns=["patient_name"]).to_csv(rel / "ed_visits.csv", index=False)
    pd.DataFrame({"protected_row": [0, 1, 2], "original_record_id": ["v0", "v1", "v2"]}).to_csv(rel / "rowmap_ed_visits.csv", index=False)
    pd.DataFrame({"record_id": ["v0", "v1", "v2"], "person_id": ["p0", "p1", "p2"]}).to_csv(kit / "truth/health__ed_visits.csv", index=False)
    pd.DataFrame({"adv_row_id": ["a0"], "published_date": ["2025-01-02"], "event_date": ["2025-01-01"], "place": ["Turku"],
                  "age_mentioned": [""], "sex_mentioned": [""], "name_mentioned": [""]}).to_csv(kit / "adversary/news_clips_health.csv", index=False)
    pd.DataFrame({"adv_row_id": ["a0"], "person_id": ["p0"]}).to_csv(kit / "truth/adversary__news_clips_health.csv", index=False)
    spec = {"attacks": [{"adversary": "news_clips_health", "dataset": "health", "table": "ed_visits", "sensitive": "icd10_primary",
                         "qis": [{"kind": "time", "adversary": ["event_date", "published_date"], "protected": ["arrival_ts"], "window": [96, 24]},
                                 {"kind": "exact", "adversary": ["place"], "protected": ["municipality"]}]}]}
    (kit / "metadata/attack_specs.json").write_text(json.dumps(spec), encoding="utf-8")
    return kit


def test_cli_emits_aggregates_only(tmp_path: Path):
    kit = _mini_kit(tmp_path)
    out = tmp_path / "out.json"
    assert main(["--kit", str(kit), "--release", str(tmp_path / "rel"), "--label", "t", "--out", str(out)] + _rungs_file(tmp_path)) == 0
    res = json.loads(out.read_text(encoding="utf-8"))
    assert set(res) == {"label", "broker", "insider", "red_team"}  # #139 adds the red team block
    assert set(res["broker"]) == {"news_clips_health"}
    for block in [res["broker"]["news_clips_health"], res["insider"]]:
        assert set(block) == set(AGGREGATE_KEYS)
        assert all(v is None or isinstance(v, (bool, int, float)) for v in block.values())
    red = res["red_team"]
    assert set(red) == {"cross_dataset", "range_aware", "attribute_inference"}
    for block in (red["cross_dataset"], red["range_aware"]):
        assert set(block) == set(LINK_KEYS)
        assert all(v is None or isinstance(v, (bool, int, float)) or k == "reason" for k, v in block.items())
    text = out.read_text(encoding="utf-8")
    for leaked in ("Anna", "Virtanen", "Turku", "v0", "p0"):
        assert leaked not in text


def test_cli_fails_closed_without_rowmap(tmp_path: Path):
    kit = _mini_kit(tmp_path)
    (tmp_path / "rel" / "rowmap_ed_visits.csv").unlink()
    assert main(["--kit", str(kit), "--release", str(tmp_path / "rel"), "--label", "t", "--out", str(tmp_path / "o.json")] + _rungs_file(tmp_path)) != 0
    assert not (tmp_path / "o.json").exists()


def _move_rowmap(tmp_path: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    return Path(str(dest / "rowmap_ed_visits.csv")) if (tmp_path / "rel" / "rowmap_ed_visits.csv").replace(dest / "rowmap_ed_visits.csv") else dest


def test_cli_accepts_a_scoring_dir_next_to_the_release(tmp_path: Path):
    kit = _mini_kit(tmp_path)
    scoring = tmp_path / "rel.scoring"
    _move_rowmap(tmp_path, scoring)
    out = tmp_path / "o.json"
    base = ["--kit", str(kit), "--release", str(tmp_path / "rel"), "--label", "t", "--out", str(out)] + _rungs_file(tmp_path)
    assert main(base) != 0  # no rowmap in the release dir and none named: refused
    assert main(base + ["--scoring-dir", str(scoring)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["insider"]["evaluated"] is True


def test_cli_accepts_an_explicit_rowmap_and_does_not_fall_back(tmp_path: Path):
    kit = _mini_kit(tmp_path)
    scoring = tmp_path / "elsewhere"
    _move_rowmap(tmp_path, scoring)
    out = tmp_path / "o.json"
    base = ["--kit", str(kit), "--release", str(tmp_path / "rel"), "--label", "t", "--out", str(out)] + _rungs_file(tmp_path)
    assert main(base + ["--rowmap", f"ed_visits={scoring / 'rowmap_ed_visits.csv'}"]) == 0
    # a planted rowmap in the release dir must not win over an explicit scoring dir that lacks one
    (tmp_path / "rel" / "rowmap_ed_visits.csv").write_text("protected_row,original_record_id\n", encoding="utf-8")
    out.unlink()
    assert main(base + ["--scoring-dir", str(tmp_path / "empty_scoring")]) != 0
    assert not out.exists()


def test_cli_refuses_a_bad_row_map(tmp_path: Path):
    kit = _mini_kit(tmp_path)
    (tmp_path / "rel" / "rowmap_ed_visits.csv").write_text("protected_row,original_record_id\n", encoding="utf-8")
    assert main(["--kit", str(kit), "--release", str(tmp_path / "rel"), "--label", "t", "--out", str(tmp_path / "o.json")] + _rungs_file(tmp_path)) != 0


def test_cli_refuses_without_rung_metadata_or_with_a_contradicting_one(tmp_path: Path):
    kit = _mini_kit(tmp_path)
    base = ["--kit", str(kit), "--release", str(tmp_path / "rel"), "--label", "t", "--out", str(tmp_path / "o.json")]
    assert main(base) != 0  # no --rungs: shape is never trusted
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"ed_visits": {"arrival_ts": "ts.day", "municipality": "keep"}}), encoding="utf-8")
    assert main(base + ["--rungs", str(bad)]) != 0  # cells carry times, rung says day
    partial = tmp_path / "partial.json"
    partial.write_text(json.dumps({"ed_visits": {"municipality": "keep"}}), encoding="utf-8")
    assert main(base + ["--rungs", str(partial)]) != 0
    assert not (tmp_path / "o.json").exists()
