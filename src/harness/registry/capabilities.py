from harness.errors import RegistryError
from harness.registry.base import Descriptor, Registry
from harness.registry.integrations import IntegrationRegistry


class Capability(Descriptor):
    integration: str | None = None


class CapabilityRegistry(Registry[Capability]):
    def validate_integrations(self, integrations: IntegrationRegistry) -> None:
        self.validate()
        for capability in self.entries():
            if capability.integration:
                integration = integrations.get(capability.integration)
                if capability.status == "supported" and integration.status != "supported":
                    raise RegistryError("Supported capability requires a supported integration")


def default_capabilities() -> CapabilityRegistry:
    catalog = {
        "database.memory": None,
        "database.sqlite": "sqlite",
        "database.postgres": "postgres",
        "database.pgvector": "pgvector",
        "cache.redis": "redis",
        "ai.fake": None,
        "ai.openai": "openai",
        "ai.gemini": "gemini",
        "ai.vertex": "vertex",
        "storage.local": None,
        "storage.s3": "s3",
        "storage.gcs": "gcs",
        "storage.azure-blob": "azure-blob",
        "auth.local": None,
        "auth.oidc": "oidc",
        "auth.firebase": "firebase",
        "jobs.memory": None,
        "jobs.taskiq": "taskiq",
        "scheduler.memory": None,
        "scheduler.taskiq": "taskiq",
        "admin.starlette": "starlette-admin",
        "observability.opentelemetry": "opentelemetry",
    }
    dependencies = {
        "database.pgvector": ("database.postgres",),
        "jobs.taskiq": ("cache.redis",),
        "scheduler.taskiq": ("cache.redis",),
    }
    registry = CapabilityRegistry(
        Capability(
            id=identifier,
            integration=integration,
            requires=dependencies.get(identifier, ()),
            status=(
                "experimental"
                if identifier.startswith(("database.", "ai.", "jobs.", "scheduler."))
                or identifier in {"cache.redis", "observability.opentelemetry"}
                else "planned"
            ),
        )
        for identifier, integration in catalog.items()
    )
    registry.validate()
    return registry
