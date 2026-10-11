import hashlib
import json

import pytest

from harness.config.loader import load_project
from harness.config.models import ProjectConfig
from harness.errors import HarnessError
from harness.infrastructure import metadata
from harness.scaffolding.fullstack import render_project, scaffold


@pytest.fixture
def config(repo_root):
    return load_project(repo_root / "examples/cloud/project.yaml")


def test_cloud_generation_is_deterministic_and_records_all_files(config):
    rendered = render_project(config)
    assert rendered == render_project(config)
    manifest = json.loads(rendered[".harness/scaffold.json"])
    assert set(manifest["files"]) == set(rendered) - {".harness/scaffold.json"}
    for name, digest in manifest["files"].items():
        assert hashlib.sha256(rendered[name]).hexdigest() == digest
    assert b"@@" not in b"".join(rendered.values())
    assert b"from harness" not in rendered["services/api/app/infrastructure/cloud_server.py"]
    assert b"TELEMETRY_EXPORTER" in rendered["infra/gcp/service/main.tf"]
    assert b"COPY --from=web-build" in rendered["Dockerfile.cloud"]


@pytest.mark.parametrize(
    "provider,target", [("gcp", "cloud-run"), ("aws", "ecs"), ("azure", "container-apps")]
)
def test_provider_independent_workload_is_explicit_about_support(config, provider, target):
    data = config.model_dump()
    data["cloud"] = {"provider": provider, "target": target}
    selected = ProjectConfig.model_validate(data)
    info = metadata(selected)
    assert info.provider == provider
    assert info.target == target
    assert info.renderer_status == ("planned" if provider == "aws" else "experimental")
    workload = info.workloads[0]
    assert workload.components == ["apps/web", "services/api"]
    assert workload.architecture == "linux/amd64"
    assert workload.access == ("environment-internal" if provider == "azure" else "authenticated")
    assert workload.memory_mib == (2048 if provider == "azure" else 512)
    assert workload.min_instances == 0 and workload.max_instances == 2
    assert not info.persistent_resources
    if provider == "aws":
        with pytest.raises(HarnessError, match="remain planned"):
            render_project(selected)


def test_azure_generation_is_isolated_and_preserves_application(config):
    data = config.model_dump()
    data["cloud"] = {"provider": "azure", "target": "container-apps"}
    azure = render_project(ProjectConfig.model_validate(data))
    gcp = render_project(config)
    assert azure == render_project(ProjectConfig.model_validate(data))
    assert not any(name.startswith("infra/gcp/") for name in azure)
    assert not any(name.startswith("infra/azure/") for name in gcp)
    for name in gcp:
        if name.startswith(("apps/", "services/")) or name == "Dockerfile.cloud":
            assert gcp[name] == azure[name]
    manifest = json.loads(azure[".harness/scaffold.json"])
    assert set(manifest["files"]) == set(azure) - {".harness/scaffold.json"}
    for name, digest in manifest["files"].items():
        assert hashlib.sha256(azure[name]).hexdigest() == digest
    assert b"@@" not in b"".join(azure.values())
    assert b"5.9.0" in azure["infra/azure/service/.terraform.lock.hcl"]
    assert b"infra/gcp" not in azure["Makefile"]
    assert b"internal ingress only" in azure["infra/README.md"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("cloud", None),
        ("iac", None),
        ("observability", None),
        ("database", {"provider": "memory"}),
        ("database", {"provider": "sqlite"}),
        ("cache", {"provider": "redis"}),
        ("ai", {"providers": ["fake"]}),
        ("storage", {"provider": "local"}),
        ("auth", {"provider": "local"}),
        ("jobs", {"enabled": True, "adapter": "memory"}),
    ],
)
def test_unsupported_cloud_combinations_rejected_before_write(config, tmp_path, field, value):
    data = config.model_dump()
    data[field] = value
    selected = ProjectConfig.model_validate(data)
    with pytest.raises(HarnessError):
        scaffold(selected, tmp_path / "generated")
    assert not (tmp_path / "generated").exists()


def test_metadata_does_not_misrepresent_persistence(config):
    data = config.model_dump()
    data["database"] = {"provider": "postgres"}
    with pytest.raises(HarnessError, match="stateless"):
        metadata(ProjectConfig.model_validate(data))


def test_cloud_resource_names_are_bounded_and_stable(config):
    data = config.model_dump()
    data["project"]["name"] = "a" * 63
    data["apps"] = {"portal": {"framework": "react"}}
    data["services"] = {"gateway": {"framework": "fastapi"}}
    rendered = render_project(ProjectConfig.model_validate(data))
    assert "services/gateway/app/infrastructure/cloud_server.py" in rendered
    dockerfile = rendered["Dockerfile.cloud"].decode()
    assert "apps/portal/" in dockerfile and "services/gateway/" in dockerfile
    main = rendered["infra/gcp/service/main.tf"].decode()
    assert "hr-" + "a" * 12 in main
    assert "a" * 64 not in main


def test_cloud_disabled_adds_no_infrastructure(config):
    data = config.model_dump()
    data["cloud"] = None
    data["iac"] = None
    rendered = render_project(ProjectConfig.model_validate(data))
    assert not any(name.startswith("infra/") for name in rendered)
    assert "Dockerfile.cloud" not in rendered
