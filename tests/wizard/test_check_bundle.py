"""Bundle-check CLI seam: names/counts only; all layouts are synthetic tmp files.

Rules / failure rows (D37): complete -> 0; absent required items -> 3 with
every missing name; broken table/map or manifest pairing, unexpected entries,
symlinks, forbidden paths, public-repo overlap, or no required items -> 1.
An orphan row map must not satisfy the protected-table requirement.
The CLI must never prompt, write .env, or invoke git/gh/browser/network tools.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "wizard" / "saturday-submission.sh"
BASH = Path(r"C:\Program Files\Git\bin\bash.exe")
ROOT_FILES = (
    "unseen_field_labels.csv",
    "customer_service_eval_redacted.csv",
    "customer_service_eval_spans.jsonl",
)


def bash_command(script, *args):
    # Git's Windows launcher prepends its own bin dirs. Prepend boundary fakes
    # inside Bash, after that launcher, so no real git/gh can win PATH lookup.
    return [
        str(BASH), "-c",
        'export PATH="$(cygpath -u "$BUNDLE_TEST_BIN"):$PATH"; exec /usr/bin/bash "$@"',
        "bundle-test", str(script), *args,
    ]


@pytest.fixture
def bundle(tmp_path):
    root = tmp_path / "synthetic bundle"
    root.mkdir()
    for name in ROOT_FILES:
        (root / name).write_text("synthetic\n", encoding="utf-8")
    for name in ("health", "customer_service"):
        dataset = root / name
        dataset.mkdir()
        (dataset / "table.csv").write_text("id\n001\n", encoding="utf-8")
        (dataset / "rowmap_table.csv").write_text("id\n001\n", encoding="utf-8")
        (dataset / "privacy_manifest.json").write_text("{}\n", encoding="utf-8")
    return root


@pytest.fixture
def check_bundle(tmp_path):
    if not BASH.is_file():
        pytest.fail(f"Required Windows Git Bash is missing: {BASH}")
    # Guard external boundaries even on the pre-fix red run: never execute
    # the interactive wizard's real git/gh/browser commands accidentally.
    guards = tmp_path / "guard-bin"
    guards.mkdir()
    calls = tmp_path / "unexpected-external-call"
    for name in ("git", "gh", "clip.exe", "explorer.exe", "curl", "wget"):
        (guards / name).write_text(
            '#!/usr/bin/env bash\nprintf "%s\\n" "$0" >> "$BUNDLE_TEST_CALLS"\nexit 86\n',
            encoding="utf-8",
        )
    env = os.environ.copy()
    env["PATH"] = str(guards) + os.pathsep + env["PATH"]
    env["BUNDLE_TEST_CALLS"] = str(calls)
    env["BUNDLE_TEST_BIN"] = str(guards)
    env["ENV_FILE"] = str(tmp_path / ".env")

    def run(path, *, script=SCRIPT, args=None):
        result = subprocess.run(
            bash_command(script, *(args if args is not None else ["--check-bundle", str(path)])),
            input="",
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
            check=False,
        )
        assert not calls.exists(), "--check-bundle entered interactive git/gh/tool flow"
        assert not (tmp_path / ".env").exists(), "check-only mode wrote .env"
        assert "Stage " not in result.stdout, result.stdout
        return result

    return run


def test_complete_bundle(check_bundle, bundle):
    result = check_bundle(bundle)
    assert result.returncode == 0, result.stdout + result.stderr


def test_missing_dataset_is_partial_and_named(check_bundle, bundle):
    shutil.rmtree(bundle / "customer_service")
    result = check_bundle(bundle)
    assert result.returncode == 3, result.stdout + result.stderr
    assert "customer_service/" in result.stdout


@pytest.mark.parametrize("name", ROOT_FILES)
def test_missing_required_root_file_is_partial_and_named(check_bundle, bundle, name):
    (bundle / name).unlink()
    result = check_bundle(bundle)
    assert result.returncode == 3, result.stdout + result.stderr
    assert name in result.stdout


def test_lists_every_missing_required_item(check_bundle, bundle):
    for name in ROOT_FILES:
        (bundle / name).unlink()
    shutil.rmtree(bundle / "customer_service")
    result = check_bundle(bundle)
    assert result.returncode == 3, result.stdout + result.stderr
    for name in (*ROOT_FILES, "customer_service/"):
        assert name in result.stdout


def test_table_without_row_map_is_invalid(check_bundle, bundle):
    (bundle / "health" / "rowmap_table.csv").unlink()
    assert check_bundle(bundle).returncode == 1


def test_dataset_without_manifest_is_invalid(check_bundle, bundle):
    (bundle / "health" / "privacy_manifest.json").unlink()
    assert check_bundle(bundle).returncode == 1


@pytest.mark.parametrize("name", ("extra.txt", ".hidden", "other_dataset"))
def test_unexpected_top_level_entry_is_invalid(check_bundle, bundle, name):
    (bundle / name).write_text("synthetic\n", encoding="utf-8")
    assert check_bundle(bundle).returncode == 1


def test_empty_directory_is_invalid(check_bundle, tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    assert check_bundle(root).returncode == 1


def test_orphan_row_map_does_not_count_as_protected_table(check_bundle, bundle):
    (bundle / "customer_service" / "table.csv").unlink()
    (bundle / "customer_service" / "rowmap_x.csv").write_text("id\n001\n", encoding="utf-8")
    result = check_bundle(bundle)
    assert result.returncode == 3, result.stdout + result.stderr
    assert "customer_service/*.csv" in result.stdout


def test_only_optional_items_is_invalid(check_bundle, tmp_path):
    root = tmp_path / "optional-only"
    root.mkdir()
    (root / ".git").mkdir()
    (root / "submission_index.json").write_text("{}\n", encoding="utf-8")
    assert check_bundle(root).returncode == 1


def test_optional_git_directory_and_index_are_allowed(check_bundle, bundle):
    (bundle / ".git").mkdir()
    (bundle / "submission_index.json").write_text("{}\n", encoding="utf-8")
    assert check_bundle(bundle).returncode == 0


@pytest.mark.parametrize("name", (".env", ".env.local", "secret.key", "truth", "Briefs"))
def test_forbidden_nested_path_is_invalid(check_bundle, bundle, name):
    (bundle / "health" / name).write_text("synthetic\n", encoding="utf-8")
    assert check_bundle(bundle).returncode == 1


@pytest.mark.parametrize("location", ("table", "root", "git"))
def test_symlink_is_invalid(check_bundle, bundle, tmp_path, location):
    link = {
        "table": bundle / "health" / "linked.txt",
        "root": tmp_path / "linked-bundle",
        "git": bundle / ".git",
    }[location]
    target = bundle if location == "root" else bundle / "health" / "table.csv"
    if location == "git":
        target = tmp_path / "external-git"
        target.mkdir()
    try:
        link.symlink_to(target, target_is_directory=location in ("root", "git"))
    except OSError as error:
        if error.winerror not in (5, 1314):
            raise
        pytest.skip(f"Windows symlink creation unavailable without admin/developer mode: {error.winerror}")
    assert check_bundle(link if location == "root" else bundle).returncode == 1


@pytest.mark.parametrize("relationship", ("inside", "contains"))
def test_public_repo_overlap_is_invalid(check_bundle, bundle, tmp_path, relationship):
    public = (tmp_path if relationship == "inside" else bundle / "health") / "synthetic-public-repo"
    script = public / "scripts" / "wizard" / SCRIPT.name
    script.parent.mkdir(parents=True)
    shutil.copyfile(SCRIPT, script)
    path = public / "bundle" if relationship == "inside" else bundle
    if relationship == "inside":
        shutil.copytree(bundle, path)
    result = check_bundle(path, script=script)
    assert result.returncode == 1
    assert "public repository" in result.stdout


@pytest.mark.parametrize("args", (["--check-bundle"], ["--check-bundle", "x", "extra"]))
def test_bad_check_mode_arguments_are_invalid(check_bundle, tmp_path, args):
    assert check_bundle(tmp_path, args=args).returncode == 1


@pytest.mark.parametrize("reply", ("PARTIAL", "partial", "yes", " PARTIAL", "PARTIAL ", ""))
def test_interactive_partial_requires_exact_acknowledgement(tmp_path, bundle, reply):
    """Interactive CLI seam; fake only git/gh/browser OS boundaries, never checks."""
    public = tmp_path / "synthetic-public-repo"
    script = public / "scripts" / "wizard" / SCRIPT.name
    script.parent.mkdir(parents=True)
    shutil.copyfile(SCRIPT, script)
    (public / ".gitignore").write_text(".env\n", encoding="utf-8")
    shutil.rmtree(bundle / "customer_service")
    tools = tmp_path / "interactive-bin"
    tools.mkdir()
    for name, body in {
        "git": '[[ "$*" == "check-ignore -q .env" ]] || exit 86\n',
        "gh": '[[ "$*" == "repo view Suhtetark-Kool/trusted-since-ai"* ]] || exit 86\nprintf "PRIVATE\\n"\n',
        "clip.exe": 'cat > "$BUNDLE_TEST_CLIPBOARD"\n',
        "explorer.exe": 'exit 0\n',
    }.items():
        (tools / name).write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    clipboard = tmp_path / "clipboard"
    env = os.environ.copy()
    env["PATH"] = str(tools) + os.pathsep + env["PATH"]
    env["BUNDLE_TEST_CLIPBOARD"] = str(clipboard)
    env["BUNDLE_TEST_BIN"] = str(tools)
    result = subprocess.run(
        bash_command(script),
        # Banner, Discord, handles, delivery, Defender, bundle, acknowledgement,
        # decline upload, final pause. No real remote or browser is ever used.
        # Raw LF bytes model terminal input; Windows text-mode pipes otherwise
        # turn acknowledgement lines into PARTIAL\r, which is not exact PARTIAL.
        input=("\n" * 5 + f"{bundle}\n{reply}\nn\n\n").encode("utf-8"),
        cwd=tmp_path,
        env=env,
        capture_output=True,
        timeout=15,
        check=False,
    )
    result.stdout = result.stdout.decode("utf-8")
    result.stderr = result.stderr.decode("utf-8")
    assert "customer_service/" in result.stdout
    if reply == "PARTIAL":
        assert result.returncode == 0, result.stdout + result.stderr
        message = clipboard.read_text(encoding="utf-8")
        assert "partial" in message.lower()
        assert "health" in message
        assert "customer_service" not in message
    else:
        assert result.returncode == 1, result.stdout + result.stderr
        assert "Push this bundle?" not in result.stdout
        assert not clipboard.exists()
