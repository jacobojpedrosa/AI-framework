"""Development CLI bridge; generated applications never import the harness."""

import re
import subprocess

from harness.config.loader import load_project
from harness.errors import HarnessError


def dispatch(args) -> int:
    project = args.project.resolve()
    config = load_project(project)
    if not config.jobs or not config.jobs.enabled:
        raise HarnessError("Jobs are not enabled in project.yaml")
    if args.command == "schedules" and not (config.scheduler and config.scheduler.enabled):
        raise HarnessError("Scheduler is not enabled in project.yaml")
    if len(config.services) != 1:
        raise HarnessError("Jobs management requires exactly one generated API service")
    service = next(iter(config.services))
    if not (project.parent / f"services/{service}/app/infrastructure/jobs_cli.py").is_file():
        raise HarnessError("Run this command in the generated project after make up")
    command = [
        "docker",
        "compose",
        "--file",
        str(project.parent / "compose.yaml"),
        "exec",
        "-T",
        "api",
        "python",
        "-m",
        "app.infrastructure.jobs_cli",
        args.command,
        args.action,
    ]
    if args.command == "jobs" and args.action == "run":
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,62}", args.name):
            raise HarnessError("Invalid registered job name")
        command.append(args.name)
    try:
        return subprocess.run(command, cwd=project.parent, check=False, timeout=30).returncode
    except (OSError, subprocess.TimeoutExpired):
        raise HarnessError("Jobs command unavailable; check Docker and the running API") from None
