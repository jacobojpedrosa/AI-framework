import hashlib
import json

import pytest
import yaml

from harness.config.loader import load_project
from harness.config.models import ProjectConfig
from harness.errors import HarnessError
from harness.scaffolding.fullstack import render_project


@pytest.mark.parametrize("extra", ["none", "jobs", "ai", "persistence", "all"])
def test_optional_observability_composes_without_frontend_credentials(repo_root, extra):
    data = load_project(repo_root / "examples/observability/project.yaml").model_dump(
        exclude_none=True
    )
    if extra in {"jobs", "all"}:
        data.update(
            cache={"provider": "redis"},
            jobs={"enabled": True, "adapter": "taskiq", "broker": "redis"},
        )
    if extra in {"ai", "all"}:
        data["ai"] = {"providers": ["fake", "openai", "gemini", "vertex"]}
    if extra in {"persistence", "all"}:
        data["database"] = {"provider": "sqlite"}
    if extra == "all":
        data.update(auth={"provider": "local"}, admin={"enabled": True, "resources": ["records"]})
    config = ProjectConfig.model_validate(data)
    rendered = render_project(config)
    assert rendered == render_project(config)
    assert b"opentelemetry-sdk==1.44.0" in rendered["services/api/requirements-telemetry.txt"]
    assert b"requirements-telemetry.txt" in rendered["services/api/Dockerfile"]
    package = json.loads(rendered["apps/web/package.json"])
    assert package["dependencies"]["@opentelemetry/sdk-trace-base"] == "2.11.0"
    compose = yaml.safe_load(rendered["compose.yaml"])
    assert "OTEL_EXPORTER_OTLP_HEADERS" in compose["services"]["api"]["environment"]
    assert "OTEL_EXPORTER_OTLP_HEADERS" not in compose["services"]["web"]["environment"]
    for name, content in rendered.items():
        if name.endswith(".py"):
            compile(content, name, "exec")
    for name, digest in json.loads(rendered[".harness/scaffold.json"])["files"].items():
        assert hashlib.sha256(rendered[name]).hexdigest() == digest


def test_telemetry_is_opt_in_and_requires_hexagonal_runtime(repo_root):
    data = load_project(repo_root / "examples/observability/project.yaml").model_dump(
        exclude_none=True
    )
    data["architecture"]["hexagonal_services"] = False
    with pytest.raises(HarnessError, match="hexagonal"):
        render_project(ProjectConfig.model_validate(data))
    data.pop("observability")
    rendered = render_project(ProjectConfig.model_validate(data))
    assert not any("telemetry" in name for name in rendered)
    assert b"opentelemetry" not in rendered["apps/web/package-lock.json"]
