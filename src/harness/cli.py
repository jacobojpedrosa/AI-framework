import argparse
import os
from pathlib import Path

import yaml
from pydantic import ValidationError

from harness.config.loader import load_project, project_from_data, validation_message
from harness.config.models import minimal_config
from harness.errors import ConfigurationError, HarnessError
from harness.filesystem import open_directory as _open_directory
from harness.logging import configure_logging


def initialize(directory: Path, name: str, environment: str | None = None) -> None:
    try:
        config = minimal_config(name)
    except ValidationError as exc:
        raise ConfigurationError(validation_message(exc)) from None
    data = config.model_dump(exclude_unset=True)
    if environment is not None:
        from harness.environments import select_environment

        data["architecture"] = {"golden_path": "fullstack-ai", "hexagonal_services": True}
        data["apps"] = {"web": {"framework": "react"}}
        data = select_environment(data, environment)
        config = project_from_data(data)
    payload = yaml.safe_dump(config.model_dump(exclude_unset=True), sort_keys=False)
    try:
        directory_fd = _open_directory(directory)
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
            file_fd = os.open("project.yaml", flags, 0o644, dir_fd=directory_fd)
            try:
                with os.fdopen(file_fd, "w", encoding="utf-8") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
            except BaseException:
                # Remove only the file created by this invocation if writing failed.
                os.unlink("project.yaml", dir_fd=directory_fd)
                raise
        finally:
            os.close(directory_fd)
    except FileExistsError:
        raise HarnessError("project.yaml already exists; nothing was overwritten") from None
    except OSError:
        raise HarnessError(
            "Cannot create project.yaml; check permissions and symlink-free path"
        ) from None


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="harness", description="Internal development harness")
    commands = root.add_subparsers(dest="command", required=True)
    init = commands.add_parser(
        "init", help="Create a minimal project.yaml without overwriting files"
    )
    init.add_argument("directory", nargs="?", type=Path, default=Path("."))
    init.add_argument(
        "--name", required=True, help="Lowercase project name, e.g. example-ai-project"
    )
    validate = commands.add_parser(
        "validate", help="Validate declarative configuration (read-only)"
    )
    validate.add_argument("file", nargs="?", type=Path, default=Path("project.yaml"))
    setup = commands.add_parser(
        "setup", help="Propose a golden path from explicit architecture choices"
    )
    setup.add_argument(
        "spec", nargs="?", type=Path, help="YAML spec or Markdown harness-spec block"
    )
    setup.add_argument("--project", type=Path, help="Existing project.yaml to preserve and update")
    setup.add_argument(
        "--output", type=Path, help="Output file (default: existing project or project.yaml)"
    )
    setup.add_argument(
        "--non-interactive", action="store_true", help="Report missing choices without prompting"
    )
    setup.add_argument("--json", action="store_true", help="Emit a machine-readable proposal")
    for command in (init, setup):
        command.add_argument(
            "--environment",
            choices=("local", "gcp", "azure", "aws"),
            help="Deployment environment: local, GCP or Azure; AWS is planned (not executable)",
        )
    setup.add_argument(
        "--write", action="store_true", help="Save after showing and approving the proposal"
    )
    setup.add_argument(
        "--approve", action="store_true", help="Explicitly approve the configuration write"
    )
    readiness = commands.add_parser("readiness", help="Read-only production evidence report")
    readiness.add_argument("--project", type=Path, default=Path("."))
    update = commands.add_parser("update", help="Preview a pinned update in an isolated Git branch")
    update.add_argument("--project", type=Path, default=Path("."))
    update.add_argument("--target-version")
    update.add_argument("--checks", type=Path, help="Reviewed JSON validation commands")
    update.add_argument("--apply", action="store_true")
    update.add_argument("--approve", help="Exact approval hash returned by preview")
    update.add_argument("--worktree", type=Path, help="New isolated destination")
    scaffold = commands.add_parser("scaffold", help="Generate a standalone fullstack-ai skeleton")
    doctor = commands.add_parser(
        "doctor", help="Read-only diagnosis; explicit missing-file repairs"
    )
    doctor.add_argument("--project", type=Path, default=Path("."))
    doctor.add_argument("--json", action="store_true")
    doctor.add_argument(
        "--strict", action="store_true", help="Also fail on warnings/unverified checks"
    )
    doctor.add_argument(
        "--runtime",
        action="store_true",
        help="Read local endpoints and scoped Docker status/log summaries",
    )
    doctor.add_argument("--api-url")
    doctor.add_argument("--web-url")
    doctor.add_argument("--compose-project")
    doctor.add_argument(
        "--fix", action="store_true", help="Preview restoration of missing original files"
    )
    doctor.add_argument("--approve", action="store_true", help="Approve the displayed repair plan")
    scaffold.add_argument("project", type=Path, help="Validated project.yaml")
    scaffold.add_argument("--output", required=True, type=Path, help="New destination directory")
    scaffold.add_argument("--dry-run", action="store_true", help="List files without writing")
    design = commands.add_parser(
        "project-design", help="Review product input and missing decisions"
    )
    design.add_argument("spec", type=Path, help="Structured product YAML")
    design.add_argument("--output", type=Path, help="New documentation directory")
    design.add_argument("--json", action="store_true", help="Emit missing questions as JSON")
    prototype = commands.add_parser("prototype", help="Generate a local collection prototype")
    prototype.add_argument("spec", type=Path, help="Reviewed product YAML")
    prototype.add_argument("--output", required=True, type=Path, help="New project directory")
    prototype.add_argument("--approve", action="store_true", help="Approve the input definition")
    prototype.add_argument("--dry-run", action="store_true", help="List files without writing")
    integrations = commands.add_parser(
        "integrations", help="Install pinned development tools locally"
    )
    integration_actions = integrations.add_subparsers(dest="action", required=True)
    integration_init = integration_actions.add_parser(
        "init", help="Fresh official OpenSpec/Agent OS installation"
    )
    integration_init.add_argument("--project", type=Path, default=Path("."))
    integration_init.add_argument(
        "--dry-run", action="store_true", help="Show pins and paths without installing"
    )
    for area in ("jobs", "schedules"):
        group = commands.add_parser(
            area, help="Manage registered jobs in a running generated project"
        )
        actions = group.add_subparsers(dest="action", required=True)
        for action in ("list", "run") if area == "jobs" else ("list",):
            command = actions.add_parser(action)
            command.add_argument("--project", type=Path, default=Path("project.yaml"))
            if action == "run":
                command.add_argument("name")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    logger = configure_logging()
    try:
        if args.command == "init":
            initialize(args.directory, args.name, args.environment)
            print("Created project.yaml. No integrations installed.")
        elif args.command == "validate":
            load_project(args.file)
            print("Configuration is valid. Integrations and runtime health have not been checked.")
        elif args.command == "readiness":
            from harness.readiness import dispatch

            return dispatch(args)
        elif args.command == "update":
            from harness.update import dispatch

            return dispatch(args)
        elif args.command == "doctor":
            from harness.doctor import dispatch

            return dispatch(args)
        elif args.command == "setup":
            from harness.resolution.setup import setup

            return setup(args)
        elif args.command == "scaffold":
            from harness.scaffolding.fullstack import scaffold

            generated = scaffold(load_project(args.project), args.output, dry_run=args.dry_run)
            if args.dry_run:
                print("\n".join(generated))
            else:
                print(f"Generated {len(generated)} files. Run make up in the new directory.")
        elif args.command in {"jobs", "schedules"}:
            from harness.jobs import dispatch

            return dispatch(args)
        elif args.command == "integrations":
            from harness.integrations import dispatch

            return dispatch(args)
        elif args.command == "project-design":
            from harness.product import dispatch_design

            return dispatch_design(args)
        elif args.command == "prototype":
            from harness.prototype import dispatch_prototype

            return dispatch_prototype(args)
        return 0
    except HarnessError as exc:
        logger.error("%s", exc)
        return 1
