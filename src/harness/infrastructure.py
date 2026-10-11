"""Provider-independent workload metadata and explicitly scoped cloud rendering."""

import hashlib
import json
from importlib.resources import files
from typing import Literal

from pydantic import Field

from harness.config.models import ProjectConfig, StrictModel
from harness.errors import HarnessError

TERRAFORM_VERSION = "1.15.8"
GOOGLE_PROVIDER_VERSION = "8.6.0"
AZURE_PROVIDER_VERSION = "5.9.0"
TARGETS = {"gcp": "cloud-run", "aws": "ecs", "azure": "container-apps"}


class Workload(StrictModel):
    name: str
    kind: Literal["http-container"] = "http-container"
    components: list[str]
    architecture: Literal["linux/amd64"] = "linux/amd64"
    port: Literal[8080] = 8080
    stateless: Literal[True] = True
    access: Literal["authenticated", "environment-internal"] = "authenticated"
    health_path: str = "/api/health"
    readiness_path: str = "/api/readiness"
    cpu: Literal[1] = 1
    memory_mib: Literal[512, 2048] = 512
    min_instances: Literal[0] = 0
    max_instances: Literal[2] = 2


class Infrastructure(StrictModel):
    schema_version: Literal[1] = 1
    environment: Literal["dev"] = "dev"
    provider: Literal["gcp", "aws", "azure"]
    target: Literal["cloud-run", "ecs", "container-apps"]
    renderer_status: Literal["experimental", "planned"]
    workloads: list[Workload]
    persistent_resources: list[str] = Field(default_factory=list)


def metadata(config: ProjectConfig) -> Infrastructure:
    if not config.cloud:
        raise HarnessError("Infrastructure metadata requires a cloud selection")
    unsupported = [
        field
        for field in ("database", "cache", "ai", "storage", "auth", "admin", "jobs", "scheduler")
        if getattr(config, field) is not None
    ]
    if unsupported:
        raise HarnessError("Infrastructure metadata only models the stateless DEV path")
    return Infrastructure(
        provider=config.cloud.provider,
        target=TARGETS[config.cloud.provider],
        renderer_status="planned" if config.cloud.provider == "aws" else "experimental",
        workloads=[
            Workload(
                name=config.project.name,
                access="environment-internal"
                if config.cloud.provider == "azure"
                else "authenticated",
                memory_mib=2048 if config.cloud.provider == "azure" else 512,
                components=[
                    *(f"apps/{name}" for name in config.apps),
                    *(f"services/{name}" for name in config.services),
                ],
            )
        ],
    )


def validate_cloud(config: ProjectConfig) -> None:
    if not config.cloud or not config.iac:
        raise HarnessError("Cloud generation requires both cloud and iac.provider=terraform")
    if config.cloud.provider == "aws":
        raise HarnessError("AWS renderers remain planned; choose GCP or Azure")
    if not config.observability or not config.architecture.hexagonal_services:
        raise HarnessError("The DEV cloud path requires OpenTelemetry and hexagonal services")
    unsupported = [
        name
        for name in ("database", "cache", "ai", "storage", "auth", "admin", "jobs", "scheduler")
        if getattr(config, name) is not None
    ]
    if unsupported:
        raise HarnessError(
            "The stateless DEV cloud path does not implement: " + ", ".join(unsupported)
        )


def add_cloud(config: ProjectConfig, rendered: dict[str, bytes], api: str, web: str) -> None:
    validate_cloud(config)
    provider = config.cloud.provider
    suffix = hashlib.sha256(config.project.name.encode()).hexdigest()[:8]
    tokens = {
        "@@PROJECT@@": config.project.name,
        "@@API@@": api,
        "@@WEB@@": web,
        "@@CLOUD_RESOURCE@@": f"{config.project.name[:30]}-{suffix}-dev",
        "@@CLOUD_ACCOUNT@@": f"hr-{config.project.name[:12]}-{suffix}-dev",
        "@@AZURE_RESOURCE@@": f"{config.project.name[:16]}-{suffix}-dev",
        "@@AZURE_REGISTRY@@": f"hr{suffix}",
    }

    def visit(directory, prefix="", *, shared=False):
        for entry in sorted(directory.iterdir(), key=lambda path: path.name):
            if (
                shared
                and provider == "azure"
                and (
                    prefix + entry.name == "infra/gcp"
                    or prefix + entry.name == "infra/README.md.tmpl"
                )
            ):
                continue
            if entry.is_dir():
                visit(entry, prefix + entry.name + "/", shared=shared)
            elif entry.name.endswith(".tmpl"):
                text = entry.read_text()
                path = (prefix + entry.name.removesuffix(".tmpl")).replace("__API__", api)
                path = path.replace("__DOT__", ".")
                for token, value in tokens.items():
                    text = text.replace(token, value)
                if "@@" in text or path in rendered:
                    raise HarnessError("Invalid or conflicting cloud template")
                rendered[path] = text.encode()

    visit(files("harness.templates").joinpath("cloud"), shared=True)
    if provider == "azure":
        visit(files("harness.templates").joinpath("cloud_azure"))
    lock_name = "azurerm" if provider == "azure" else "google"
    lock = (
        files("harness.templates").joinpath(f"cloud_locks/{lock_name}.lock.hcl.tmpl").read_bytes()
    )
    for module in ("bootstrap", "service"):
        rendered[f"infra/{provider}/{module}/.terraform.lock.hcl"] = lock
    rendered["infra/workload.json"] = (metadata(config).model_dump_json(indent=2) + "\n").encode()
    rendered["infra/workload.schema.json"] = (
        json.dumps(Infrastructure.model_json_schema(), indent=2) + "\n"
    ).encode()
    rendered[".gitignore"] += (
        b"\n.terraform/\n*.tfstate\n*.tfstate.*\n*.tfplan\n*.auto.tfvars\n"
        b"*.auto.tfvars.json\nterraform.tfvars\nterraform.tfvars.json\ncrash.log\n"
    )
    rendered["README.md"] += (
        b"\nCloud DEV instructions: infra/README.md. No resources are created by scaffold.\n"
    )
    rendered["Makefile"] += (
        b"\n.PHONY: cloud-build infra-fmt infra-validate\ncloud-build:\n"
        b"\tdocker build --platform linux/amd64 -f Dockerfile.cloud -t harness-cloud-dev .\n"
        b"infra-fmt:\n\tterraform fmt -check -recursive infra/gcp\n"
        b"infra-validate:\n\tterraform -chdir=infra/gcp/bootstrap validate\n"
        b"\tterraform -chdir=infra/gcp/service validate\n"
    )
    if provider == "azure":
        rendered["Makefile"] = rendered["Makefile"].replace(b"infra/gcp", b"infra/azure")
