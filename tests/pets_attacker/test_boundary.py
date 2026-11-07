"""Truth-boundary and import-graph guards.

Seams: (a) static raw-text scan of every file under src/ outside pets_attacker/;
(b) runtime import of every pets_release module in a subprocess.
Misses: truth paths or import names computed at runtime are only caught by (b),
and only on code paths exercised at import time.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pets_attacker.boundary import (
    BoundaryError,
    attacker_importers,
    attacker_reads_truth,
    launcher_shape_violates,
    runtime_violations,
    truth_references,
)

SRC = Path(__file__).resolve().parents[2] / "src"


def _plant(root: Path, rel: str, text: str | bytes) -> None:
    p = root / "src" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        p.write_bytes(text)
    else:
        p.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------- static guard
def test_real_tree_is_clean_and_attacker_reads_truth():
    assert attacker_reads_truth(SRC)
    assert truth_references(SRC) == []
    assert attacker_importers(SRC) == []


@pytest.mark.parametrize("text", [
    "import pets_attacker\n",
    "from pets_attacker.personas import broker_attack\n",
    'import importlib\nimportlib.import_module("pets_attacker")\n',
    'MOD = "pets_attacker"\n',
    "# pets_attacker\n",
    '"""mentions pets_attacker"""\n',
])
def test_any_mention_of_the_attacker_is_a_violation(tmp_path: Path, text):
    _plant(tmp_path, "pets_release/x.py", text)
    assert any(h.endswith("x.py") for h in attacker_importers(tmp_path / "src"))


@pytest.mark.parametrize("text", [
    'PATH = "truth/health__ed_visits.csv"\n',
    'p = root / "truth" / "x.csv"\n',
    'p = "kit\\\\truth\\\\x.csv"\n',
    "p = 'truth/x'\n",
])
def test_truth_path_segments_are_violations(tmp_path: Path, text):
    _plant(tmp_path, "pets_release/x.py", text)
    assert any(h.endswith("x.py") for h in truth_references(tmp_path / "src"))


def test_word_truth_in_prose_is_not_a_reference(tmp_path: Path):
    _plant(tmp_path, "pets_release/doc.py", '"""ground truth is not used here."""\nX = "the truth"\n')
    assert truth_references(tmp_path / "src") == []


def test_inside_attacker_is_allowed(tmp_path: Path):
    _plant(tmp_path, "pets_attacker/truth.py", 'from pets_attacker import b\nP = "truth/x.csv"\n')
    assert truth_references(tmp_path / "src") == []
    assert attacker_importers(tmp_path / "src") == []
    assert attacker_reads_truth(tmp_path / "src")


def test_non_python_and_odd_files_are_scanned_too_as_py_only_but_bom_and_unreadable_fail(tmp_path: Path):
    _plant(tmp_path, "pets_release/bom.py", b'\xef\xbb\xbfimport pets_attacker\nP = "truth/x.csv"\n')
    _plant(tmp_path, "pets_release/bad.py", b"\xff\xfe\x00\x80 not utf8")
    _plant(tmp_path, "pets_release/broken.py", "def (:\n")  # unparseable but readable and clean: fine for static text scan
    for fn in (attacker_importers, truth_references):
        hits = fn(tmp_path / "src")
        assert any(h.endswith("bom.py") for h in hits)
        assert any(h.endswith("bad.py") for h in hits)  # unreadable = violation


@pytest.mark.parametrize("fn", [attacker_importers, truth_references, attacker_reads_truth])
def test_missing_or_empty_scan_root_is_an_error(tmp_path: Path, fn):
    with pytest.raises(BoundaryError):
        fn(tmp_path / "nope")
    (tmp_path / "empty").mkdir()
    with pytest.raises(BoundaryError):
        fn(tmp_path / "empty")


# --------------------------------------------------------------- runtime guard
def _tree(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        _plant(tmp_path, rel, text)
    _plant(tmp_path, "pets_release/__init__.py", "")
    _plant(tmp_path, "pets_attacker/__init__.py", "")  # stub so a planted import can succeed
    return tmp_path / "src"


def _truth(tmp_path: Path) -> Path:
    d = tmp_path / "kit" / "truth"
    d.mkdir(parents=True)
    (d / "health__ed_visits.csv").write_text("record_id,person_id\n", encoding="utf-8")
    return d


def test_runtime_clean_tree_passes(tmp_path: Path):
    src = _tree(tmp_path, {"pets_release/a.py": "X = 1\n", "pets_release/sub/__init__.py": "", "pets_release/sub/b.py": "Y = 2\n"})
    assert runtime_violations(src, _truth(tmp_path)) == []


def test_runtime_catches_computed_attacker_import(tmp_path: Path):
    src = _tree(tmp_path, {"pets_release/sneak.py": 'import importlib\nimportlib.import_module("pets_" + "attacker")\n'})
    v = runtime_violations(src, _truth(tmp_path))
    assert any("attacker" in x for x in v)


def test_runtime_catches_truth_file_opened_at_import(tmp_path: Path):
    truth = _truth(tmp_path)
    p = str(truth / "health__ed_visits.csv").replace("\\", "/")
    src = _tree(tmp_path, {"pets_release/peek.py": f'open("{p}", encoding="utf-8").read()\n'})
    v = runtime_violations(src, truth)
    assert any("truth" in x for x in v)


def test_runtime_import_error_is_a_violation(tmp_path: Path):
    src = _tree(tmp_path, {"pets_release/boom.py": "raise RuntimeError('x')\n"})
    assert any("import-error" in x for x in runtime_violations(src, _truth(tmp_path)))


def test_runtime_missing_package_is_an_error(tmp_path: Path):
    _plant(tmp_path, "other/__init__.py", "")
    with pytest.raises(BoundaryError):
        runtime_violations(tmp_path / "src", _truth(tmp_path))


def test_runtime_does_not_leak_parent_modules(tmp_path: Path):
    """The subprocess starts clean: the already-loaded attacker in this process is irrelevant."""
    assert "pets_attacker" in sys.modules
    src = _tree(tmp_path, {"pets_release/a.py": "X = 1\n"})
    assert runtime_violations(src, _truth(tmp_path)) == []


def test_runtime_guard_on_the_real_tree(tmp_path: Path):
    """Until pets_release lands in this tree the guard must refuse, not pass; afterwards it must be clean."""
    truth = tmp_path / "truth"
    truth.mkdir()
    if (SRC / "pets_release" / "__init__.py").is_file():
        assert runtime_violations(SRC, truth) == []
    else:
        with pytest.raises(BoundaryError):
            runtime_violations(SRC, truth)


def test_main_entry_modules_are_not_executed_by_the_runtime_walk(tmp_path: Path):
    src = _tree(tmp_path, {"pets_release/__main__.py": "raise SystemExit(3)\n", "pets_release/a.py": "X = 1\n"})
    assert runtime_violations(src, _truth(tmp_path)) == []


# --- follow-up #77: the audit hook fails closed --------------------------------------------------------
# Rule: any error inside the hook, and any `open` target that is neither a path nor an int fd, is a violation,
# blocks that open, and makes the child exit non-zero. Rows: hook error -> open refused -> import error ->
# hook-error recorded -> child exit != 0 -> runtime-check-failed.
_SABOTAGE = (
    "import os, os.path\n"
    "def _boom(*a, **k):\n"
    "    raise RuntimeError('sabotaged')\n"
    "os.path.realpath = _boom\n"
    "open({p!r}, encoding='utf-8').read()\n"
)


def test_runtime_hook_error_fails_closed_and_blocks_the_open(tmp_path: Path):
    truth = _truth(tmp_path)
    p = str(truth / "health__ed_visits.csv")
    src = _tree(tmp_path, {"pets_release/peek.py": _SABOTAGE.format(p=p)})
    v = runtime_violations(src, truth)
    assert "hook-error" in v
    assert "import-error:pets_release.peek" in v  # the open was refused, so the import failed
    assert "runtime-check-failed" in v  # the child exited non-zero


def test_runtime_truth_opened_via_os_open_then_fd_is_caught(tmp_path: Path):
    """The fd route: os.open is audited with its path, so wrapping the fd later cannot hide a truth read."""
    truth = _truth(tmp_path)
    p = str(truth / "health__ed_visits.csv")
    code = f"import os\nfd = os.open({p!r}, os.O_RDONLY)\nopen(fd, encoding='utf-8').read()\n"
    src = _tree(tmp_path, {"pets_release/fd.py": code})
    assert "truth-opened" in runtime_violations(src, truth)


def test_runtime_int_fd_of_a_non_truth_file_is_allowed(tmp_path: Path):
    """Int fds wrap pipes (subprocess at import time) or already-audited opens; they are not violations."""
    other = tmp_path / "other.txt"
    other.write_text("x\n", encoding="utf-8")
    code = f"import os\nfd = os.open({str(other)!r}, os.O_RDONLY)\nopen(fd, encoding='utf-8').close()\n"
    src = _tree(tmp_path, {"pets_release/fd.py": code})
    assert runtime_violations(src, _truth(tmp_path)) == []


def test_runtime_unknown_open_target_type_is_a_hook_error(tmp_path: Path):
    """An open event whose target is neither a path nor an int fd cannot be resolved: refused."""
    code = "import sys\nsys.audit('open', 1.5, 'r', 0)\n"
    src = _tree(tmp_path, {"pets_release/odd.py": code})
    v = runtime_violations(src, _truth(tmp_path))
    assert "hook-error" in v and "runtime-check-failed" in v


# --- #138: the measured run's attacker launcher ----------------------------------------------------------
# Rule (round 3, identity): the attacker-name exemption applies only to pets_release/measure/attackers.py whose
# canonical content (UTF-8, LF line endings) has the SHA-256 pinned in boundary.py. Any other content at that
# path, or the same content at any other path, gets the any-mention rule. Changing the launcher needs a visible,
# reviewed digest update in boundary.py.
# Defence in depth (round 2): the launcher must also have the approved shape (launcher_shape_violates): the two
# module-name constants only as the -m module of subprocess.run([sys.executable, "-m", NAME, ...]); subprocess
# and sys used only as subprocess.run / subprocess.TimeoutExpired / sys.executable; nothing rebound.
# Rows: real launcher unchanged (LF or CRLF) -> clean; one byte changed -> flagged; real launcher + each planted
# route -> flagged; real launcher at any other path -> flagged; shape check flags every planted route on CLEAN.
LAUNCHER = "pets_release/measure/attackers.py"
REAL = (SRC / LAUNCHER).read_bytes().replace(b"\r\n", b"\n")
CONSTANTS = 'ATTACKER_MODULE = "pets_attacker"\nBRIDGE_MODULE = "pets_attacker.bridge"\n'
CLEAN = ("import subprocess\nimport sys\n\n" + CONSTANTS + "\n\n"
         "def attack(argv):\n"
         "    return subprocess.run([sys.executable, \"-m\", ATTACKER_MODULE, *argv], check=False, timeout=5)\n\n\n"
         "def bridge(argv):\n"
         "    return subprocess.run([sys.executable, \"-m\", BRIDGE_MODULE, *argv], check=False)\n")
ROUTES = [
    "import pets_attacker\n",
    "from pets_attacker import cli\n",
    "from pets_attacker.bridge import main\n",
    "# pets_attacker\n",
    'OTHER = "pets_attacker.truth"\n',
    "import importlib\nimportlib.import_module(ATTACKER_MODULE)\n",
    "__import__(BRIDGE_MODULE)\n",
    "import runpy\nrunpy.run_module(ATTACKER_MODULE)\n",
    "import pkgutil\n",
    "exec('import ' + ATTACKER_MODULE)\n",
    "eval(compile('1', 'x', 'eval'))\n",
    "from importlib import import_module\n",
    "def (:\n",
    # round 2 (Sol Standards, high)
    'import builtins\ndef load():\n    return getattr(builtins, "__import__")(ATTACKER_MODULE)\n',
    'def load():\n    m = ATTACKER_MODULE\n    return getattr(__builtins__, "__imp" + "ort__")(m)\n',
    "def load():\n    m = ATTACKER_MODULE\n    import importlib as il\n    return il.import_module(m)\n",
    'X = ATTACKER_MODULE + ".cli"\n',
    'X = f"{ATTACKER_MODULE}.cli"\n',
    'X = "{}.cli".format(BRIDGE_MODULE)\n',
    'X = "%s.cli" % BRIDGE_MODULE\n',
    "X = [ATTACKER_MODULE]\n",
    'subprocess.run([sys.executable, "-c", ATTACKER_MODULE])\n',
    'subprocess.run(["python", "-m", ATTACKER_MODULE])\n',
    'subprocess.run([sys.executable, "-m", ATTACKER_MODULE], executable="sh")\n',
    'subprocess.run([sys.executable, "-m", ATTACKER_MODULE], shell=True)\n',
    'subprocess.Popen([sys.executable, "-m", ATTACKER_MODULE])\n',
    'ATTACKER_MODULE = "os"\n',
    "import builtins as subprocess\n",
    "def f():\n    global sys\n    sys = None\n",
    'sys.executable = "x"\n',
    "subprocess.run = print\n",
    "def f(sys):\n    return sys\n",
    "def subprocess():\n    return None\n",
    "try:\n    pass\nexcept Exception as ATTACKER_MODULE:\n    pass\n",
    # round 2 (Grok Standards, high)
    'def load():\n    return getattr(__builtins__, "__imp" + "ort__")(ATTACKER_MODULE)\n',
    'import os\ndef load(n):\n    return getattr(os, "sys" + "tem")(n)\n',
    'def load():\n    return globals()["ATTACKER_" + "MODULE"]\n',
    'def load():\n    return vars()["BRIDGE_MODULE"]\n',
    # round 3 (Grok Standards r2, high): routes that passed the shape check at 79c4055
    'def load():\n    return sys.modules["import" + "lib"].__dict__["import" + "_module"]("pets_" + "attacker")\n',
    'def load():\n    return sys._getframe(0).f_builtins["__imp" + "ort__"]("pets_" + "attacker")\n',
    'def patch(fn):\n    setattr(subprocess, "run", fn)\n',
    "def patch(fn):\n    type(subprocess).run = fn\n",
]
ROUTE_IDS = ["import", "from", "from_sub", "comment", "other_string", "importlib", "dunder_import", "runpy",
             "pkgutil", "exec", "eval_compile", "from_importlib", "unparseable", "getattr_builtins",
             "alias_getattr_computed", "alias_importlib", "concat", "fstring", "format", "percent", "other_list",
             "dash_c", "other_executable", "executable_kw", "shell_kw", "popen", "rebind_constant",
             "rebind_subprocess", "rebind_sys", "store_sys_attr", "store_subprocess_attr", "shadow_param",
             "shadow_def", "shadow_except", "grok_computed_dunder", "computed_getattr", "globals_lookup",
             "vars_lookup", "sys_modules_importlib", "getframe_builtins", "setattr_subprocess_run",
             "type_store_subprocess_run"]


def _flagged(tmp_path: Path, rel: str = LAUNCHER) -> bool:
    return any(Path(h).relative_to(tmp_path / "src").as_posix() == rel for h in attacker_importers(tmp_path / "src"))


@pytest.mark.parametrize("eol", [b"\n", b"\r\n"], ids=["lf", "crlf"])
def test_real_launcher_unchanged_is_clean(tmp_path: Path, eol):
    _plant(tmp_path, LAUNCHER, REAL.replace(b"\n", eol))
    assert attacker_importers(tmp_path / "src") == []


@pytest.mark.parametrize("edit", [
    lambda b: b.replace(b"Attacker rates", b"attacker rates", 1),  # one byte, in the docstring
    lambda b: b + b"\n",
    lambda b: b.replace(b"TIMEOUT_S = 3600", b"TIMEOUT_S = 3601", 1),
], ids=["docstring_byte", "trailing_newline", "constant_byte"])
def test_real_launcher_with_one_byte_changed_is_flagged(tmp_path: Path, edit):
    changed = edit(REAL)
    assert changed != REAL
    _plant(tmp_path, LAUNCHER, changed)
    assert _flagged(tmp_path)


@pytest.mark.parametrize("extra", ROUTES, ids=ROUTE_IDS)
def test_real_launcher_with_any_planted_route_is_flagged(tmp_path: Path, extra):
    _plant(tmp_path, LAUNCHER, REAL + b"\n" + extra.encode("utf-8"))
    assert _flagged(tmp_path)


def test_shape_check_accepts_the_approved_form_and_the_real_launcher():
    assert not launcher_shape_violates(CLEAN)
    assert not launcher_shape_violates(REAL.decode("utf-8"))


@pytest.mark.parametrize("extra", ROUTES, ids=ROUTE_IDS)
def test_shape_check_flags_every_planted_route(extra):
    """Defence in depth: without the digest pin, the shape check alone still flags each route."""
    assert launcher_shape_violates(CLEAN + extra)


@pytest.mark.parametrize("text", [
    CLEAN.replace('"pets_attacker"', '"pets_attacker.cli"'),
    CLEAN.replace("ATTACKER_MODULE = ", "ATTACKER_MODULE: str = "),
    "if True:\n    " + CLEAN.replace("\n", "\n    "),
], ids=["other_constant_value", "annotated_assignment", "nested_assignment"])
def test_shape_check_flags_constants_outside_the_two_exact_top_level_assignments(text):
    assert launcher_shape_violates(text)


@pytest.mark.parametrize("rel", ["pets_release/attackers.py", "pets_release/ui/attackers.py",
                                 "pets_release/measure/sub/attackers.py", "pets_release/measure/other.py"])
def test_the_real_launcher_in_any_other_file_is_a_violation(tmp_path: Path, rel):
    _plant(tmp_path, LAUNCHER, REAL)
    _plant(tmp_path, rel, REAL)
    assert [Path(h).relative_to(tmp_path / "src").as_posix() for h in attacker_importers(tmp_path / "src")] == [rel]


def test_launcher_unreadable_is_a_violation(tmp_path: Path):
    _plant(tmp_path, LAUNCHER, b"\xff\xfe\x00\x80 not utf8")
    assert _flagged(tmp_path)


def test_kit_module_is_exempt_from_the_truth_scan_only(tmp_path: Path):
    """pets_release/kit.py names `truth` to forbid it; the exemption is that one file, truth text only."""
    lit = 'FORBIDDEN = frozenset({"truth"})\n'
    _plant(tmp_path, "pets_release/kit.py", lit)
    _plant(tmp_path, "pets_release/other.py", lit)
    hits = truth_references(tmp_path / "src")
    assert not any(h.endswith("kit.py") for h in hits)
    assert any(h.endswith("other.py") for h in hits)
    _plant(tmp_path, "pets_release/kit.py", "import pets_attacker\n")
    assert any(h.endswith("kit.py") for h in attacker_importers(tmp_path / "src"))
