"""Bounded YAML parser. No aliases, merge keys, interpolation or input echo."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError
from yaml.events import AliasEvent, MappingStartEvent, SequenceStartEvent

from harness.config.models import ProjectConfig
from harness.errors import ConfigurationError

MAX_BYTES = 256 * 1024
MAX_DEPTH = 32
MAX_NODES = 10000


class BoundedSafeLoader(yaml.SafeLoader):
    def __init__(self, stream: str):
        super().__init__(stream)
        self.depth = 0
        self.nodes = 0

    def compose_node(self, parent: Any, index: Any) -> Any:
        if self.check_event(AliasEvent):
            raise ConfigurationError("YAML aliases are not allowed")
        self.nodes += 1
        if self.nodes > MAX_NODES:
            raise ConfigurationError("YAML exceeds the node limit")
        container = self.check_event(MappingStartEvent, SequenceStartEvent)
        if container:
            self.depth += 1
        try:
            if self.depth > MAX_DEPTH:
                raise ConfigurationError("YAML exceeds the nesting limit")
            return super().compose_node(parent, index)
        finally:
            if container:
                self.depth -= 1

    def construct_mapping(self, node: Any, deep: bool = False) -> dict[str, Any]:
        result = {}
        for key_node, value_node in node.value:
            if key_node.tag != "tag:yaml.org,2002:str":
                raise ConfigurationError(
                    "YAML mapping keys must be strings; merge keys are forbidden"
                )
            key = self.construct_object(key_node, deep=deep)
            if key in result:
                raise ConfigurationError("YAML contains a duplicate key")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def parse_yaml(text: str) -> dict[str, Any]:
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise ConfigurationError("YAML exceeds the 256 KiB size limit")
    try:
        value = yaml.load(text, Loader=BoundedSafeLoader)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        location = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
        raise ConfigurationError(f"Invalid or unsupported YAML{location}") from None
    except (ValueError, OverflowError):
        # SafeLoader also converts timestamps and integers; their constructors
        # can fail outside the YAMLError hierarchy. Do not echo their input.
        raise ConfigurationError("Invalid YAML scalar value") from None
    if not isinstance(value, dict):
        raise ConfigurationError("YAML root must be a non-empty mapping")
    return value


def read_text(path: Path) -> str:
    try:
        if not path.is_file():
            raise ConfigurationError("Configuration must be an existing regular file")
        with path.open("rb") as stream:
            data = stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ConfigurationError("YAML exceeds the 256 KiB size limit")
        return data.decode("utf-8")
    except (OSError, UnicodeError):
        raise ConfigurationError("Cannot read configuration as UTF-8") from None


def read_yaml(path: Path) -> dict[str, Any]:
    return parse_yaml(read_text(path))


# Only schema-owned path segments are rendered; user-controlled keys may contain secrets.
SAFE_SEGMENTS = set(ProjectConfig.model_fields) | {
    "spec_version",
    "web",
    "web_framework",
    "capabilities",
    "rationale",
    "name",
    "golden_path",
    "hexagonal_services",
    "framework",
    "provider",
    "vector",
    "providers",
    "authorization",
    "enabled",
    "resources",
    "adapter",
    "broker",
    "store",
    "target",
    "product_version",
    "title",
    "summary",
    "personas",
    "use_cases",
    "flows",
    "steps",
    "screens",
    "entities",
    "singular",
    "plural",
    "fields",
    "statuses",
    "integrations",
    "ai_capabilities",
    "constraints",
    "design",
    "direction",
    "accent",
    "references",
    "source",
    "notes",
    "seed",
    "description",
    "status",
}


def validation_message(exc: ValidationError) -> str:
    messages = []
    for error in exc.errors(include_input=False, include_context=False, include_url=False):
        location = (
            ".".join(
                str(part) if isinstance(part, int) or part in SAFE_SEGMENTS else "<field>"
                for part in error["loc"]
            )
            or "project"
        )
        # Our schema validators use static messages only. Pydantic's messages
        # describe expected types/values, without rendering input or context.
        detail = error["msg"]
        messages.append(f"{location}: {detail}")
    return "Invalid configuration: " + "; ".join(messages)


def project_from_data(data: dict[str, Any]) -> ProjectConfig:
    # bool and float compare equal to Literal[1] in Python; require an actual integer.
    if type(data.get("schema_version")) is not int:
        raise ConfigurationError("schema_version: expected integer 1")
    try:
        return ProjectConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigurationError(validation_message(exc)) from None


def load_project(path: Path) -> ProjectConfig:
    return project_from_data(read_yaml(path))
