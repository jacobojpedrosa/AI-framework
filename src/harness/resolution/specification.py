from pathlib import Path
from typing import Literal, Self

from pydantic import Field, ValidationError, field_validator, model_validator

from harness.config.loader import parse_yaml, read_text, validation_message
from harness.config.models import (
    AI,
    Admin,
    Auth,
    Cache,
    Cloud,
    Database,
    GoldenPath,
    IaC,
    Jobs,
    Name,
    Observability,
    Scheduler,
    Storage,
    StrictModel,
)
from harness.errors import ConfigurationError


class CapabilityChoices(StrictModel):
    """Partial capability blocks; omission preserves an existing project block."""

    database: Database | None = None
    cache: Cache | None = None
    ai: AI | None = None
    storage: Storage | None = None
    auth: Auth | None = None
    admin: Admin | None = None
    jobs: Jobs | None = None
    scheduler: Scheduler | None = None
    observability: Observability | None = None
    cloud: Cloud | None = None
    iac: IaC | None = None


class Specification(StrictModel):
    spec_version: Literal[1] = 1
    name: Name | None = None
    environment: Literal["local", "gcp", "azure", "aws"] | None = None
    web: bool | None = None
    services: list[Name] | None = Field(default=None, max_length=32)
    golden_path: GoldenPath | None = None
    web_framework: Literal["react", "next"] | None = None
    hexagonal_services: bool | None = None
    rationale: str | None = Field(default=None, min_length=1, max_length=1000)
    capabilities: CapabilityChoices = Field(default_factory=CapabilityChoices)

    @field_validator("spec_version", mode="before")
    @classmethod
    def integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("spec_version must be integer 1")
        return value

    @model_validator(mode="after")
    def coherent_input(self) -> Self:
        if self.services is not None and len(set(self.services)) != len(self.services):
            raise ValueError("services must contain unique names")
        if self.rationale is not None and not self.rationale.strip():
            raise ValueError("rationale must contain an explanation")
        return self


def specification_from_data(data: dict) -> Specification:
    try:
        return Specification.model_validate(data)
    except ValidationError as exc:
        raise ConfigurationError(validation_message(exc)) from None


def load_specification(path: Path) -> Specification:
    text = read_text(path)
    if path.suffix.lower() in (".md", ".markdown"):
        # Only a deliberately marked, top-level fenced block is machine input.
        # Prose, shell snippets and other fences never supply instructions.
        blocks: list[str] = []
        current: list[str] | None = None
        fence: str | None = None
        for line in text.splitlines():
            if fence is None:
                if line.startswith("```") or line.startswith("~~~"):
                    marker = line[:3]
                    count = len(line) - len(line.lstrip(marker[0]))
                    fence = marker[0] * count
                    current = [] if line[count:].strip() == "harness-spec" else None
            elif line.strip() == fence:
                if current is not None:
                    blocks.append("\n".join(current))
                fence, current = None, None
            elif current is not None:
                current.append(line)
        if current is not None:
            raise ConfigurationError("Unclosed harness-spec Markdown block")
        if len(blocks) > 1:
            raise ConfigurationError("Use exactly one harness-spec Markdown block")
        if not blocks:
            raise ConfigurationError(
                "Markdown requires a harness-spec block; free prose is not inferred. "
                "Run setup without a spec to answer architecture questions."
            )
        text = blocks[0]
    return specification_from_data(parse_yaml(text))
