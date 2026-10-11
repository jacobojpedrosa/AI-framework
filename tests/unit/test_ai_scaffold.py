import hashlib
import itertools
import json
import os
import subprocess
import sys

import pytest
import yaml

from harness.config.loader import load_project
from harness.config.models import ProjectConfig
from harness.errors import HarnessError
from harness.scaffolding.fullstack import render_project, scaffold

PROVIDERS = ("fake", "openai", "gemini", "vertex")
SELECTIONS = [s for size in range(1, 5) for s in itertools.combinations(PROVIDERS, size)]


@pytest.mark.parametrize("providers", SELECTIONS)
@pytest.mark.parametrize(
    "storage", ["none", "redis", "sqlite", "sqlite-redis", "postgres", "postgres-redis"]
)
def test_provider_combinations_are_explicit_and_locked(repo_root, providers, storage):
    data = load_project(
        repo_root / "examples/specifications/fullstack-ai/expected-project.yaml"
    ).model_dump(exclude_none=True)
    data["ai"] = {"providers": list(providers)}
    if storage.startswith("sqlite"):
        data["database"] = {"provider": "sqlite"}
    if storage.startswith("postgres"):
        data["database"] = {"provider": "postgres", "vector": "pgvector"}
    if "redis" in storage:
        data["cache"] = {"provider": "redis"}
    config = ProjectConfig.model_validate(data)
    rendered = render_project(config)
    assert rendered == render_project(config)
    req = rendered["services/api/requirements.txt"]
    assert (b"openai==3.19.0" in req) == ("openai" in providers)
    assert (b"google-genai==2.25.0" in req) == bool({"gemini", "vertex"} & set(providers))
    compose = yaml.safe_load(rendered["compose.yaml"])
    assert "OPENAI_API_KEY" not in compose["services"]["web"].get("environment", {})
    assert ("OPENAI_API_KEY" in compose["services"]["api"]["environment"]) == (
        "openai" in providers
    )
    assert b'"ai_configuration"' in rendered["services/api/app/infrastructure/bootstrap.py"]
    for name, payload in rendered.items():
        if name.endswith(".py"):
            compile(payload, name, "exec")
    for name, digest in json.loads(rendered[".harness/scaffold.json"])["files"].items():
        assert hashlib.sha256(rendered[name]).hexdigest() == digest


def test_fake_domain_and_use_case_need_no_sdk(repo_root, tmp_path):
    data = load_project(
        repo_root / "examples/specifications/fullstack-ai/expected-project.yaml"
    ).model_dump()
    data["ai"] = {"providers": ["fake"]}
    destination = tmp_path.resolve() / "fake"
    scaffold(ProjectConfig.model_validate(data), destination)
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [
            sys.executable,
            "-S",
            "-c",
            "from app.application.generate_text import GenerateText; "
            "from app.adapters.fake_ai import FakeAI; from app.domain.ai import TextRequest; "
            "assert GenerateText(FakeAI()).execute(TextRequest('test')).provider == 'fake'",
        ],
        cwd=destination / "services/api",
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_ai_requires_hexagonal_service(repo_root):
    data = load_project(
        repo_root / "examples/specifications/fullstack-ai/expected-project.yaml"
    ).model_dump()
    data["ai"] = {"providers": ["fake"]}
    data["architecture"]["hexagonal_services"] = False
    with pytest.raises(HarnessError, match="hexagonal"):
        render_project(ProjectConfig.model_validate(data))
