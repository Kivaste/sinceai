"""Tier rules: measured/real-kit -> slow; unlisted mini-kit/CLI smoke -> fast.

Failure rows cover exact parametrized IDs, inherited kit markers, transitive kit
fixtures, planted list paths, and real pytest marker deselection (not skipping).
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def policy(request):
    return request.config.pluginmanager.get_plugin(str(ROOT / "tests" / "conftest.py"))


def item(nodeid="tests/example.py::test_small", fixtures=(), kit=False):
    marks = [pytest.mark.kit.mark] if kit else []
    return SimpleNamespace(
        nodeid=nodeid,
        fixturenames=fixtures,
        get_closest_marker=lambda name: next((m for m in reversed(marks) if m.name == name), None),
        add_marker=lambda marker: marks.append(marker.mark),
    )


@pytest.mark.parametrize("fixtures,kit", [((), True), (("wrapper", "kit_root"), False)])
def test_real_kit_dependencies_are_slow(policy, fixtures, kit):
    test = item(fixtures=fixtures, kit=kit)
    policy.pytest_collection_modifyitems([test])
    assert test.get_closest_marker("slow") is not None


def test_measured_ids_match_exactly_and_synthetic_kit_stays_fast(policy, monkeypatch, tmp_path):
    manifest = tmp_path / "slow_tests.txt"
    manifest.write_text("# measured\ntests/example.py::test_heavy[a b]\n", encoding="utf-8")
    monkeypatch.setattr(policy, "SLOW_TESTS_PATH", manifest)
    tests = [item("tests/example.py::test_heavy[a b]"), item("tests/example.py::test_heavy[a]"),
             item(fixtures=("make_kit", "kit", "mini_kit", "cli"))]
    policy.pytest_collection_modifyitems(tests)
    assert [t.get_closest_marker("slow") is not None for t in tests] == [True, False, False]


def test_cli_smoke_survives_timing_but_never_real_kit(policy, monkeypatch, tmp_path):
    manifest = tmp_path / "slow_tests.txt"
    manifest.write_text("\n".join(sorted(policy.FAST_CLI_SMOKE)) + "\n", encoding="utf-8")
    monkeypatch.setattr(policy, "SLOW_TESTS_PATH", manifest)
    tests = [item(nodeid) for nodeid in sorted(policy.FAST_CLI_SMOKE)]
    real = item(min(policy.FAST_CLI_SMOKE), fixtures=("kit_root",))
    policy.pytest_collection_modifyitems([*tests, real])
    assert len(tests) >= 3
    assert all(t.get_closest_marker("slow") is None for t in tests)
    assert real.get_closest_marker("slow") is not None


def test_missing_canonical_list_fails_despite_planted_cwd_list(policy, monkeypatch, tmp_path):
    monkeypatch.setattr(policy, "SLOW_TESTS_PATH", tmp_path / "canonical" / "slow_tests.txt")
    (tmp_path / "slow_tests.txt").write_text("", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(pytest.UsageError, match="slow_tests.txt"):
        policy.pytest_collection_modifyitems([item()])


def test_production_hook_deselects_only_when_requested(tmp_path):
    tests = tmp_path / "tests"
    tests.mkdir()
    shutil.copyfile(ROOT / "tests" / "conftest.py", tests / "conftest.py")
    (tests / "slow_tests.txt").write_text("tests/test_sample.py::test_measured\n", encoding="utf-8")
    (tmp_path / "pytest.ini").write_text("[pytest]\nmarkers =\n    kit: real kit\n    slow: heavy\n", encoding="utf-8")
    (tests / "test_sample.py").write_text(
        "import pytest\n"
        "def test_small(): pass\n"
        "def test_measured(): pass\n"
        "@pytest.mark.kit\ndef test_real(): pass\n"
        "@pytest.fixture\ndef wrapped(kit_root): return kit_root\n"
        "def test_transitive(wrapped): pass\n", encoding="utf-8",
    )
    env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTHONUTF8="1",
               PYTHONDONTWRITEBYTECODE="1", TZ="UTC")
    for selection, expected in [((), "4 tests collected"), (("-m", "not slow"), "1/4 tests collected")]:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", *selection],
            cwd=tmp_path, env=env, capture_output=True, text=True, encoding="utf-8", check=False,
        )
        assert result.returncode == 0, result.stderr
        assert expected in result.stdout


def test_live_collection_preserves_synthetic_cli_and_honours_slow_list(policy, tmp_path):
    """Exercise the production hook and pytest's actual -m deselection, not a model of it."""
    import json

    snapshot = tmp_path / "collection.json"
    (tmp_path / "tier_snapshot.py").write_text(
        "import json, os\n"
        "from pathlib import Path\n"
        "deselected = []\n"
        "def pytest_deselected(items): deselected.extend(items)\n"
        "def pytest_collection_finish(session):\n"
        "    all_items = [*session.items, *deselected]\n"
        "    Path(os.environ['TIER_SNAPSHOT']).write_text(json.dumps({\n"
        "        'fast': [i.nodeid for i in session.items],\n"
        "        'slow': [i.nodeid for i in all_items if i.get_closest_marker('slow')],\n"
        "    }), encoding='utf-8')\n", encoding="utf-8",
    )
    env = dict(os.environ, TIER_SNAPSHOT=str(snapshot),
               PYTHONPATH=os.pathsep.join((str(tmp_path), str(ROOT / "src"))))
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "--collect-only", "-q",
         "-p", "no:cacheprovider", "-p", "tier_snapshot", "-m", "not slow"],
        cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    collected = json.loads(snapshot.read_text(encoding="utf-8"))
    required_fast = {
        "tests/run/test_purpose_gate.py::test_failing_purpose_checks_refuse_publication",
        "tests/run/test_purpose_gate.py::test_full_verify_fails_when_signed_scores_differ_from_rerun",
        "tests/run/test_purpose_gate.py::test_full_verify_reruns_purpose_checks",
        "tests/run/test_recipient_cli.py::test_each_recipient_release_verifies_in_both_tiers",
        "tests/checks/test_runner.py::test_cli_refuses_planted_card_and_passes_valid",
        "tests/manifest/test_cli.py::test_duplicate_key_fails",
        "tests/manifest/test_cli.py::test_non_canonical_bytes_fail",
        "tests/manifest/test_cli.py::test_mutated_copies_fail_with_exit_1[_missing-$.exportAssertions: required]",
        "tests/verify/test_recipient.py::test_planted_card_fails_even_with_rebound_digests",
        "tests/verify/test_full.py::test_full_cli_bad_signature_fails",
    }
    assert required_fast <= set(collected["fast"]), sorted(required_fast - set(collected["fast"]))
    assert policy.FAST_CLI_SMOKE <= set(collected["fast"])
    listed_slow = {
        line for line in (ROOT / "tests" / "slow_tests.txt").read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    }
    assert listed_slow <= set(collected["slow"]), sorted(listed_slow - set(collected["slow"]))


@pytest.fixture
def generator():
    spec = importlib.util.spec_from_file_location("slow_list_generator", ROOT / "tools" / "list_slow_tests.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_duration_parser_sums_phases_and_preserves_parameter_spaces(generator):
    log = ("2.00s call tests/a.py::test_a[x y]\n"
           "1.25s setup tests/a.py::test_b\n1.00s call tests/a.py::test_b\n"
           "1.99s call tests/a.py::test_small\n")
    assert generator.parse_durations(log, threshold=2.0) == {
        "tests/a.py::test_a[x y]", "tests/a.py::test_b",
    }


def test_generator_refuses_missing_duration_report(generator):
    with pytest.raises(ValueError, match="duration"):
        generator.parse_durations("2000 passed in 3.00s", threshold=2.0)


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16"])
def test_generator_reads_powershell_and_utf8_logs(generator, tmp_path, encoding):
    log = tmp_path / "profile.log"
    text = "2.00s call tests/a.py::test_a\n1 passed in 2.00s\n"
    log.write_text(text, encoding=encoding)
    assert generator.read_duration_log(log) == text


def test_generator_includes_real_kit_and_exempts_only_synthetic_smoke(generator):
    assert generator.select_slow({"measured", "smoke"}, {"real", "real_smoke"},
                                 {"smoke", "real_smoke"}) == {"measured", "real", "real_smoke"}


def test_failed_profile_requires_explicit_timing_only_opt_in(generator, monkeypatch, tmp_path, capsys):
    tests = tmp_path / "tests"
    tests.mkdir()
    shutil.copyfile(ROOT / "tests" / "conftest.py", tests / "conftest.py")
    log = tmp_path / "profile.log"
    log.write_text("2.00s call tests/a.py::test_a\n1 failed, 2 passed, 1 skipped in 3.00s\n", encoding="utf-8")
    monkeypatch.setattr(generator, "ROOT", tmp_path)

    def collect(args, plugins):
        plugins[0].collected = {"tests/a.py::test_a"}
        plugins[0].real_kit = set()
        return pytest.ExitCode.OK

    monkeypatch.setattr(generator.pytest, "main", collect)
    monkeypatch.setattr(sys, "argv", ["list_slow_tests.py", str(log)])
    with pytest.raises(SystemExit) as exc:
        generator.main()
    assert exc.value.code == 2
    assert not (tests / "slow_tests.txt").exists()
    monkeypatch.setattr(sys, "argv", ["list_slow_tests.py", str(log), "--allow-failed-profile"])
    assert generator.main() == 0
    assert "not pass evidence" in capsys.readouterr().err
    assert "tests/a.py::test_a\n" in (tests / "slow_tests.txt").read_text(encoding="utf-8")
