from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import yaml

from harness.config.loader import project_from_data
from harness.config.models import ProjectConfig
from harness.errors import ConfigurationError
from harness.registry.capabilities import default_capabilities
from harness.registry.integrations import default_integrations
from harness.resolution.golden_paths import GOLDEN_PATHS
from harness.resolution.specification import Specification


@dataclass(frozen=True)
class Proposal:
    config: ProjectConfig
    reasons: tuple[str, ...]
    capabilities: tuple[str, ...]
    rationale: str | None

    def configuration(self) -> dict[str, Any]:
        return self.config.model_dump(exclude_none=True, exclude_unset=True)

    def yaml(self) -> str:
        return yaml.safe_dump(self.configuration(), sort_keys=True, allow_unicode=True)


def known_choices(spec: Specification, existing: ProjectConfig | None = None) -> dict[str, Any]:
    values = {
        "name": spec.name,
        "web": spec.web,
        "services": spec.services,
    }
    if existing:
        inherited = {
            "name": existing.project.name,
            "web": bool(existing.apps),
            "services": sorted(existing.services),
        }
        values = {key: inherited[key] if value is None else value for key, value in values.items()}
    if spec.golden_path:
        metadata = GOLDEN_PATHS[spec.golden_path]
        if values["web"] is None:
            values["web"] = metadata.web
        if values["services"] is None and metadata.default_services is not None:
            values["services"] = list(metadata.default_services)
    return values


def missing_questions(
    spec: Specification, existing: ProjectConfig | None = None
) -> tuple[str, ...]:
    return tuple(key for key, value in known_choices(spec, existing).items() if value is None)


def _merge(base: dict, patch: dict) -> dict:
    result = deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def selected_capabilities(config: ProjectConfig) -> tuple[str, ...]:
    selected: set[str] = set()
    for section in ("database", "cache", "storage", "auth", "observability"):
        block = getattr(config, section)
        if block:
            selected.add(f"{section}.{block.provider}")
    if config.database and config.database.vector:
        selected.add("database.pgvector")
    if config.ai:
        selected.update(f"ai.{provider}" for provider in config.ai.providers)
    for section in ("jobs", "scheduler"):
        block = getattr(config, section)
        if block and block.enabled:
            selected.add(f"{section}.{block.adapter}")
    if config.admin and config.admin.enabled:
        selected.add("admin.starlette")
    catalog = default_capabilities()
    catalog.validate_integrations(default_integrations())
    for identifier in sorted(selected):
        entry = catalog.get(identifier)
        if set(entry.requires) - selected:
            raise ConfigurationError("A selected capability is missing a required capability")
        if set(entry.conflicts) & selected:
            raise ConfigurationError("Selected capabilities conflict")
    return tuple(sorted(selected))


def resolve(spec: Specification, existing: ProjectConfig | None = None) -> Proposal:
    missing = missing_questions(spec, existing)
    if missing:
        raise ConfigurationError("Missing architecture choices: " + ", ".join(missing))
    facts = known_choices(spec, existing)
    services = sorted(facts["services"])
    web = facts["web"]
    if len(services) >= 2:
        selected = "service-platform"
        reason = "Multiple explicitly named independent services require service-platform."
    elif services:
        selected = "fullstack-ai" if web else "ai-service"
        reason = (
            "Web plus one API service selects fullstack-ai."
            if web
            else ("One API service without web selects ai-service.")
        )
    elif web:
        selected = "simple-web"
        reason = "Web without an independent API service selects simple-web."
    else:
        raise ConfigurationError("At least one web app or service is required")
    if spec.golden_path and spec.golden_path != selected:
        raise ConfigurationError("golden_path conflicts with the explicit web/services choices")
    if not web and spec.web_framework is not None:
        raise ConfigurationError("web_framework requires web=true")

    reasons = [reason]
    default_hexagonal = GOLDEN_PATHS[selected].hexagonal_services
    hexagonal = spec.hexagonal_services
    if hexagonal is None:
        if existing and existing.architecture.golden_path == selected:
            hexagonal = existing.architecture.hexagonal_services
            reasons.append("Existing service layering is preserved.")
        else:
            hexagonal = default_hexagonal
            reasons.append("Service layering follows the selected golden path default.")
    elif hexagonal != default_hexagonal:
        if not spec.rationale:
            raise ConfigurationError("Non-default hexagonal_services requires rationale")
        reasons.append("Non-default service layering is explicitly proposed with a rationale.")

    data = existing.model_dump(exclude_unset=True) if existing else {}
    data = _merge(data, spec.capabilities.model_dump(exclude_unset=True))
    data.update(
        schema_version=1,
        project={"name": facts["name"]},
        architecture={
            "golden_path": selected,
            "hexagonal_services": hexagonal,
        },
    )
    if web:
        apps = data.get("apps") or {"web": {"framework": "react"}}
        if spec.web_framework:
            if len(apps) != 1:
                raise ConfigurationError("web_framework cannot update multiple apps at once")
            apps = {key: {"framework": spec.web_framework} for key in apps}
        elif not existing or not existing.apps:
            reasons.append("React is the proposed web default; no web tooling is installed.")
        data["apps"] = apps
    else:
        data.pop("apps", None)
    if services:
        previous = data.get("services", {})
        data["services"] = {name: previous.get(name, {"framework": "fastapi"}) for name in services}
    else:
        data.pop("services", None)
    if spec.environment is not None:
        from harness.environments import select_environment

        explicit = spec.capabilities.model_fields_set
        if "cloud" in explicit:
            cloud = spec.capabilities.cloud
            provider = cloud.provider if cloud else "local"
            if provider != spec.environment:
                raise ConfigurationError("environment conflicts with capabilities.cloud")
        if "iac" in explicit and spec.environment != "local" and spec.capabilities.iac is None:
            raise ConfigurationError("Cloud environment requires Terraform")
        if "iac" in explicit and spec.environment == "local" and spec.capabilities.iac:
            raise ConfigurationError("Local environment conflicts with capabilities.iac")
        if (
            "observability" in explicit
            and spec.environment != "local"
            and spec.capabilities.observability is None
        ):
            raise ConfigurationError("Cloud environment requires OpenTelemetry")
        data = select_environment(data, spec.environment)
        reasons.append(f"Deployment environment selected explicitly: {spec.environment}.")
    config = project_from_data(data)
    capabilities = selected_capabilities(config)
    reasons.append("Only explicit capabilities are selected; scaffold checks their support.")
    return Proposal(config, tuple(reasons), capabilities, spec.rationale)
