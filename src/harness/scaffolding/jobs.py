"""Compose explicit job registrations and optional durable worker services."""

from importlib.resources import files

import yaml

from harness.config.models import ProjectConfig
from harness.scaffolding.persistence import REDIS_IMAGE


def add_jobs(config: ProjectConfig, rendered: dict[str, bytes], visit, api: str) -> None:
    assert config.jobs and config.jobs.enabled
    templates = files("harness.templates")
    prefix = f"services/{api}/"
    taskiq = config.jobs.adapter == "taskiq"
    scheduler = bool(config.scheduler and config.scheduler.enabled)
    visit(templates.joinpath("jobs"), overlay=True)
    rendered[prefix + "app/infrastructure/jobs_selection.py"] = (
        f'ADAPTER = "{config.jobs.adapter}"\nSCHEDULER_ENABLED = {scheduler}\n'
    ).encode()
    if taskiq:
        visit(templates.joinpath("jobs_taskiq"), overlay=True)
        for extension in ("in", "txt"):
            name = f"requirements-jobs.{extension}"
            rendered[prefix + name] = templates.joinpath("jobs_locks", name + ".tmpl").read_bytes()
            for stem in ("requirements", "requirements-dev"):
                rendered[prefix + f"{stem}.{extension}"] += f"\n-r {name}\n".encode()
        path = prefix + "Dockerfile"
        rendered[path] = rendered[path].replace(
            b"COPY requirements.txt ", b"COPY requirements.txt requirements-jobs.txt "
        )
    path = prefix + "pyproject.toml"
    if b"known-first-party" not in rendered[path]:
        rendered[path] += b'\n[tool.ruff.lint.isort]\nknown-first-party = ["app", "tests"]\n'
    path = prefix + "app/infrastructure/bootstrap.py"
    text = rendered[path].decode()
    imports = [line for line in text.splitlines() if line.startswith("from app.infrastructure.")]
    new_import = "from app.infrastructure.jobs_runtime import install_jobs"
    if imports:
        start = text.index(imports[0])
        end = text.index(imports[-1]) + len(imports[-1])
        text = text[:start] + "\n".join(sorted([*imports, new_import])) + text[end:]
    else:
        marker = "from app.application.readiness import CheckReadiness\n"
        text = text.replace(marker, marker + new_import + "\n")
    # Admin factories need app.state.jobs before the admin is mounted.
    marker = "    install_auth(app)" if config.auth else "    app.include_router"
    text = text.replace(marker, "    install_jobs(app)\n" + marker)
    rendered[path] = text.encode()
    if config.admin and config.admin.enabled and "schedules" in config.admin.resources:
        visit(templates.joinpath("jobs_admin"), overlay=True)
        path = prefix + "app/infrastructure/admin.py"
        rendered[path] = rendered[path].replace(
            b"    for name in ADMIN_RESOURCES:",
            b"    from app.adapters.admin_schedules import SchedulesView\n\n"
            b'    factories["schedules"] = lambda: '
            b"SchedulesView(app.state.jobs.schedules, runtime)\n"
            b"    for name in ADMIN_RESOURCES:",
        )
    if taskiq:
        compose = yaml.safe_load(rendered["compose.yaml"])
        services = compose["services"]
        env = {
            "JOBS_REDIS_URL": "${JOBS_REDIS_URL:-redis://jobs-redis:6379/0}",
            "JOBS_NAMESPACE": "${JOBS_NAMESPACE:-" + config.project.name + "}",
        }
        services["api"].setdefault("environment", {}).update(env)
        services["api"].setdefault("depends_on", {})["jobs-redis"] = {
            "condition": "service_healthy"
        }
        compose.setdefault("volumes", {})["jobs-data"] = {}
        services["jobs-redis"] = {
            "image": REDIS_IMAGE,
            "command": ["redis-server", "--appendonly", "yes", "--appendfsync", "everysec"],
            "volumes": ["jobs-data:/data"],
            "healthcheck": {
                "test": ["CMD", "redis-cli", "ping"],
                "interval": "2s",
                "timeout": "3s",
                "retries": 30,
            },
        }
        for name in ["worker", "scheduler"] if scheduler else ["worker"]:
            command = (
                [
                    "taskiq",
                    "worker",
                    "app.infrastructure.taskiq_worker:broker",
                    "--workers",
                    "1",
                    "--ack-type",
                    "when_executed",
                ]
                if name == "worker"
                else [
                    "taskiq",
                    "scheduler",
                    "app.infrastructure.taskiq_worker:scheduler",
                    "--update-interval",
                    "1",
                ]
            )
            services[name] = {
                "build": {"context": f"./services/{api}", "target": "runtime"},
                "command": command,
                "environment": env,
                "depends_on": {"jobs-redis": {"condition": "service_healthy"}},
                "init": True,
                "security_opt": ["no-new-privileges:true"],
                "stop_grace_period": "30s",
            }
        rendered["compose.yaml"] = yaml.safe_dump(compose, sort_keys=False).encode()
        rendered[".env.example"] += (
            f"\nJOBS_REDIS_URL=redis://jobs-redis:6379/0\nJOBS_NAMESPACE={config.project.name}\n"
        ).encode()
    for target, command in {
        "jobs-list": "jobs list",
        "jobs-run": "jobs run $(JOB)",
        "schedules-list": "schedules list",
    }.items():
        rendered["Makefile"] += (
            f"\n.PHONY: {target}\n{target}:\n"
            "\t$(COMPOSE) exec -T api python -m app.infrastructure.jobs_cli " + command + "\n"
        ).encode()
    rendered["README.md"] += (
        f"\n## Jobs and schedules\n\nSee `services/{api}/JOBS.md`. "
        "Run `make jobs-list`, `make jobs-run JOB=heartbeat`, or `make schedules-list`.\n"
    ).encode()
