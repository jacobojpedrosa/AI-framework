from harness.registry.base import Descriptor, Registry


class Integration(Descriptor):
    """Tool identity and metadata; no executable commands in phase 1."""


class IntegrationRegistry(Registry[Integration]):
    pass


def default_integrations() -> IntegrationRegistry:
    experimental = {
        "terraform",
        "gcp",
        "azure",
        "react",
        "fastapi",
        "docker-compose",
        "sqlite",
        "postgres",
        "pgvector",
        "redis",
        "openai",
        "gemini",
        "vertex",
        "taskiq",
        "opentelemetry",
        "openspec",
        "agent-os",
        "playwright",
    }
    registry = IntegrationRegistry(
        Integration(
            id=identifier,
            status="experimental" if identifier in experimental else "planned",
        )
        for identifier in (
            "fastapi",
            "react",
            "next",
            "postgres",
            "sqlite",
            "pgvector",
            "redis",
            "openai",
            "gemini",
            "vertex",
            "s3",
            "gcs",
            "azure-blob",
            "oidc",
            "firebase",
            "taskiq",
            "starlette-admin",
            "opentelemetry",
            "terraform",
            "openspec",
            "agent-os",
            "playwright",
            "docker-compose",
            "gcp",
            "aws",
            "azure",
        )
    )
    registry.validate()
    return registry
