import hashlib
import json
import os
import subprocess
import sys

import pytest
import yaml

from harness.config.loader import load_project
from harness.config.models import ProjectConfig
from harness.errors import HarnessError
from harness.scaffolding import fullstack


@pytest.fixture
def fullstack_config(repo_root):
    return load_project(repo_root / "examples/specifications/fullstack-ai/expected-project.yaml")


def test_deterministic_standalone_files_and_hashes(fullstack_config):
    first = fullstack.render_project(fullstack_config)
    assert first == fullstack.render_project(fullstack_config)
    manifest = json.loads(first[".harness/scaffold.json"])
    assert set(manifest["files"]) == set(first) - {".harness/scaffold.json"}
    for path, digest in manifest["files"].items():
        assert hashlib.sha256(first[path]).hexdigest() == digest
    assert json.loads(first["apps/web/package.json"])["private"] is True
    for name in ("requirements.txt", "requirements-dev.txt"):
        assert b"--hash=sha256:" in first[f"services/api/{name}"]
        assert b"harness" not in first[f"services/api/{name}"]
    assert b"harness" not in first["apps/web/package-lock.json"]
    assert b"from harness" not in first["services/api/app/main.py"]
    assert b"@@" not in b"".join(first.values())
    assert b"/Users/" not in b"".join(first.values())


def test_safe_compose_and_matching_paths(fullstack_config):
    rendered = fullstack.render_project(fullstack_config)
    compose = yaml.safe_load(rendered["compose.yaml"])
    assert set(compose["services"]) == {"api", "web"}
    assert "volumes" not in compose
    for service in compose["services"].values():
        assert all(port.startswith("127.0.0.1:") for port in service["ports"])
        assert "healthcheck" in service
    assert compose["services"]["web"]["depends_on"]["api"]["condition"] == "service_healthy"
    assert "privileged" not in str(compose)


def test_custom_directory_names_and_disabled_processes(fullstack_config):
    data = fullstack_config.model_dump()
    data["apps"] = {"portal": {"framework": "react"}}
    data["services"] = {"gateway": {"framework": "fastapi"}}
    data["jobs"] = {"enabled": False}
    rendered = fullstack.render_project(ProjectConfig.model_validate(data))
    assert "apps/portal/package.json" in rendered
    assert "services/gateway/app/main.py" in rendered
    assert b"./services/gateway" in rendered["compose.yaml"]
    assert b"./apps/portal" in rendered["compose.yaml"]
    assert (
        b'SERVICE_NAME = "gateway"' in rendered["services/gateway/app/infrastructure/bootstrap.py"]
    )
    assert not any(name.startswith("workers/") for name in rendered)


@pytest.mark.parametrize(
    "changes",
    [
        {"architecture": {"golden_path": "ai-service"}},
        {"apps": {"web": {"framework": "next"}}},
        {"apps": {}},
        {"services": {}},
        {"services": {"one": {"framework": "fastapi"}, "two": {"framework": "fastapi"}}},
        {
            "database": {"provider": "memory"},
            "architecture": {"golden_path": "fullstack-ai", "hexagonal_services": False},
        },
        {"scheduler": {"enabled": True, "adapter": "memory"}},
        {"cloud": {"provider": "gcp", "target": "cloud-run"}},
    ],
)
def test_unsupported_choices_fail_before_writing(fullstack_config, changes, tmp_path):
    data = fullstack_config.model_dump()
    data.update(changes)
    target = tmp_path / "new-project"
    with pytest.raises(HarnessError):
        fullstack.scaffold(ProjectConfig.model_validate(data), target)
    assert not target.exists()


def test_dry_run_and_existing_targets_are_read_only(fullstack_config, tmp_path):
    target = tmp_path / "new-project"
    names = fullstack.scaffold(fullstack_config, target, dry_run=True)
    assert "project.yaml" in names
    assert not target.exists()
    target.mkdir()
    source = target / "user.py"
    source.write_text("user code")
    with pytest.raises(HarnessError, match="already exists"):
        fullstack.scaffold(fullstack_config, target)
    assert list(target.iterdir()) == [source]
    assert source.read_text() == "user code"


def test_empty_directory_is_not_overwritten(fullstack_config, tmp_path):
    target = tmp_path / "new-project"
    target.mkdir()
    with pytest.raises(HarnessError, match="already exists"):
        fullstack.scaffold(fullstack_config, target)
    assert not list(target.iterdir())


def test_symlink_destination_and_parent_rejected(fullstack_config, tmp_path):
    root = tmp_path.resolve()
    real = root / "real"
    real.mkdir()
    link = root / "link"
    link.symlink_to(real, target_is_directory=True)
    for target in (link, link / "nested"):
        with pytest.raises(HarnessError):
            fullstack.scaffold(fullstack_config, target)
    assert not list(real.iterdir())


def test_failed_generation_has_no_completion_manifest(fullstack_config, tmp_path, monkeypatch):
    target = tmp_path.resolve() / "project"

    def fail(*args, **kwargs):
        raise OSError("internal sensitive path")

    monkeypatch.setattr(fullstack, "_write_file", fail)
    with pytest.raises(HarnessError, match="partial destination") as caught:
        fullstack.scaffold(fullstack_config, target)
    assert "sensitive" not in str(caught.value)
    assert not (target / ".harness/scaffold.json").exists()


def test_result_validates_and_does_not_copy_secrets(fullstack_config, tmp_path):
    target = tmp_path.resolve() / "project"
    fullstack.scaffold(fullstack_config, target)
    assert load_project(target / "project.yaml") == fullstack_config
    assert not (target / ".env").exists()
    assert (target / ".env.example").is_file()
    assert (target / ".gitignore").is_file()


def test_hexagonal_layers_run_without_site_packages(fullstack_config, tmp_path):
    target = tmp_path.resolve() / "project"
    fullstack.scaffold(fullstack_config, target)
    script = (
        "from app.application.readiness import CheckReadiness; "
        "from tests.fakes import FrozenClock, StaticProbe; "
        "assert CheckReadiness('test', {'process': StaticProbe()}, FrozenClock()).execute().ready"
    )
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, "-S", "-c", script],
        cwd=target / "services/api",
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_generated_contracts_and_boundaries(fullstack_config, tmp_path):
    target = tmp_path.resolve() / "project"
    fullstack.scaffold(fullstack_config, target)
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/contracts", "tests/test_architecture.py"],
        cwd=target / "services/api",
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_simple_variant_has_no_hexagonal_layers(fullstack_config):
    data = fullstack_config.model_dump()
    data["architecture"]["hexagonal_services"] = False
    rendered = fullstack.render_project(ProjectConfig.model_validate(data))
    assert not any("app/domain/" in name for name in rendered)
    assert not any("tests/contracts/" in name for name in rendered)
    assert b"test-contracts:" not in rendered["Makefile"]
    assert b"FastAPI" in rendered["services/api/app/main.py"]
    assert json.loads(rendered[".harness/scaffold.json"])["service_architecture"] == "simple"
