"""Explicit deployment selection; never discovers accounts or creates resources."""

from copy import deepcopy

from harness.config.loader import project_from_data
from harness.errors import ConfigurationError
from harness.infrastructure import TARGETS, validate_cloud


def select_environment(data: dict, environment: str) -> dict:
    selected = deepcopy(data)
    if environment == "aws":
        raise ConfigurationError("AWS remains planned; choose local, gcp or azure")
    if environment == "local":
        selected.pop("cloud", None)
        selected.pop("iac", None)
        return selected
    if environment not in {"gcp", "azure"}:
        raise ConfigurationError("Unknown environment; choose local, gcp or azure")
    selected["cloud"] = {"provider": environment, "target": TARGETS[environment]}
    selected["iac"] = {"provider": "terraform"}
    if not selected.get("observability"):
        selected["observability"] = {"provider": "opentelemetry"}
    config = project_from_data(selected)
    if (
        config.architecture.golden_path != "fullstack-ai"
        or len(config.apps) != 1
        or len(config.services) != 1
        or next(iter(config.apps.values())).framework != "react"
    ):
        raise ConfigurationError("Cloud DEV currently requires one React web app and one FastAPI")
    validate_cloud(config)
    return selected
