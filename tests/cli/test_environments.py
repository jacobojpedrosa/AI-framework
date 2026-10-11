import json
import subprocess
import sys

import pytest

from harness.config.loader import load_project
from harness.resolution.resolver import resolve
from harness.resolution.specification import Specification
from harness.scaffolding.fullstack import render_project


def cli(*args, cwd):
    return subprocess.run(
        [sys.executable, "-m", "harness", *map(str, args)],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("environment", ["local", "gcp", "azure"])
def test_init_environment_creates_renderable_project(tmp_path, environment):
    result = cli("init", "demo", "--name", "demo", "--environment", environment, cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    config = load_project(tmp_path / "demo/project.yaml")
    files = render_project(config)
    if environment == "local":
        assert config.cloud is None and config.iac is None
        assert not any(name.startswith("infra/") for name in files)
    else:
        assert config.cloud.provider == environment
        assert config.observability.provider == "opentelemetry"
        assert f"infra/{environment}/service/main.tf" in files
    assert list((tmp_path / "demo").iterdir()) == [tmp_path / "demo/project.yaml"]


def test_aws_init_rejected_before_creating_directory(tmp_path):
    result = cli("init", "demo", "--name", "demo", "--environment", "aws", cwd=tmp_path)
    assert result.returncode == 1 and "planned" in result.stderr
    assert not (tmp_path / "demo").exists()


def test_setup_switch_preview_and_explicit_write(tmp_path):
    assert (
        cli("init", "demo", "--name", "demo", "--environment", "gcp", cwd=tmp_path).returncode == 0
    )
    path = tmp_path / "demo/project.yaml"
    original = path.read_bytes()
    result = cli(
        "setup",
        "--project",
        path,
        "--environment",
        "azure",
        "--non-interactive",
        "--json",
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["config"]["cloud"]["provider"] == "azure"
    assert path.read_bytes() == original
    result = cli(
        "setup",
        "--project",
        path,
        "--environment",
        "azure",
        "--non-interactive",
        "--write",
        "--approve",
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert load_project(path).cloud.provider == "azure"
    assert len(list(path.parent.glob("project.yaml.backup-*"))) == 1
    result = cli(
        "setup",
        "--project",
        path,
        "--environment",
        "local",
        "--non-interactive",
        "--json",
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    proposed = json.loads(result.stdout)["config"]
    assert "cloud" not in proposed and "iac" not in proposed
    assert proposed["observability"]["provider"] == "opentelemetry"
    assert load_project(path).cloud.provider == "azure"


@pytest.mark.parametrize(
    "extra",
    [
        "environment: gcp\n",
        "capabilities:\n  cloud:\n    provider: gcp\n    target: cloud-run\n",
        "capabilities:\n  database:\n    provider: sqlite\n",
        "capabilities:\n  iac: null\n",
    ],
)
def test_setup_conflicts_or_unsupported_features_never_write(tmp_path, extra):
    spec = tmp_path / "spec.yaml"
    spec.write_text("name: demo\nweb: true\nservices: [api]\n" + extra)
    result = cli(
        "setup",
        spec,
        "--environment",
        "azure",
        "--write",
        "--approve",
        "--non-interactive",
        cwd=tmp_path,
    )
    assert result.returncode == 1
    assert not (tmp_path / "project.yaml").exists()


def test_environment_from_spec_and_omission_preserve_selection(repo_root):
    existing = load_project(repo_root / "examples/cloud-azure/project.yaml")
    assert resolve(Specification(), existing).config.cloud == existing.cloud
    spec = Specification(name="demo", web=True, services=["api"], environment="azure")
    assert resolve(spec).config.cloud.provider == "azure"


def test_cloud_selection_does_not_silently_change_topology(tmp_path):
    spec = tmp_path / "spec.yaml"
    spec.write_text("name: demo\nweb: false\nservices: [api]\n")
    result = cli(
        "setup",
        spec,
        "--environment",
        "azure",
        "--write",
        "--approve",
        "--non-interactive",
        cwd=tmp_path,
    )
    assert result.returncode == 1
    assert "one React" in result.stderr
    assert not (tmp_path / "project.yaml").exists()
