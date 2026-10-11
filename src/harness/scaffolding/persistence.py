"""Compose optional, packaged persistence templates without executing any tools."""

from importlib.resources import files

import yaml

from harness.config.models import ProjectConfig

POSTGRES_IMAGE = (
    "postgres:17-bookworm@sha256:639ab7ceb90e13123085b741fb31ef493fba25463002f6da665352e7b534b652"
)
VECTOR_IMAGE = (
    "pgvector/pgvector:0.8.6-pg17-trixie@sha256:"
    "724a4041afdb1750446e3f6b5cfa8f3b0ac5a2cf538ddfa6bfee4f94c2fa85c6"
)
REDIS_IMAGE = (
    "redis:8.2-bookworm@sha256:164c759a0c342ee69d08fc99219382b0fd682181465c0df2e0e6911f4c85d73c"
)
LOCAL_DATABASE_URL = "postgresql+psycopg://harness:local-development-only@db:5432/harness"


def add_persistence(config: ProjectConfig, rendered: dict[str, bytes], visit, api: str) -> None:
    templates = files("harness.templates")
    provider = config.database.provider if config.database else None
    vector = bool(config.database and config.database.vector)
    cache = config.cache is not None
    sql = provider in {"sqlite", "postgres"}
    groups = ["persistence"]
    if provider:
        groups.append("repository")
    if sql:
        groups.append("sql")
    if vector:
        groups.append("vector")
    if cache:
        groups.append("cache")
    for group in groups:
        visit(templates.joinpath(group), overlay=True)
    service = f"services/{api}/"
    rendered[service + "app/infrastructure/persistence_settings.py"] = (
        (f"DATABASE = {repr(provider)}\nVECTOR_ENABLED = {vector}\nCACHE_ENABLED = {cache}\n")
        .replace("'", '"')
        .encode()
    )
    variant = "postgres" if provider == "postgres" else "sql" if sql else ""
    if cache:
        variant += "-redis" if variant else "redis"
    if variant:
        for stem in ("requirements", "requirements-dev"):
            for extension in ("in", "txt"):
                name = f"{stem}.{extension}"
                rendered[service + name] = templates.joinpath(
                    "persistence_locks", variant, name + ".tmpl"
                ).read_bytes()

    # Keep the pre-existing readiness unit tests independent from external services.
    test_path = service + "tests/test_readiness.py"
    rendered[test_path] = rendered[test_path].replace(
        b"with TestClient(create_app()) as client:",
        b'use_case = CheckReadiness(SERVICE_NAME, {"process": StaticProbe()}, FrozenClock())\n'
        b"    with TestClient(create_app(use_case)) as client:",
    )
    compose = yaml.safe_load(rendered["compose.yaml"])
    services = compose["services"]
    api_service = services["api"]
    environment = api_service.setdefault("environment", {})
    dependencies = api_service.setdefault("depends_on", {})
    volumes = compose.setdefault("volumes", {})
    integration_env = []
    if provider == "sqlite":
        environment["DATABASE_URL"] = "sqlite:////app/data/app.db"
        api_service["volumes"] = ["sqlite-data:/app/data"]
        volumes["sqlite-data"] = {}
    if provider == "postgres":
        environment["DATABASE_URL"] = "${DATABASE_URL:-" + LOCAL_DATABASE_URL + "}"
        dependencies["db"] = {"condition": "service_healthy"}
        volumes["postgres-data"] = {}
        services["db"] = {
            "image": VECTOR_IMAGE if vector else POSTGRES_IMAGE,
            "environment": {
                "POSTGRES_USER": "harness",
                "POSTGRES_PASSWORD": "local-development-only",
                "POSTGRES_DB": "harness",
            },
            "volumes": ["postgres-data:/var/lib/postgresql/data"],
            "healthcheck": {
                "test": ["CMD-SHELL", "pg_isready -U harness -d harness"],
                "interval": "2s",
                "timeout": "3s",
                "retries": 30,
            },
        }
        integration_env += ["-e", "TEST_DATABASE_URL=" + LOCAL_DATABASE_URL]
    if cache:
        environment["REDIS_URL"] = "${REDIS_URL:-redis://cache:6379/0}"
        dependencies["cache"] = {"condition": "service_healthy"}
        services["cache"] = {
            "image": REDIS_IMAGE,
            "tmpfs": ["/data"],
            "command": ["redis-server", "--save", "", "--appendonly", "no"],
            "healthcheck": {
                "test": ["CMD", "redis-cli", "ping"],
                "interval": "2s",
                "timeout": "3s",
                "retries": 30,
            },
        }
        integration_env += ["-e", "TEST_REDIS_URL=redis://cache:6379/0"]
    if not volumes:
        del compose["volumes"]
    rendered["compose.yaml"] = yaml.safe_dump(compose, sort_keys=False).encode()
    if sql:
        dockerfile = (
            rendered[service + "Dockerfile"]
            .decode()
            .replace(
                "COPY --chown=app:app app ./app",
                "COPY --chown=app:app app ./app\n"
                "COPY --chown=app:app migrations ./migrations\n"
                "COPY --chown=app:app alembic.ini .\n"
                "RUN mkdir -p /app/data && chown app:app /app/data",
            )
        )
        rendered[service + "Dockerfile"] = dockerfile.encode()
        rendered["Makefile"] += (
            b"\n.PHONY: migrate\nmigrate:\n"
            b"\t$(COMPOSE) run --build --rm api python -m app.infrastructure.migrate\n"
        )
    if integration_env:
        rendered["Makefile"] += (
            "\n.PHONY: test-integration\ntest-integration:\n"
            "\t$(COMPOSE) run --build --rm "
            + " ".join(integration_env)
            + " api python -m pytest tests/contracts\n"
        ).encode()
    rendered["README.md"] += (
        f"\n## Persistence\n\nSee `services/{api}/PERSISTENCE.md` for selected adapters, "
        "explicit migrations and integration tests. Run `make migrate` before using "
        "SQL storage. `make down` preserves database volumes.\n"
    ).encode()
    rendered["README.md"] = (
        rendered["README.md"]
        .replace(
            b"No persistent volumes exist in this skeleton.",
            b"Database volumes, when enabled, are preserved by make down.",
        )
        .replace(
            b"database, authentication, admin, AI provider, worker, scheduler or cloud setup.",
            b"authentication, admin, AI provider, worker, scheduler or cloud setup.",
        )
    )
