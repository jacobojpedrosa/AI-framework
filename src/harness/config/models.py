from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Name = Annotated[str, Field(pattern=r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$", max_length=63)]
GoldenPath = Literal["simple-web", "ai-service", "fullstack-ai", "service-platform"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)


class Project(StrictModel):
    name: Name


class Architecture(StrictModel):
    golden_path: GoldenPath
    hexagonal_services: bool = True


class WebApp(StrictModel):
    framework: Literal["react", "next"]


class Service(StrictModel):
    framework: Literal["fastapi"]


class Database(StrictModel):
    provider: Literal["memory", "sqlite", "postgres"]
    vector: Literal["pgvector"] | None = None


class Cache(StrictModel):
    provider: Literal["redis"]


class AI(StrictModel):
    providers: Annotated[list[Literal["fake", "openai", "gemini", "vertex"]], Field(min_length=1)]

    @model_validator(mode="after")
    def unique_providers(self) -> Self:
        if len(self.providers) != len(set(self.providers)):
            raise ValueError("ai.providers must be unique")
        return self


class Storage(StrictModel):
    provider: Literal["local", "s3", "gcs", "azure-blob"]


class Auth(StrictModel):
    provider: Literal["local", "oidc", "firebase"]
    authorization: Literal["authentication", "roles", "permissions"] = "authentication"


class Admin(StrictModel):
    enabled: bool = False
    provider: Literal["starlette-admin"] = "starlette-admin"
    resources: list[Name] = Field(default_factory=list)


class Jobs(StrictModel):
    enabled: bool = False
    adapter: Literal["memory", "taskiq"] = "memory"
    broker: Literal["redis"] | None = None


class Scheduler(StrictModel):
    enabled: bool = False
    adapter: Literal["memory", "taskiq"] = "memory"
    store: Literal["redis"] | None = None


class Observability(StrictModel):
    provider: Literal["opentelemetry"]


class Cloud(StrictModel):
    provider: Literal["gcp", "aws", "azure"]
    target: Literal["cloud-run", "ecs", "container-apps"]

    @model_validator(mode="after")
    def match_target(self) -> Self:
        targets = {"gcp": "cloud-run", "aws": "ecs", "azure": "container-apps"}
        if targets[self.provider] != self.target:
            raise ValueError("cloud.target does not match cloud.provider")
        return self


class IaC(StrictModel):
    provider: Literal["terraform"]


class ProjectConfig(StrictModel):
    schema_version: Literal[1]
    project: Project
    architecture: Architecture
    apps: dict[Name, WebApp] = Field(default_factory=dict)
    services: dict[Name, Service] = Field(default_factory=dict)
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

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("schema_version must be integer 1")
        return value

    @model_validator(mode="after")
    def coherent_capabilities(self) -> Self:
        if self.database and self.database.vector and self.database.provider != "postgres":
            raise ValueError("database.vector requires database.provider=postgres")
        if self.admin and self.admin.enabled:
            if self.auth is None:
                raise ValueError("admin.enabled requires auth")
            if not self.services:
                raise ValueError("admin.enabled requires a FastAPI service")
        if self.jobs:
            if self.jobs.adapter == "memory" and self.jobs.broker is not None:
                raise ValueError("jobs.broker is not applicable to the memory adapter")
            if self.jobs.enabled and self.jobs.adapter == "taskiq":
                if self.jobs.broker != "redis" or self.cache is None:
                    raise ValueError(
                        "jobs.taskiq requires jobs.broker=redis and cache.provider=redis"
                    )
        if self.scheduler:
            if self.scheduler.adapter == "memory" and self.scheduler.store is not None:
                raise ValueError("scheduler.store is not applicable to the memory adapter")
            if self.scheduler.enabled and self.scheduler.adapter == "taskiq":
                if self.scheduler.store != "redis" or self.cache is None:
                    raise ValueError(
                        "scheduler.taskiq requires scheduler.store=redis and cache.provider=redis"
                    )
        return self


def minimal_config(name: str) -> ProjectConfig:
    return ProjectConfig.model_validate(
        {
            "schema_version": 1,
            "project": {"name": name},
            "architecture": {"golden_path": "ai-service", "hexagonal_services": True},
            "services": {"api": {"framework": "fastapi"}},
        }
    )
