import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from harness.cli import initialize
from harness.config.loader import load_project
from harness.errors import HarnessError


def run_cli(*args, cwd):
    return subprocess.run(
        [sys.executable, "-m", "harness", *map(str, args)],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def test_help_and_usage(tmp_path):
    result = run_cli("--help", cwd=tmp_path)
    assert result.returncode == 0
    for command in (
        "init",
        "validate",
        "setup",
        "scaffold",
        "project-design",
        "prototype",
        "integrations",
        "jobs",
        "schedules",
        "doctor",
        "update",
        "readiness",
    ):
        assert command in result.stdout
    assert not list(tmp_path.iterdir())
    assert run_cli("init", cwd=tmp_path).returncode == 2
    assert run_cli("doctor", cwd=tmp_path).returncode == 1


def test_roundtrip_and_no_overwrite(tmp_path):
    result = run_cli("init", "demo", "--name", "demo", cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    path = tmp_path / "demo/project.yaml"
    assert load_project(path).project.name == "demo"
    before = path.read_bytes(), path.stat().st_mtime_ns
    result = run_cli("init", "demo", "--name", "different", cwd=tmp_path)
    assert result.returncode == 1
    assert "nothing was overwritten" in result.stderr
    result = run_cli("validate", path, cwd=tmp_path)
    assert result.returncode == 0
    assert "runtime health have not been checked" in result.stdout
    assert before == (path.read_bytes(), path.stat().st_mtime_ns)
    assert sorted(p.name for p in path.parent.iterdir()) == ["project.yaml"]


def test_default_paths(tmp_path):
    assert run_cli("init", "--name", "demo", cwd=tmp_path).returncode == 0
    assert run_cli("validate", cwd=tmp_path).returncode == 0


def test_invalid_input_has_no_traceback_or_write(tmp_path):
    result = run_cli("init", "demo", "--name", "../secret", cwd=tmp_path)
    assert result.returncode == 1
    assert "../secret" not in result.stderr
    assert "Traceback" not in result.stderr
    assert not (tmp_path / "demo").exists()
    result = run_cli("validate", cwd=tmp_path)
    assert result.returncode == 1
    assert "ERROR:" in result.stderr
    assert not result.stdout


@pytest.mark.parametrize("dangling", [False, True])
def test_init_rejects_file_symlink(tmp_path, dangling):
    target = tmp_path / "target.yaml"
    if not dangling:
        target.write_text("keep me")
    (tmp_path / "project.yaml").symlink_to(target)
    result = run_cli("init", "--name", "demo", cwd=tmp_path)
    assert result.returncode == 1
    if dangling:
        assert not target.exists()
    else:
        assert target.read_text() == "keep me"


def test_init_rejects_symlink_directory_and_parent_traversal(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "link").symlink_to(real, target_is_directory=True)
    for destination in ("link", "link/nested", "../elsewhere"):
        result = run_cli("init", destination, "--name", "demo", cwd=tmp_path)
        assert result.returncode == 1
    assert not list(real.iterdir())


def test_concurrent_init_only_one_writer(tmp_path):
    destination = tmp_path.resolve() / "demo"

    def attempt(name):
        try:
            initialize(destination, name)
            return name
        except HarnessError:
            return None

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(attempt, ["one", "two", "three", "four"]))
    winners = [name for name in results if name]
    assert len(winners) == 1
    assert load_project(destination / "project.yaml").project.name == winners[0]


def test_permission_error_is_sanitized(monkeypatch, tmp_path):
    def denied(*args, **kwargs):
        raise PermissionError("sensitive operating system detail")

    monkeypatch.setattr(os, "open", denied)
    with pytest.raises(HarnessError) as caught:
        initialize(tmp_path, "demo")
    assert "sensitive" not in str(caught.value)


def test_installed_entrypoint(tmp_path):
    executable = Path(sys.executable).parent / "harness"
    result = subprocess.run(
        [str(executable), "--help"], cwd=tmp_path, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0
