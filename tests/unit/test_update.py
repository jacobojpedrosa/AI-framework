import json
import subprocess
import sys
from argparse import Namespace

import pytest

from harness.config.loader import load_project
from harness.doctor import digest
from harness.errors import HarnessError
from harness.scaffolding.fullstack import scaffold
from harness.update import MANIFEST, dispatch, make_plan


@pytest.fixture
def project(tmp_path, repo_root):
    root = tmp_path / "source"
    scaffold(
        load_project(repo_root / "examples/specifications/fullstack-ai/expected-project.yaml"), root
    )
    manifest = json.loads((root / MANIFEST).read_text())
    manifest["harness_version"] = "0.14.0"
    path = "services/api/requirements.in"
    original = (root / path).read_bytes().replace(b"0.141.1", b"0.140.0")
    (root / path).write_bytes(original)
    manifest["files"][path] = digest(original)
    (root / MANIFEST).write_text(json.dumps(manifest))
    for args in (
        ["init"],
        ["add", "."],
        [
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "fixture",
        ],
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    return root


def arguments(project, **kwargs):
    return Namespace(
        project=project,
        target_version=None,
        checks=None,
        apply=False,
        approve=None,
        worktree=None,
        **kwargs,
    )


def test_preview_detects_pinned_dependency_update_without_writes(project, capsys):
    before = (project / MANIFEST).read_bytes()
    assert dispatch(arguments(project)) == 0
    plan = json.loads(capsys.readouterr().out)
    assert any(c["path"] == "services/api/requirements.in" for c in plan["changes"])
    assert plan["conflicts"] == []
    assert (project / MANIFEST).read_bytes() == before


def test_modified_dependency_is_conflict(project):
    (project / "services/api/requirements.in").write_text("user dependency\n")
    plan, _ = make_plan(project)
    assert "services/api/requirements.in" in plan["conflicts"]


@pytest.mark.parametrize("mutation", ["newer", "prototype", "traversal", "configuration"])
def test_reject_incompatible(project, mutation):
    manifest = json.loads((project / MANIFEST).read_text())
    if mutation == "newer":
        manifest["harness_version"] = "999.0.0"
    elif mutation == "prototype":
        manifest["template"] = "collection-prototype"
    elif mutation == "traversal":
        manifest["files"]["../escape"] = "a" * 64
    else:
        (project / "project.yaml").write_text("schema_version: 99\n")
    (project / MANIFEST).write_text(json.dumps(manifest))
    with pytest.raises(HarnessError):
        make_plan(project)


def test_requires_clean_source_and_exact_approval(project):
    (project / "untracked.txt").write_text("keep")
    with pytest.raises(HarnessError, match="clean"):
        dispatch(arguments(project))
    (project / "untracked.txt").unlink()
    args = arguments(project)
    args.apply = True
    args.approve = "stale"
    with pytest.raises(HarnessError, match="exact preview"):
        dispatch(args)


@pytest.mark.parametrize("fails", [False, True])
def test_isolated_branch_all_gates_and_failed_gate(project, tmp_path, capsys, fails):
    checks = tmp_path / "checks.json"
    checks.write_text(
        json.dumps(
            {
                name: {
                    "cwd": ".",
                    "argv": [
                        sys.executable,
                        "-c",
                        "raise SystemExit(1)" if fails and name == "contracts" else "pass",
                    ],
                }
                for name in ("dependencies", "tests", "contracts", "e2e")
            }
        )
    )
    args = arguments(project)
    args.checks = checks
    assert dispatch(args) == 0
    approval = json.loads(capsys.readouterr().out)["approval"]
    before = (project / MANIFEST).read_bytes()
    args.apply, args.approve, args.worktree = True, approval, tmp_path / "candidate"
    assert dispatch(args) == int(fails)
    report = json.loads((args.worktree / ".harness/update-report.json").read_text())
    assert report["status"] == ("failed" if fails else "ready-for-human-review")
    assert report["branch"].startswith("harness-update-")
    assert (project / MANIFEST).read_bytes() == before
    if fails:
        assert "e2e" not in report["checks"]
    else:
        assert set(report["checks"]) == {"dependencies", "tests", "contracts", "e2e", "doctor"}


def test_symlink_managed_file_rejected(project, tmp_path):
    path = project / "services/api/requirements.in"
    path.unlink()
    path.symlink_to(tmp_path / "outside")
    with pytest.raises(HarnessError):
        make_plan(project)


def test_unrelated_user_edit_preserved(project):
    path = project / "README.md"
    path.write_text("User documentation\n")
    plan, _ = make_plan(project)
    assert "README.md" not in plan["conflicts"]
    assert not any(change["path"] == "README.md" for change in plan["changes"])


def test_validation_cannot_silently_rewrite_candidate(project, tmp_path, capsys):
    checks = tmp_path / "checks.json"
    checks.write_text(
        json.dumps(
            {
                name: {
                    "cwd": ".",
                    "argv": [
                        sys.executable,
                        "-c",
                        "from pathlib import Path; Path('README.md').write_text('changed')"
                        if name == "tests"
                        else "pass",
                    ],
                }
                for name in ("dependencies", "tests", "contracts", "e2e")
            }
        )
    )
    args = arguments(project)
    args.checks = checks
    dispatch(args)
    args.approve = json.loads(capsys.readouterr().out)["approval"]
    args.apply, args.worktree = True, tmp_path / "candidate"
    assert dispatch(args) == 1
    report = json.loads((args.worktree / ".harness/update-report.json").read_text())
    assert report["managed_files_unchanged_by_checks"] is False
