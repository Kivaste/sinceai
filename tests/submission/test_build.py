"""build_submission through its public seam: layout, contents, refusals, determinism.

Failure rows (trigger -> result):
  out inside the public repo tree / a clone of it      -> refused, nothing written
  out or its scoring folder already exists             -> refused
  no release                                           -> refused
  release tampered (table edited)                      -> refused (verify --full)
  release has a planted extra file / rowmap in it      -> refused
  release path passes through Briefs/ or truth/        -> refused
  row map missing / swapped / extra table's map        -> refused
  a scorecard that errors                              -> refused, nothing written
  duplicate dataset                                    -> refused
  planted truth/, .env, *.key next to the row maps     -> never copied
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pandas as pd
import pytest
from sub_helpers import TEST_KEY, git

from pets_release.kit import Kit
from pets_release.pseudonym import MasterKey
from pets_release.submission import SubmissionRefused, build_submission

MASTER = MasterKey.from_text(TEST_KEY)
REPO = Path(__file__).resolve().parents[2]


class FakeScorecard:
    """Records how the adapter is called; stands for the out-of-process kit evaluator."""

    def __init__(self, fail: str | None = None):
        self.calls, self.fail = [], fail

    def __call__(self, original_dir, protected_dir, *, scenario, root, rowmaps, lineage, out_dir):
        from pets_release.kiteval import ScorecardRejected

        if self.fail:
            raise ScorecardRejected(self.fail)
        names = sorted(p.name for p in Path(protected_dir).iterdir())
        self.calls.append({"scenario": scenario, "rowmaps": sorted(rowmaps), "lineage": sorted(lineage),
                           "protected": names, "original": Path(original_dir).name})
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        (Path(out_dir) / "scorecard.json").write_text("{}", encoding="utf-8")
        return {"scenario": scenario, "dataset": Path(original_dir).name,
                "summary": {"privacy": 1.0, "utility": 1.0, "composite": 1.0}}


def build(pair, out, *, scorecard=None, releases=None, **kw):
    kit, rel = pair
    return build_submission(kit=Kit(kit), releases=releases if releases is not None else [rel], out=out,
                            master=MASTER, scorecard=scorecard or FakeScorecard(), **kw)


def tree(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def test_layout_is_exactly_the_organiser_layout(world, tmp_path):
    _, rel = world
    tables = sorted(p.name for p in rel.glob("*.csv"))
    assert tables  # the release has tables
    expected = sorted(
        ["customer_service_eval_redacted.csv", "customer_service_eval_spans.jsonl", "unseen_field_labels.csv",
         "health/privacy_manifest.json"]
        + [f"health/{t}" for t in tables] + [f"health/rowmap_{t}" for t in tables])
    res = build(world, tmp_path / "pets_submission")
    files = tree(res.out)
    assert sorted(files) == expected
    assert res.files == files


def test_tables_and_row_maps_are_the_release_bytes(world, tmp_path):
    _, rel = world
    res = build(world, tmp_path / "s")
    for f in sorted(rel.iterdir()):
        assert (res.out / "health" / f.name).read_bytes() == f.read_bytes()
    maps = sorted(rel.with_name("health.scoring").glob("rowmap_*.csv"))
    assert maps
    for f in maps:
        assert (res.out / "health" / f.name).read_bytes() == f.read_bytes()


def test_scorecard_gets_explicit_row_maps_lineage_and_a_row_map_free_release(world, tmp_path):
    sc = FakeScorecard()
    res = build(world, tmp_path / "s", scorecard=sc)
    (call,) = sc.calls
    tables = sorted(p.stem for p in (res.out / "health").glob("*.csv") if not p.name.startswith("rowmap_"))
    assert call["scenario"] == "HEALTH-S1" and call["original"] == "health"
    assert call["rowmaps"] == tables and call["lineage"] == tables
    assert not any(n.startswith("rowmap_") for n in call["protected"])
    assert res.scoring.name == "s.scoring" and (res.scoring / "health" / "scorecard.json").is_file()


def test_unseen_labels_cover_every_column_in_the_unseen_format(world, tmp_path):
    res = build(world, tmp_path / "s")
    df = pd.read_csv(res.out / "unseen_field_labels.csv", dtype=str, keep_default_na=False)
    assert list(df.columns) == ["column", "privacy_role", "subtype"]
    assert list(df["column"]) == ["c01", "c02", "c03"]
    assert (df["privacy_role"] != "").all() and (df["subtype"] != "").all()


def test_cs_eval_outputs_cover_exactly_the_eval_turns(world, tmp_path):
    res = build(world, tmp_path / "s")
    red = pd.read_csv(res.out / "customer_service_eval_redacted.csv", dtype=str, keep_default_na=False)
    assert list(red.columns) == ["turn_id", "text"]
    assert list(red["turn_id"]) == ["t1", "t2", "t3", "t4"]  # eval split only (t5 is train), sorted
    lines = [json.loads(x) for x in (res.out / "customer_service_eval_spans.jsonl").read_text("utf-8").splitlines()]
    assert [r["record_id"] for r in lines] == ["t1", "t2", "t3", "t4"]
    spans = {r["record_id"]: r["spans"] for r in lines}
    s = spans["t1"][0]
    assert set(s) == {"start", "end", "label"}
    assert "Hello my email is anna.testi@example.com please call"[s["start"]:s["end"]] == "anna.testi@example.com"
    assert s["label"] == "EMAIL"
    assert "anna.testi@example.com" not in red.loc[red.turn_id == "t1", "text"].iloc[0]
    assert spans["t4"] == [] and red.loc[red.turn_id == "t4", "text"].iloc[0] == ""


def test_reruns_are_byte_identical(world, tmp_path):
    a = build(world, tmp_path / "a" / "s")
    b = build(world, tmp_path / "b" / "s")
    assert tree(a.out) == tree(b.out)
    assert (a.scoring / "submission_index.json").read_bytes() == (b.scoring / "submission_index.json").read_bytes()


def test_index_lists_every_file_with_its_digest(world, tmp_path):
    res = build(world, tmp_path / "s")
    idx = json.loads((res.scoring / "submission_index.json").read_text("utf-8"))
    assert idx["files"] == res.files
    assert [d["dataset"] for d in idx["datasets"]] == ["health"]
    assert idx["datasets"][0]["scorecard"]["summary"] == {"privacy": 1.0, "utility": 1.0, "composite": 1.0}


# ---------- refusals ----------

def _refused(pair, out, **kw):
    with pytest.raises(SubmissionRefused) as e:
        build(pair, out, **kw)
    assert not Path(out).exists() and not Path(str(out) + ".scoring").exists()
    return e.value.code


def test_refuses_out_inside_the_public_repo_tree(world):
    assert _refused(world, REPO / "out" / "pets_submission") == "out_in_public_repo"


def test_refuses_out_inside_a_clone_of_the_public_repo(world, tmp_path):
    repo = tmp_path / "clone"
    repo.mkdir()
    git("init", "-q", cwd=repo)
    public = git("config", "--get", "remote.origin.url", cwd=REPO).stdout.strip()
    git("remote", "add", "origin", public, cwd=repo)
    assert _refused(world, repo / "deep" / "pets_submission") == "out_in_public_repo"


def test_allows_out_inside_a_different_private_repo(world, tmp_path):
    repo = tmp_path / "private"
    repo.mkdir()
    git("init", "-q", cwd=repo)
    git("remote", "add", "origin", "https://github.com/Suhtetark-Kool/trusted-since-ai.git", cwd=repo)
    assert build(world, repo / "pets_submission").out.is_dir()


def test_refuses_existing_out_and_existing_scoring(world, tmp_path):
    (tmp_path / "s").mkdir()
    with pytest.raises(SubmissionRefused) as e:
        build(world, tmp_path / "s")
    assert e.value.code == "out_exists"
    (tmp_path / "t.scoring").mkdir()
    with pytest.raises(SubmissionRefused) as e:
        build(world, tmp_path / "t")
    assert e.value.code == "out_exists"


def test_refuses_without_releases(world, tmp_path):
    assert _refused(world, tmp_path / "s", releases=[]) == "no_release"


def test_refuses_duplicate_dataset(world, tmp_path):
    _, rel = world
    assert _refused(world, tmp_path / "s", releases=[rel, rel]) == "duplicate_dataset"


def test_refuses_tampered_release(fresh, tmp_path):
    _, rel = fresh
    p = rel / "ed_visits.csv"
    p.write_bytes(p.read_bytes() + b"x")
    assert _refused(fresh, tmp_path / "s") == "release_not_verified"


def test_refuses_planted_file_in_release_folder(fresh, tmp_path):
    _, rel = fresh
    (rel / "notes.txt").write_text("planted", encoding="utf-8")
    assert _refused(fresh, tmp_path / "s") == "release_not_verified"


def test_refuses_planted_rowmap_in_release_folder(fresh, tmp_path):
    _, rel = fresh
    shutil.copyfile(rel.with_name("health.scoring") / "rowmap_ed_visits.csv", rel / "rowmap_ed_visits.csv")
    assert _refused(fresh, tmp_path / "s") == "release_not_verified"


@pytest.mark.parametrize("part", ["Briefs", "truth"])
def test_refuses_release_under_a_forbidden_path_component(world, tmp_path, part):
    kit, rel = world
    dst = tmp_path / part / "health"
    shutil.copytree(rel, dst)
    shutil.copytree(rel.with_name("health.scoring"), dst.with_name("health.scoring"))
    assert _refused((kit, dst), tmp_path / "s") == "forbidden_source_path"


def test_refuses_missing_row_map(fresh, tmp_path):
    _, rel = fresh
    (rel.with_name("health.scoring") / "rowmap_ed_visits.csv").unlink()
    assert _refused(fresh, tmp_path / "s") == "rowmap_missing"


def test_refuses_row_map_with_swapped_keys(fresh, tmp_path):
    _, rel = fresh
    p = rel.with_name("health.scoring") / "rowmap_ed_visits.csv"
    df = pd.read_csv(p, dtype=str, keep_default_na=False)
    df["original_record_id"] = list(df["original_record_id"][1:]) + [df["original_record_id"].iloc[0]]
    df.to_csv(p, index=False, lineterminator="\n")
    assert _refused(fresh, tmp_path / "s") == "rowmap_invalid"


def test_refuses_row_map_for_a_table_the_release_does_not_have(fresh, tmp_path):
    _, rel = fresh
    sd = rel.with_name("health.scoring")
    shutil.copyfile(sd / "rowmap_ed_visits.csv", sd / "rowmap_ghost.csv")
    assert _refused(fresh, tmp_path / "s") == "rowmap_unexpected"


def test_refuses_when_the_scorecard_errors(world, tmp_path):
    assert _refused(world, tmp_path / "s", scorecard=FakeScorecard(fail="evaluator_failed")) == "scorecard_rejected"


def test_planted_truth_env_and_key_files_are_never_copied(fresh, tmp_path):
    _, rel = fresh
    sd = rel.with_name("health.scoring")
    (sd / "truth").mkdir()
    (sd / "truth" / "identity.csv").write_text("who,is,who\n", encoding="utf-8")
    (sd / ".env").write_text("PETS_HMAC_KEY=x\n", encoding="utf-8")
    (sd / "release.key").write_text("k", encoding="utf-8")
    res = build(fresh, tmp_path / "s")
    for p in tree(res.out):
        assert "truth" not in p and ".env" not in p and not p.endswith(".key")
    assert "health/rowmap_ed_visits.csv" in res.files


def test_a_failed_build_leaves_no_temporary_folder(world, tmp_path):
    out = tmp_path / "x" / "s"
    with pytest.raises(SubmissionRefused):
        build(world, out, scorecard=FakeScorecard(fail="evaluator_failed"))
    assert not list((tmp_path / "x").glob("*"))


def test_refuses_when_the_scorecard_crashes(world, tmp_path):
    class Crash:
        def __call__(self, *a, **k):
            raise FileNotFoundError("boom")

    assert _refused(world, tmp_path / "s", scorecard=Crash()) == "scorecard_error"
