import hashlib
import json
import os
from importlib.resources import files
from pathlib import Path, PurePosixPath

import yaml

from harness import __version__
from harness.config.models import ProjectConfig
from harness.errors import HarnessError
from harness.filesystem import open_directory

TEMPLATE_VERSION = "14.0.0"


def _validate(config: ProjectConfig) -> tuple[str, str]:
    if config.architecture.golden_path != "fullstack-ai":
        raise HarnessError("Scaffolding supports fullstack-ai only")
    if len(config.apps) != 1 or len(config.services) != 1:
        raise HarnessError("fullstack-ai scaffolding requires exactly one web app and one API")
    web, app = next(iter(config.apps.items()))
    api, service = next(iter(config.services.items()))
    if app.framework != "react" or service.framework != "fastapi":
        raise HarnessError("Scaffolding supports React and FastAPI only")
    if (
        config.database
        or config.cache
        or config.ai
        or config.auth
        or config.storage
        or config.observability
        or (config.jobs and config.jobs.enabled)
        or (config.scheduler and config.scheduler.enabled)
    ) and not config.architecture.hexagonal_services:
        raise HarnessError("Runtime capabilities require hexagonal_services=true")
    if config.scheduler and config.scheduler.enabled:
        if not config.jobs or not config.jobs.enabled:
            raise HarnessError("Scheduler requires enabled jobs")
        if config.scheduler.adapter != config.jobs.adapter:
            raise HarnessError("Scheduler and jobs must use the same adapter")
    if config.admin and config.admin.enabled:
        if len(set(config.admin.resources)) != len(config.admin.resources):
            raise HarnessError("Admin resources must be unique")
        if set(config.admin.resources) - {"records", "schedules"}:
            raise HarnessError("Unknown admin resource; supported resources: records, schedules")
        if "records" in config.admin.resources and not config.database:
            raise HarnessError("Admin records requires an explicit database provider")
        if "schedules" in config.admin.resources and not (
            config.scheduler and config.scheduler.enabled
        ):
            raise HarnessError("Admin schedules requires an enabled scheduler")
    if config.cloud or config.iac:
        from harness.infrastructure import validate_cloud

        validate_cloud(config)
    return web, api


def render_project(config: ProjectConfig) -> dict[str, bytes]:
    """Pure, deterministic rendering. Does not install tools or execute templates."""
    web, api = _validate(config)
    substitutions = {"@@PROJECT@@": config.project.name, "@@WEB@@": web, "@@API@@": api}
    paths = {"__WEB__": web, "__API__": api, "__DOT__": "."}
    rendered: dict[str, bytes] = {}

    def visit(directory, prefix: str = "", *, overlay: bool = False) -> None:
        for resource in sorted(directory.iterdir(), key=lambda item: item.name):
            relative = prefix + resource.name
            if resource.is_dir():
                visit(resource, relative + "/", overlay=overlay)
            elif resource.name.endswith(".tmpl"):
                destination = relative.removesuffix(".tmpl")
                for token, value in paths.items():
                    destination = destination.replace(token, value)
                parts = PurePosixPath(destination)
                if parts.is_absolute() or ".." in parts.parts:
                    raise HarnessError("Unsafe packaged template path")
                if destination in rendered and not overlay:
                    raise HarnessError("Duplicate packaged template path")
                text = resource.read_text(encoding="utf-8")
                for token, value in substitutions.items():
                    text = text.replace(token, value)
                if "@@" in text:
                    raise HarnessError("Unresolved template token")
                rendered[destination] = text.encode("utf-8")

    visit(files("harness.templates").joinpath("fullstack_ai"))
    visit(files("harness.templates").joinpath("hardening"))
    if config.architecture.hexagonal_services:
        visit(files("harness.templates").joinpath("hexagonal_api"), overlay=True)
        rendered["Makefile"] += (
            b"\n.PHONY: test-contracts\ntest-contracts:\n"
            b"\t$(COMPOSE) run --build --rm --no-deps api python -m pytest tests/contracts\n"
        )
    if config.database or config.cache:
        from harness.scaffolding.persistence import add_persistence

        add_persistence(config, rendered, visit, api)
    if config.ai:
        from harness.scaffolding.ai import add_ai

        add_ai(config, rendered, visit, api)
    if config.auth:
        from harness.scaffolding.auth import add_auth

        add_auth(config, rendered, visit, api)
    if config.storage:
        from harness.scaffolding.storage import add_storage

        add_storage(config, rendered, visit, api)
    if config.jobs and config.jobs.enabled:
        from harness.scaffolding.jobs import add_jobs

        add_jobs(config, rendered, visit, api)
    if config.observability:
        from harness.scaffolding.observability import add_observability

        add_observability(config, rendered, visit, api, web)
    if config.cloud:
        from harness.infrastructure import add_cloud

        add_cloud(config, rendered, api, web)
    from harness.cicd import add_cicd

    add_cicd(config, rendered, api, web)
    for skill in ("backend-diagnose", "frontend-diagnose", "browser-inspect"):
        rendered[f"skills/{skill}/SKILL.md"] = (
            files("harness.data").joinpath(f"skills/{skill}/SKILL.md").read_bytes()
        )
    project_yaml = yaml.safe_dump(
        config.model_dump(exclude_none=True, exclude_unset=True), sort_keys=True
    ).encode("utf-8")
    rendered["project.yaml"] = project_yaml
    manifest = {
        "manifest_version": 1,
        "harness_version": __version__,
        "template": "fullstack-ai-skeleton",
        "template_version": TEMPLATE_VERSION,
        "service_architecture": (
            "hexagonal" if config.architecture.hexagonal_services else "simple"
        ),
        "files": {
            name: hashlib.sha256(data).hexdigest() for name, data in sorted(rendered.items())
        },
    }
    rendered[".harness/scaffold.json"] = (
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    ).encode()
    return rendered


def _write_file(root: int, relative: str, payload: bytes) -> None:
    parts = PurePosixPath(relative).parts
    descriptor = os.dup(root)
    try:
        for part in parts[:-1]:
            try:
                os.mkdir(part, mode=0o755, dir_fd=descriptor)
            except FileExistsError:
                pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        target = os.open(
            parts[-1],
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o644,
            dir_fd=descriptor,
        )
        with os.fdopen(target, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)


def scaffold(config: ProjectConfig, destination: Path, *, dry_run: bool = False) -> tuple[str, ...]:
    rendered = render_project(config)
    return write_project(rendered, destination, dry_run=dry_run)


def write_project(
    rendered: dict[str, bytes], destination: Path, *, dry_run: bool = False
) -> tuple[str, ...]:
    """Publish a fully rendered project into a new, symlink-free directory."""
    if any(
        not name or PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts
        for name in rendered
    ):
        raise HarnessError("Unsafe rendered project path")
    if dry_run:
        return tuple(sorted(rendered))
    if not destination.name or ".." in destination.parts:
        raise HarnessError("Use a new named directory without parent traversal")
    parent: int | None = None
    root: int | None = None
    created = False
    try:
        parent = open_directory(destination.parent)
        os.mkdir(destination.name, mode=0o755, dir_fd=parent)
        created = True
        root = os.open(
            destination.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
        )
        # Completion manifest is written last. No shell or installer is invoked.
        ordered = sorted(name for name in rendered if name != ".harness/scaffold.json")
        if ".harness/scaffold.json" in rendered:
            ordered.append(".harness/scaffold.json")
        for name in ordered:
            _write_file(root, name, rendered[name])
    except FileExistsError:
        if not created:
            raise HarnessError("Destination already exists; no files were changed") from None
        raise HarnessError(
            "Scaffolding stopped at a collision; inspect the partial destination"
        ) from None
    except OSError:
        message = (
            "Scaffolding failed; inspect the partial destination"
            if created
            else ("Cannot create destination; check permissions and symlink-free paths")
        )
        raise HarnessError(message) from None
    finally:
        if root is not None:
            os.close(root)
        if parent is not None:
            os.close(parent)
    return tuple(sorted(rendered))
