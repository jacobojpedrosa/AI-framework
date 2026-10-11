from datetime import date
from importlib.resources import files
from typing import Literal, Self

from pydantic import Field, ValidationError, field_validator, model_validator

from harness.config.loader import parse_yaml
from harness.config.models import StrictModel
from harness.errors import RegistryError
from harness.registry.base import Status
from harness.registry.integrations import IntegrationRegistry, default_integrations


class CompatibilityEntry(StrictModel):
    status: Status
    supported: str | None = None
    tested_version: str | None = None
    source: str = Field(pattern=r"^https://[^\s]+$")
    verified_at: str | None = None
    evidence: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)
    runtimes: dict[str, str] = Field(default_factory=dict)
    constraints: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_evidence(self) -> Self:
        if self.verified_at:
            date.fromisoformat(self.verified_at)
        if self.status == "supported":
            if not all(
                (
                    self.supported,
                    self.tested_version,
                    self.verified_at,
                    self.evidence,
                    self.platforms,
                )
            ):
                raise ValueError("Supported integrations require versioned test evidence")
            if self.supported != f"=={self.tested_version}":
                raise ValueError("Phase 1 compatibility supports exact tested versions only")
            if self.tested_version == "latest":
                raise ValueError("Floating versions are not supported")
        if any(not entry.strip() for entry in (*self.evidence, *self.platforms)):
            raise ValueError("Evidence and platforms must be non-empty")
        return self


class CompatibilityMatrix(StrictModel):
    schema_version: Literal[1]
    integrations: dict[str, CompatibilityEntry]

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("schema_version must be integer 1")
        return value

    def validate_registry(self, registry: IntegrationRegistry) -> None:
        if set(self.integrations) != {entry.id for entry in registry.entries()}:
            raise RegistryError(
                "Compatibility matrix must cover exactly the registered integrations"
            )
        for identifier, entry in self.integrations.items():
            if registry.get(identifier).status != entry.status:
                raise RegistryError("Registry and compatibility status disagree")


def load_compatibility() -> CompatibilityMatrix:
    text = files("harness.data").joinpath("compatibility.yaml").read_text(encoding="utf-8")
    try:
        matrix = CompatibilityMatrix.model_validate(parse_yaml(text))
    except ValidationError:
        raise RegistryError("Invalid packaged compatibility metadata") from None
    matrix.validate_registry(default_integrations())
    return matrix
