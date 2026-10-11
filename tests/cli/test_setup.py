import json
import subprocess
import sys
from argparse import Namespace

import pytest

from harness.config.loader import load_project
from harness.errors import HarnessError
from harness.resolution.setup import setup


def run(*args, cwd):
    return subprocess.run(
        [sys.executable, "-m", "harness", "setup", *map(str, args)],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def spec_file(tmp_path):
    path = tmp_path / "spec.yaml"
    path.write_text("name: demo\nweb: true\nservices: [api]\n")
    return path


def test_preview_is_read_only_and_stable(spec_file, tmp_path):
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    first = run(spec_file, "--json", cwd=tmp_path)
    second = run(spec_file, "--json", cwd=tmp_path)
    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout
    proposal = json.loads(first.stdout)
    assert proposal["golden_path"] == "fullstack-ai"
    assert proposal["status"] == "proposed"
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


def test_noninteractive_reports_only_missing_fields(tmp_path):
    path = tmp_path / "spec.yaml"
    path.write_text("name: demo\nweb: false\n")
    result = run(path, "--non-interactive", "--json", cwd=tmp_path)
    assert result.returncode == 1
    assert json.loads(result.stdout) == {"status": "incomplete", "missing": ["services"]}
    assert not (tmp_path / "project.yaml").exists()


def test_write_needs_approval(spec_file, tmp_path):
    result = run(spec_file, "--write", cwd=tmp_path)
    assert result.returncode == 1
    assert "requires approval" in result.stderr
    assert not (tmp_path / "project.yaml").exists()
    result = run(spec_file, "--write", "--approve", cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert load_project(tmp_path / "project.yaml").architecture.golden_path == "fullstack-ai"
    assert run(spec_file, "--write", "--approve", cwd=tmp_path).returncode == 1


def test_update_preserves_backup_and_repeated_update_is_noop(spec_file, tmp_path):
    assert run(spec_file, "--write", "--approve", cwd=tmp_path).returncode == 0
    path = tmp_path / "project.yaml"
    path.write_text("# keep exact original in backup\n" + path.read_text())
    original = path.read_bytes()
    spec_file.write_text("name: renamed\n")
    args = (spec_file, "--project", path, "--write", "--approve")
    assert run(*args, cwd=tmp_path).returncode == 0
    backups = list(tmp_path.glob("project.yaml.backup-*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original
    assert load_project(path).project.name == "renamed"
    before = path.read_bytes(), path.stat().st_mtime_ns
    result = run(*args, cwd=tmp_path)
    assert result.returncode == 0
    assert "No semantic changes" in result.stderr
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    assert list(tmp_path.glob("project.yaml.backup-*")) == backups


def test_interactive_asks_only_missing_and_decline_preserves_files(monkeypatch, capsys, tmp_path):
    path = tmp_path / "spec.yaml"
    path.write_text("name: demo\nweb: false\n")
    answers = iter(["local", "api", "no"])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda: next(answers))
    args = Namespace(
        spec=path,
        project=None,
        output=tmp_path / "project.yaml",
        non_interactive=False,
        json=False,
        write=True,
        approve=False,
    )
    with pytest.raises(HarnessError, match="cancelled"):
        setup(args)
    stderr = capsys.readouterr().err
    assert "Independent API service names" in stderr
    assert "Deployment environment" in stderr
    assert "Project name (" not in stderr
    assert "Does the project need" not in stderr
    assert not args.output.exists()


def test_existing_can_be_used_without_spec_and_saved_elsewhere(spec_file, tmp_path):
    assert run(spec_file, "--write", "--approve", cwd=tmp_path).returncode == 0
    existing = tmp_path / "project.yaml"
    original = existing.read_bytes()
    result = run(
        "--project", existing, "--output", "copy/project.yaml", "--write", "--approve", cwd=tmp_path
    )
    assert result.returncode == 0, result.stderr
    assert existing.read_bytes() == original
    assert load_project(tmp_path / "copy/project.yaml") == load_project(existing)


def test_bad_spec_errors_do_not_echo_secrets(tmp_path):
    path = tmp_path / "spec.yaml"
    path.write_text("name: 'my-secret-token!'\nweb: false\nservices: [api]\n")
    result = run(path, cwd=tmp_path)
    assert result.returncode == 1
    assert "my-secret-token" not in result.stderr
    assert "Traceback" not in result.stderr


def test_all_interactive_answers_and_approval(monkeypatch, capsys, tmp_path):
    answers = iter(["local", "demo", "yes", "-", "yes"])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda: next(answers))
    args = Namespace(
        spec=None,
        project=None,
        output=tmp_path.resolve() / "project.yaml",
        non_interactive=False,
        json=False,
        write=True,
        approve=False,
    )
    assert setup(args) == 0
    assert load_project(args.output).architecture.golden_path == "simple-web"
    assert "Write this proposal?" in capsys.readouterr().err


def test_interactive_eof_is_clean_cancellation(monkeypatch, tmp_path):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)

    def end_of_input():
        raise EOFError

    monkeypatch.setattr("builtins.input", end_of_input)
    args = Namespace(
        spec=None,
        project=None,
        output=tmp_path / "project.yaml",
        non_interactive=False,
        json=False,
        write=False,
        approve=False,
    )
    with pytest.raises(HarnessError, match="cancelled"):
        setup(args)
    assert not args.output.exists()
