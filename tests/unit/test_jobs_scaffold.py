import hashlib
import json
import subprocess
from argparse import Namespace

import pytest
import yaml

from harness.config.loader import load_project
from harness.config.models import ProjectConfig
from harness.errors import HarnessError
from harness.jobs import dispatch
from harness.scaffolding.fullstack import render_project, scaffold


def configuration(repo_root, adapter="memory", admin=False, scheduler=True):
    data = load_project(repo_root / "examples/jobs/project.yaml").model_dump(exclude_none=True)
    if adapter == "memory":
        data.pop("cache")
        data["jobs"] = {"enabled": True, "adapter": "memory"}
        data["scheduler"] = {"enabled": scheduler, "adapter": "memory"}
    else:
        data["scheduler"]["enabled"] = scheduler
    if not admin:
        data.pop("admin")
        data.pop("auth")
    return data


@pytest.mark.parametrize(
    "adapter,admin,scheduler",
    [
        ("memory", False, False),
        ("memory", False, True),
        ("memory", True, True),
        ("taskiq", False, False),
        ("taskiq", False, True),
        ("taskiq", True, True),
    ],
)
@pytest.mark.parametrize("extras", [False, True])
def test_jobs_composition_and_explicit_dependencies(repo_root, adapter, admin, scheduler, extras):
    data = configuration(repo_root, adapter, admin, scheduler)
    if extras:
        data.update(
            database={"provider": "postgres", "vector": "pgvector"},
            ai={"providers": ["fake", "openai", "gemini", "vertex"]},
        )
    config = ProjectConfig.model_validate(data)
    files = render_project(config)
    assert files == render_project(config)
    taskiq = adapter == "taskiq"
    assert ("services/api/requirements-jobs.txt" in files) == taskiq
    if taskiq:
        assert b"taskiq==0.12.6" in files["services/api/requirements-jobs.txt"]
        assert b"requirements-jobs.txt" in files["services/api/Dockerfile"]
        if admin:
            assert b"requirements-auth.txt" in files["services/api/Dockerfile"]
    compose = yaml.safe_load(files["compose.yaml"])
    assert ("worker" in compose["services"]) == taskiq
    assert ("scheduler" in compose["services"]) == (taskiq and scheduler)
    if taskiq:
        assert compose["services"]["jobs-redis"]["volumes"] == ["jobs-data:/data"]
        assert "ports" not in compose["services"]["jobs-redis"]
        assert "JOBS_REDIS_URL" not in compose["services"]["web"]["environment"]
    assert ("services/api/app/adapters/admin_schedules.py" in files) == admin
    for name, payload in files.items():
        if name.endswith(".py"):
            compile(payload, name, "exec")
    for name, digest in json.loads(files[".harness/scaffold.json"])["files"].items():
        assert hashlib.sha256(files[name]).hexdigest() == digest


@pytest.mark.parametrize("change", ["no-jobs", "mismatch", "simple", "admin-without-scheduler"])
def test_invalid_jobs_topologies_fail_before_write(repo_root, tmp_path, change):
    data = configuration(repo_root, "memory", True)
    if change == "no-jobs":
        data.pop("jobs")
    elif change == "mismatch":
        data["scheduler"] = {"enabled": True, "adapter": "taskiq", "store": "redis"}
        data["cache"] = {"provider": "redis"}
    elif change == "simple":
        data["architecture"]["hexagonal_services"] = False
    else:
        data.pop("scheduler")
    with pytest.raises(HarnessError):
        scaffold(ProjectConfig.model_validate(data), tmp_path / "new")
    assert not (tmp_path / "new").exists()


def test_cli_dispatch_uses_fixed_argv_and_checks_project(repo_root, tmp_path, monkeypatch):
    target = tmp_path / "generated"
    scaffold(ProjectConfig.model_validate(configuration(repo_root)), target)
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 7)

    monkeypatch.setattr("harness.jobs.subprocess.run", run)
    args = Namespace(
        project=target / "project.yaml", command="jobs", action="run", name="heartbeat"
    )
    assert dispatch(args) == 7
    argv, options = calls[0]
    assert argv[-3:] == ["jobs", "run", "heartbeat"]
    assert options["cwd"] == target and "shell" not in options
    args.name = "heartbeat;touch /tmp/not-authorized"
    with pytest.raises(HarnessError, match="Invalid"):
        dispatch(args)
    assert len(calls) == 1


def test_disabled_jobs_have_no_runtime_or_dependencies(repo_root):
    data = configuration(repo_root, scheduler=False)
    data["jobs"]["enabled"] = False
    files = render_project(ProjectConfig.model_validate(data))
    assert not any("jobs_runtime" in path or "requirements-jobs" in path for path in files)
