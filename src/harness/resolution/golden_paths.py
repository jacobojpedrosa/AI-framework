from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True)
class GoldenPathMetadata:
    id: str
    description: str
    web: bool | None
    default_services: tuple[str, ...] | None
    hexagonal_services: bool


GOLDEN_PATHS = MappingProxyType(
    {
        "simple-web": GoldenPathMetadata(
            "simple-web", "Web without a separate API service", True, (), False
        ),
        "ai-service": GoldenPathMetadata(
            "ai-service", "One independent API/AI service without a web app", False, ("api",), True
        ),
        "fullstack-ai": GoldenPathMetadata(
            "fullstack-ai", "Web and one independent API service", True, ("api",), True
        ),
        "service-platform": GoldenPathMetadata(
            "service-platform", "Multiple independent services, with optional web", None, None, True
        ),
    }
)
