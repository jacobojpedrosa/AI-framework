"""Explicit project-local installation of upstream development tools.

Scaffolding remains offline. Installers run in staging, never in the user's home.
This is a fresh-install operation, not a tool updater or a prompt generator.
"""

import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from importlib.resources import files
from pathlib import Path

import yaml

from harness import __version__
from harness.config.loader import load_project
from harness.errors import HarnessError

RESOURCES = files("harness.data").joinpath("tooling")
PINS = json.loads(RESOURCES.joinpath("pins.json").read_text())
TARGETS = (".harness/tooling", "openspec", "agent-os", ".claude", ".agents")
RECEIPT = ".harness/integrations.json"


def _preflight(project: Path) -> Path:
    path = Path(os.path.abspath(project))
    if ".." in project.parts or any(p.is_symlink() for p in (path, *path.parents)):
        raise HarnessError("Integration installation requires a symlink-free project path")
    for relative in ("project.yaml", ".harness", ".harness/scaffold.json"):
        if (path / relative).is_symlink():
            raise HarnessError("Integration installation refuses symlinked project metadata")
    if not (path / ".harness/scaffold.json").is_file():
        raise HarnessError("Integrations require an existing generated Harness project")
    load_project(path / "project.yaml")
    for relative in (*TARGETS, RECEIPT):
        if os.path.lexists(path / relative):
            raise HarnessError(f"Already exists: {relative}; nothing was overwritten")
    return path


def tool_environment(tooling: Path) -> dict[str, str]:
    return dict(
        os.environ,
        OPENSPEC_TELEMETRY="0",
        DO_NOT_TRACK="1",
        XDG_CONFIG_HOME=str(tooling / "state/config"),
        XDG_DATA_HOME=str(tooling / "state/data"),
        CI="1",
        NO_COLOR="1",
    )


def _run(command: list[str], cwd: Path, env: dict[str, str]) -> str:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=True,
            timeout=300,
        )
        return completed.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        # Upstream output may contain private registry URLs or environment data.
        raise HarnessError(f"Official tool command failed: {Path(command[0]).name}") from None


def _extract_agent_os(archive: Path, destination: Path) -> Path:
    if hashlib.sha256(archive.read_bytes()).hexdigest() != PINS["agent_os"]["sha256"]:
        raise HarnessError("Agent OS archive checksum mismatch; installation stopped")
    with tarfile.open(archive, "r:gz") as bundle:
        members = bundle.getmembers()
        if any(not (m.isfile() or m.isdir()) for m in members):
            raise HarnessError("Agent OS archive contains links or special files")
        bundle.extractall(destination, members=members, filter="data")
    return destination / f"agent-os-{PINS['agent_os']['commit']}"


def _prepare(stage: Path) -> dict:
    tooling = stage / ".harness/tooling"
    tooling.mkdir(parents=True)
    for name in ("package.json", "package-lock.json", "pins.json"):
        (tooling / name).write_bytes(RESOURCES.joinpath(name).read_bytes())
    env = tool_environment(tooling)
    node = shutil.which("node")
    npm = shutil.which("npm")
    bash = shutil.which("bash")
    if not all((node, npm, bash)):
        raise HarnessError("Integration installation requires Node >=20.19, npm and Bash")
    node_version = _run([node, "--version"], stage, env)
    try:
        version = tuple(int(part) for part in node_version.lstrip("v").split("."))
    except ValueError:
        raise HarnessError("Cannot determine Node version") from None
    if version < (20, 19, 0):
        raise HarnessError("OpenSpec requires Node >=20.19.0")
    npm_version = _run([npm, "--version"], stage, env)
    print("Installing locked OpenSpec dependencies locally...", flush=True)
    _run(
        [
            npm,
            "ci",
            "--ignore-scripts",
            "--no-audit",
            "--no-fund",
            "--cache",
            str(tooling / "cache"),
        ],
        tooling,
        env,
    )
    openspec = [node, str(tooling / "node_modules/@fission-ai/openspec/bin/openspec.js")]
    if _run([*openspec, "--version"], stage, env) != PINS["openspec"]:
        raise HarnessError("Installed OpenSpec version differs from the pin")
    _run(
        [
            *openspec,
            "init",
            "--tools",
            ",".join(PINS["tools"]),
            "--profile",
            "core",
            "--no-animation",
        ],
        stage,
        env,
    )
    print("Installing pinned Agent OS standards commands...", flush=True)
    archive = tooling / "agent-os.tar.gz"
    url = "https://codeload.github.com/buildermethods/agent-os/tar.gz/" + PINS["agent_os"]["commit"]
    with urllib.request.urlopen(url, timeout=60) as response:
        payload = response.read(5 * 1024 * 1024 + 1)
    if len(payload) > 5 * 1024 * 1024:
        raise HarnessError("Agent OS archive exceeds the download limit")
    archive.write_bytes(payload)
    source = _extract_agent_os(archive, tooling)
    _run([bash, str(source / "scripts/project-install.sh"), "--profile", "default"], stage, env)
    commands = stage / ".claude/commands/agent-os"
    # Keep upstream commands unchanged, activate only the standards responsibility.
    for command in commands.glob("*.md"):
        if command.stem not in PINS["agent_os_commands"]:
            command.unlink()
    for name in PINS["agent_os_commands"]:
        if (commands / f"{name}.md").read_bytes() != (
            source / "commands/agent-os" / f"{name}.md"
        ).read_bytes():
            raise HarnessError("Installed Agent OS command differs from upstream")
    # Upstream's default profile contains no installable standards in this revision.
    # This is project configuration, not an alternative specification workflow.
    (stage / "agent-os/standards/harness.md").write_text(
        "# Development ownership\n\n"
        "Agent OS owns engineering standards: how we build.\n"
        "OpenSpec owns specifications and changes: what changes.\n"
        "Harness owns configuration, scaffolding and orchestration.\n"
        "Keep domain and application logic independent of external adapters.\n"
        "Use the generated architecture documentation and make test / make lint.\n"
        "Never put credentials in specifications or standards.\n",
        encoding="utf-8",
    )
    (stage / "agent-os/standards/index.yml").write_text(
        yaml.safe_dump(
            {"root": {"harness": {"description": "Development ownership and boundaries"}}}
        ),
        encoding="utf-8",
    )
    config = stage / "openspec/config.yaml"
    data = yaml.safe_load(config.read_text())
    data["context"] = (
        "Engineering standards are in agent-os/standards/index.yml and the referenced files. "
        "OpenSpec owns all change specifications. Harness owns project.yaml and orchestration. "
        "See DEVELOPMENT_TOOLS.md for ownership and supported versions."
    )
    config.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    _run([*openspec, "list", "--json"], stage, env)
    _run([*openspec, "schemas", "--json"], stage, env)
    return {"node": node_version, "npm": npm_version}


def initialize_integrations(project: Path, *, dry_run: bool = False) -> None:
    project = _preflight(project)
    if dry_run:
        print(json.dumps({"pins": PINS, "creates": [*TARGETS, RECEIPT]}, indent=2))
        return
    lock = project / ".harness/integrations.installing"
    try:
        descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        raise HarnessError(
            "Integration installation already running or interrupted; inspect its lock"
        ) from None
    os.close(descriptor)
    published: list[Path] = []
    try:
        # Same filesystem permits directory renames. Subprocesses get a new, empty project.
        with tempfile.TemporaryDirectory(prefix="integration-", dir=project / ".harness") as temp:
            stage = Path(temp)
            runtime = _prepare(stage)
            receipt = {
                "schema_version": 1,
                "harness_version": __version__,
                "pins": PINS,
                "runtime": runtime,
                "files": {
                    str(path.relative_to(stage)): hashlib.sha256(path.read_bytes()).hexdigest()
                    for name in TARGETS[1:]
                    for path in sorted((stage / name).rglob("*"))
                    if path.is_file()
                },
            }
            _preflight(project)
            for relative in TARGETS:
                source, destination = stage / relative, project / relative
                if not source.is_dir() or source.is_symlink():
                    raise HarnessError(f"Upstream did not create expected directory: {relative}")
                # mkdir reserves the name without replacing any pre-existing entry.
                destination.mkdir()
                published.append(destination)
                os.replace(source, destination)
            with (project / RECEIPT).open("x", encoding="utf-8") as stream:
                published.append(project / RECEIPT)
                stream.write(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    except BaseException:
        for path in reversed(published):
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
        raise
    finally:
        lock.unlink(missing_ok=True)
    print(
        "Installed OpenSpec and Agent OS. See DEVELOPMENT_TOOLS.md and .harness/integrations.json."
    )


def dispatch(args) -> int:
    try:
        initialize_integrations(args.project, dry_run=args.dry_run)
    except (OSError, tarfile.TarError):
        raise HarnessError(
            "Integration installation failed; check network, permissions and tools"
        ) from None
    return 0
