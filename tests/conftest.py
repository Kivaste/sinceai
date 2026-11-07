"""Shared fixtures for the scaffold ticket. Synthetic rows only."""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
PYTHON = sys.executable

_CHECKOUT_BASELINE = pytest.StashKey[dict[Path, set[str]]]()


def _guard_git(directory: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(directory), *args], capture_output=True,
        text=True, encoding="utf-8", check=False,
    )
    if result.returncode:
        raise pytest.UsageError("checkout write guard: Git identity/status unavailable")
    return result.stdout


def _dirty_paths(root: Path) -> set[str]:
    # NUL records preserve spaces, quoting and newlines. A rename has two paths.
    records = iter(_guard_git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all").split("\0"))
    paths = set()
    for record in records:
        if not record:
            continue
        paths.add(record[3:])
        if "R" in record[:2] or "C" in record[:2]:
            paths.add(next(records))
    return paths


def _literal_test_path(node, source: Path) -> Path | None:
    """Interpret only literal pathlib expressions, never execute test source."""
    if (isinstance(node, ast.Call) and len(node.args) == 1 and not node.keywords
            and isinstance(node.func, ast.Name) and node.func.id == "Path"):
        arg = node.args[0]
        if isinstance(arg, ast.Name) and arg.id == "__file__":
            return source
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return Path(arg.value)
    if (isinstance(node, ast.Call) and not node.args and not node.keywords
            and isinstance(node.func, ast.Attribute) and node.func.attr in {"resolve", "absolute"}):
        path = _literal_test_path(node.func.value, source)
        return path.resolve() if path is not None else None
    if isinstance(node, ast.Attribute) and node.attr == "parent":
        path = _literal_test_path(node.value, source)
        return path.parent if path is not None else None
    if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute)
            and node.value.attr == "parents" and isinstance(node.slice, ast.Constant)):
        path = _literal_test_path(node.value.value, source)
        if path is not None:
            return path.parents[node.slice.value]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        path = _literal_test_path(node.left, source)
        if path is not None and isinstance(node.right, ast.Constant) and isinstance(node.right.value, str):
            return path / node.right.value
    return None


def _check_test_roots(root: Path):
    """Check helpers, conftests and function-local resolutions before tests run.

    A parents[n] reference into tests/ is legitimate for fixtures/imports. It
    must stay inside this checkout; a repo-root assignment must equal Git's root.
    """
    for source in sorted((root / "tests").rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8-sig"), filename=str(source))
        for node in ast.walk(tree):
            named_root = False
            strict_root = False
            expression = node
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                strict_root = any(
                    isinstance(t, ast.Name) and t.id in {"ROOT", "REPO", "REPO_ROOT"}
                    for t in targets
                )
                named_root = any(
                    isinstance(t, ast.Name) and t.id.lower() in {"root", "repo", "repo_root"}
                    for t in targets
                )
                expression = node.value
            parent_ref = isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute) \
                and node.value.attr == "parents"
            if not named_root and not parent_ref:
                continue
            path = _literal_test_path(expression, source)
            if path is None:
                if strict_root:
                    raise pytest.UsageError(
                        f"checkout root guard: {source.relative_to(root)}:{node.lineno} "
                        "repo-root resolution must be a literal pathlib expression"
                    )
                continue  # tmp_path/kit roots and non-literal expressions are not repo resolutions.
            path = path.resolve()
            if (named_root and path != root) or (parent_ref and not path.is_relative_to(root)):
                raise pytest.UsageError(
                    f"checkout root guard: {source.relative_to(root)}:{node.lineno} "
                    "resolves outside the running tests' Git worktree root"
                )


def pytest_sessionstart(session):
    """Take one baseline per checkout, before collection or worker startup.

    Fixtures never execute in the xdist controller, so its session hooks own the
    same autouse guard's lifecycle. Workers must not take independent baselines.
    """
    if hasattr(session.config, "workerinput"):
        return
    identity = _guard_git(
        Path(__file__).resolve().parent, "rev-parse", "--path-format=absolute",
        "--show-toplevel", "--git-common-dir",
    ).splitlines()
    root, common = map(Path, identity)
    roots = {root.resolve(), common.resolve().parent}
    session.config.stash[_CHECKOUT_BASELINE] = {
        checkout: _dirty_paths(checkout) for checkout in sorted(roots)
    }
    _check_test_roots(root.resolve())


@pytest.fixture(scope="session", autouse=True)
def _checkout_write_guard(request):
    """Controller hooks bracket all workers and fixture teardowns, once only."""
    if not hasattr(request.config, "workerinput"):
        assert _CHECKOUT_BASELINE in request.config.stash, "checkout write guard did not start"


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    if hasattr(session.config, "workerinput") or _CHECKOUT_BASELINE not in session.config.stash:
        return
    factory = getattr(session.config, "_tmp_path_factory", None)
    basetemp = getattr(factory, "_basetemp", None)
    new_paths = []
    for root, baseline in session.config.stash[_CHECKOUT_BASELINE].items():
        for relative in sorted(_dirty_paths(root) - baseline):
            path = (root / relative).resolve()
            if basetemp is None or not path.is_relative_to(basetemp.resolve()):
                new_paths.append(str(path))
    if new_paths:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        if reporter is not None:
            reporter.write_sep("=", "checkout write guard: new dirty paths", red=True)
            for path in new_paths:
                reporter.write_line(path, red=True)

VISITS_CSV = "id,when,code\n00123,7.11.2026,010\n000,1.1.2024,00\n"
LABS_CSV = "lab_id\nL1\n"
VISITS_SHA256 = "2a83f33a95c1b48e2a33dcb78d7698d1cc4adbf43f8ca2426b5b49f129e66842"
LABS_SHA256 = "de4ded3552e7ee8fbe4b626adf1eceea23ae55c68bbd10276056f4b519219b88"

DICTIONARY = """# Data dictionary

## health

### health / ed_visits

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `id` | record_key | RECORD_ID |  | Visit identifier |
| `when` | quasi_identifier | DATE |  | Date of visit |
| `code` | technical_identifier | RECORD_ID |  | Code |

### health / lab_results

| column | role | subtype | Art. 9 | description |
|---|---|---|---|---|
| `lab_id` | record_key | RECORD_ID | yes | Lab result identifier |
"""


def write_minikit(root: Path, scenarios=None, tables=None, dictionary: str | None = DICTIONARY) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "metadata").mkdir(exist_ok=True)
    (root / "data" / "health").mkdir(parents=True, exist_ok=True)
    (root / "docs").mkdir(exist_ok=True)
    if scenarios is None:
        scenarios = [
            {
                "id": "HEALTH-S1",
                "dataset": "health",
                "title": "synthetic",
                "utility_requirements": ["H-U2"],
            }
        ]
    (root / "metadata" / "scenarios.json").write_text(
        json.dumps(scenarios), encoding="utf-8"
    )
    if tables is None:
        tables = {"ed_visits": VISITS_CSV, "lab_results": LABS_CSV}
    for name, text in tables.items():
        (root / "data" / "health" / f"{name}.csv").write_bytes(text.encode("utf-8"))
    if dictionary is not None:
        (root / "docs" / "DATA_DICTIONARY.md").write_bytes(dictionary.encode("utf-8"))
    return root


def cli_env(extra: dict | None = None) -> dict[str, str]:
    """Minimal env. Does not inherit PETS_KIT, PETS_HMAC_KEY or SOURCE_DATE_EPOCH."""
    keep = (
        "PATH",
        "SYSTEMROOT",
        "PATHEXT",
        "WINDIR",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "HOMEDRIVE",
        "HOMEPATH",
        "COMSPEC",
        "VIRTUAL_ENV",
    )
    env = {key: os.environ[key] for key in keep if key in os.environ}
    env["PYTHONUTF8"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["TZ"] = "UTC"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = str(SRC)
    if extra:
        env.update(extra)
    return env


def run_cli(*args: str, env: dict | None = None, module: str = "pets_release") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [PYTHON, "-m", module, *args],
        cwd=ROOT,
        env=cli_env(env),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


PINNED_KIT = Path(r"C:\Users\kivas\AI\sinceai-hackaton\Briefs\TRUSTED_PETS_PROVING_GROUND_2026 (1)"
                  r"\TRUSTED_PETS_PROVING_GROUND_2026")


def find_kit() -> Path | None:
    """The kit root: PETS_KIT if set, else the pinned path. None when it is not a kit (no results/benchmark.json)."""
    kit = Path(os.environ.get("PETS_KIT") or PINNED_KIT)
    return kit if (kit / "results" / "benchmark.json").is_file() else None


@pytest.fixture
def kit_root(request) -> Path:
    """The kit root for tests marked ``kit``. A missing kit FAILS (never skips: skipped = not run = unknown = fail).
    Kit-less runs deselect them explicitly with ``-m "not kit"``."""
    kit = find_kit()
    if kit is None:
        pytest.fail("kit required but not found: set PETS_KIT or place the kit at the pinned path "
                    '(run with -m "not kit" to exclude kit tests explicitly)', pytrace=False)
    return kit


@pytest.fixture(autouse=True)
def _kit_marked_tests_need_the_kit(request):
    if request.node.get_closest_marker("kit") is not None:
        request.getfixturevalue("kit_root")


@pytest.fixture
def make_kit(tmp_path: Path):
    def _make(**kwargs) -> Path:
        return write_minikit(tmp_path / "kit", **kwargs)

    return _make


@pytest.fixture
def cli():
    return run_cli


# Test tiers: collection only, never skip or change the default full-suite run.
SLOW_TESTS_PATH = Path(__file__).resolve().with_name("slow_tests.txt")
FAST_CLI_SMOKE = frozenset({
    "tests/run/test_run.py::test_planted_card_number_refuses_via_cli",
    "tests/run/test_run.py::test_release_passes_gate_and_both_verify_tiers",
    "tests/run/test_run.py::test_two_runs_byte_identical",
})
# These modules exercise the release/gate/verification boundary on hand-made
# synthetic fixtures. Keep the whole module fast, including shared fixture setup,
# rather than letting noisy timings remove individual fail-closed cases.
FAST_SYNTHETIC_CLI_MODULES = frozenset({
    "tests/checks/test_runner.py",
    "tests/checks/test_review_r3.py",
    "tests/manifest/test_cli.py",
})


def keep_synthetic_cli_fast(item) -> bool:
    module = item.nodeid.split("::", 1)[0]
    return not requires_real_kit(item) and (
        module.startswith(("tests/run/", "tests/verify/"))
        or module in FAST_SYNTHETIC_CLI_MODULES
        or item.nodeid in FAST_CLI_SMOKE
    )


def requires_real_kit(item) -> bool:
    """Fixture names include the transitive closure; synthetic `kit` is not real.

    `kit` is the repo's real-kit marker, including inherited module/class marks.
    New real-kit fixtures must depend on kit_root (or tests must carry that mark).
    """
    return item.get_closest_marker("kit") is not None or "kit_root" in item.fixturenames


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items):
    """Add marks before pytest's own -m deselection, using the canonical list."""
    try:
        measured = {
            line.strip() for line in SLOW_TESTS_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
    except OSError as exc:
        raise pytest.UsageError("cannot read canonical tests/slow_tests.txt") from exc
    for item in items:
        if requires_real_kit(item):
            item.add_marker(pytest.mark.slow(reason="real-kit"))
        elif item.nodeid in measured and not keep_synthetic_cli_fast(item):
            item.add_marker(pytest.mark.slow(reason="profile"))
