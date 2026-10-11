"""Optional SDK templates; rendering never reads credentials or calls providers."""

from importlib.resources import files

import yaml

from harness.config.models import ProjectConfig


def add_ai(config: ProjectConfig, rendered: dict[str, bytes], visit, api: str) -> None:
    assert config.ai is not None
    providers = sorted(config.ai.providers)
    templates = files("harness.templates")
    visit(templates.joinpath("ai"), overlay=True)
    openai = "openai" in providers
    google = bool({"gemini", "vertex"} & set(providers))
    if openai:
        visit(templates.joinpath("ai_openai"), overlay=True)
    if google:
        visit(templates.joinpath("ai_google"), overlay=True)
    prefix = f"services/{api}/"
    dockerfile = prefix + "Dockerfile"
    rendered[dockerfile] = rendered[dockerfile].replace(
        b"COPY --chown=app:app tests ./tests\n",
        b"COPY --chown=app:app tests ./tests\nCOPY --chown=app:app evals ./evals\n",
    )
    rendered[prefix + "pyproject.toml"] += (
        b'\n[tool.ruff.lint.isort]\nknown-first-party = ["app", "tests"]\n'
    )
    rendered[prefix + "app/infrastructure/ai_settings.py"] = (
        "ENABLED_PROVIDERS = " + repr(tuple(providers)).replace("'", '"') + "\n"
    ).encode()
    if openai or google:
        sdk = "both" if openai and google else "openai" if openai else "google"
        provider = config.database.provider if config.database else None
        storage = "postgres" if provider == "postgres" else "sql" if provider == "sqlite" else ""
        if config.cache:
            storage += "-redis" if storage else "redis"
        variant = (storage or "base") + "-" + sdk
        for stem in ("requirements", "requirements-dev"):
            for extension in ("in", "txt"):
                name = f"{stem}.{extension}"
                rendered[prefix + name] = templates.joinpath(
                    "ai_locks", variant, name + ".tmpl"
                ).read_bytes()
    bootstrap = prefix + "app/infrastructure/bootstrap.py"
    text = rendered[bootstrap].decode()
    marker = "from app.application.readiness import CheckReadiness\n"
    text = text.replace(
        marker,
        marker + "from app.infrastructure.ai_configuration import AIConfigurationProbe\n"
        "from app.infrastructure.ai_runtime import RuntimeAI\n",
    )
    text = text.replace(
        "        readiness = CheckReadiness(SERVICE_NAME, "
        '{"process": ProcessProbe()}, SystemClock())',
        '        probes = {"process": ProcessProbe(), "ai_configuration": AIConfigurationProbe()}\n'
        "        readiness = CheckReadiness(SERVICE_NAME, probes, SystemClock())",
    ).replace(
        '        probes = {"process": ProcessProbe(), **resources.probes}',
        '        probes = {"process": ProcessProbe(), **resources.probes}\n'
        '        probes["ai_configuration"] = AIConfigurationProbe()',
    )
    text = text.replace(
        "    app.include_router", "    app.state.ai = RuntimeAI()\n    app.include_router"
    )
    rendered[bootstrap] = text.encode()
    path = prefix + "tests/test_readiness.py"
    rendered[path] = rendered[path].replace(
        b"with TestClient(create_app()) as client:",
        b'use_case = CheckReadiness(SERVICE_NAME, {"process": StaticProbe()}, FrozenClock())\n'
        b"    with TestClient(create_app(use_case)) as client:",
    )
    default = "fake" if "fake" in providers else providers[0]
    variables = {"AI_PROVIDER": default}
    for provider in providers:
        if provider == "fake":
            continue
        variables[provider.upper() + "_MODEL"] = ""
        if provider in {"openai", "gemini"}:
            variables[provider.upper() + "_API_KEY"] = ""
        else:
            variables.update(
                GOOGLE_CLOUD_PROJECT="", GOOGLE_CLOUD_LOCATION="", GOOGLE_APPLICATION_CREDENTIALS=""
            )
    compose = yaml.safe_load(rendered["compose.yaml"])
    env = compose["services"]["api"].setdefault("environment", {})
    env.update({key: "${" + key + ":-" + value + "}" for key, value in variables.items()})
    rendered["compose.yaml"] = yaml.safe_dump(compose, sort_keys=False).encode()
    rendered[".env.example"] += (
        "\n# AI: real models and credentials must be supplied explicitly.\n"
        + "\n".join(key + "=" + value for key, value in variables.items())
        + "\n"
    ).encode()
    for target, command in {
        "ai-check": "check",
        "ai-check-remote": "check --remote",
        "ai-generate": "generate",
        "ai-generate-live": "generate --live",
    }.items():
        rendered["Makefile"] += (
            f"\n.PHONY: {target}\n{target}:\n"
            "\t$(COMPOSE) run --build --rm --no-deps -T api python -m "
            f"app.infrastructure.ai_cli {command}\n"
        ).encode()
    rendered["README.md"] += (
        f"\n## AI providers\n\nSee `services/{api}/AI.md` for provider switching, "
        "configuration checks and explicit live tests. `make ai-check` is offline.\n"
    ).encode()
