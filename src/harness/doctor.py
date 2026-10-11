"""Read-only project diagnosis and explicitly approved missing-file restoration."""

import ast
import hashlib
import json
import os
import re
import stat
import sys
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

from harness import __version__
from harness.config.loader import parse_yaml, project_from_data
from harness.errors import HarnessError
from harness.registry.compatibility import load_compatibility
from harness.resolution.writer import write_configuration

LIMIT = 2 * 1024 * 1024


@dataclass(frozen=True)
class Finding:
    id: str
    status: str
    message: str
    action: str = ""


class ProjectFiles:
    """Bounded regular-file reads through directory descriptors; never mkdir or follow links."""

    def __init__(self, root):
        self.root = Path(os.path.abspath(root))
        if ".." in Path(root).parts:
            raise HarnessError("Doctor refuses parent traversal")
        descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
        try:
            for part in self.root.parts[1:]:
                child = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
                )
                os.close(descriptor)
                descriptor = child
        except OSError:
            os.close(descriptor)
            raise HarnessError(
                "Doctor requires an existing symlink-free project directory"
            ) from None
        self.fd = descriptor

    def close(self):
        os.close(self.fd)

    def read(self, relative):
        parts = PurePosixPath(relative)
        if parts.is_absolute() or ".." in parts.parts or not parts.parts:
            raise HarnessError("Unsafe project metadata path")
        parent = os.dup(self.fd)
        try:
            for part in parts.parts[:-1]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                os.close(parent)
                parent = child
            fd = os.open(parts.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            with os.fdopen(fd, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise HarnessError("Doctor reads regular files only")
                data = stream.read(LIMIT + 1)
                if len(data) > LIMIT:
                    raise HarnessError("Diagnostic file exceeds the size limit")
                return data
        except FileNotFoundError:
            return None
        except OSError:
            raise HarnessError("Unreadable or symlinked project file") from None
        finally:
            os.close(parent)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inspect_project(files):
    findings = []
    fixes = {}

    def add(identifier, status, message, action=""):
        findings.append(Finding(identifier, status, message, action))

    raw = files.read("project.yaml")
    try:
        if raw is None:
            raise HarnessError("Missing configuration")
        config = project_from_data(parse_yaml(raw.decode()))
    except (HarnessError, UnicodeError):
        add(
            "project.config",
            "fail",
            "project.yaml is missing or invalid.",
            "Review project.yaml with harness validate; input values are not printed.",
        )
        return findings, fixes, None
    add("project.config", "pass", "Declarative configuration is valid; credentials not verified.")
    manifest = {}
    try:
        data = files.read(".harness/scaffold.json")
        if data:
            manifest = json.loads(data)
            entries = manifest["files"]
            if not isinstance(entries, dict) or len(entries) > 2000:
                raise ValueError
            if any(
                not isinstance(name, str)
                or not isinstance(value, str)
                or not re.fullmatch("[a-f0-9]{64}", value)
                or PurePosixPath(name).is_absolute()
                or ".." in PurePosixPath(name).parts
                for name, value in entries.items()
            ):
                raise ValueError
    except (ValueError, KeyError, TypeError, UnicodeError, RecursionError):
        add("project.manifest", "fail", "Scaffold manifest is invalid; no repairs proposed.")
        manifest = {}
    if not manifest:
        add(
            "project.structure",
            "warn",
            "No usable scaffold manifest; completeness cannot be proved.",
        )
    else:
        missing, changed = [], []
        secrets_found = False
        for name, expected in sorted(manifest["files"].items()):
            try:
                data = files.read(name)
            except HarnessError:
                add("project.path", "fail", "A manifest file is unsafe or unreadable.")
                continue
            if data is None:
                missing.append(name)
                add(
                    "file.missing:" + name,
                    "fail",
                    "Generated file is missing.",
                    "Use doctor --fix to preview available restorations.",
                )
            elif digest(data) != expected:
                changed.append(name)
            if data and re.search(
                rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
                rb"AKIA[A-Z0-9]{16}|gh[pousr]_[A-Za-z0-9]{36,}",
                data,
            ):
                secrets_found = True
        add(
            "security.manifest-secrets",
            "fail" if secrets_found else "pass",
            "Possible secret in a manifest file; value withheld."
            if secrets_found
            else "No baseline secret patterns found in manifest files; not a complete Git scan.",
        )
        add(
            "project.integrity",
            "warn" if changed else "pass",
            f"{len(changed)} files differ from original hashes; edits may be intentional.",
        )
        if manifest.get("harness_version") != __version__:
            add(
                "framework.version",
                "warn",
                "Project provenance differs from this Core version.",
                "Review version compatibility; doctor does not upgrade projects.",
            )
        elif missing and manifest["files"].get("project.yaml") == digest(raw):
            from harness.scaffolding.fullstack import render_project

            try:
                rendered = render_project(config)
                for name in missing:
                    payload = rendered.get(name)
                    if payload is not None and digest(payload) == manifest["files"][name]:
                        fixes[name] = payload
            except HarnessError:
                pass

    for tool, marker in (
        ("openspec", "openspec/config.yaml"),
        ("agent-os", "agent-os/standards/index.yml"),
    ):
        initialized = files.read(marker) is not None
        add(
            "tools." + tool,
            "pass" if initialized else "warn",
            "Initialization marker present." if initialized else "Initialization marker not found.",
            ""
            if initialized
            else "Review harness integrations init --dry-run; doctor never installs tools.",
        )
    matrix = load_compatibility()
    add(
        "framework.matrix",
        "pass",
        f"Packaged compatibility matrix valid ({len(matrix.integrations)} entries).",
    )
    add(
        "framework.updates",
        "unverified",
        "No online latest-version lookup or implicit upgrade performed.",
    )

    environment = {}
    env_data = files.read(".env")
    if env_data:
        for line in env_data.decode(errors="replace").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                if re.fullmatch("[A-Z][A-Z0-9_]*", key.strip()):
                    environment[key.strip()] = value.strip().strip("'\"")
    environment.update(
        {
            key: value
            for key, value in os.environ.items()
            if key.startswith(
                (
                    "AUTH_",
                    "OIDC_",
                    "FIREBASE_",
                    "OPENAI_",
                    "GEMINI_",
                    "GOOGLE_",
                    "STORAGE_",
                    "TELEMETRY_",
                    "OTEL_",
                )
            )
        }
    )

    if config.auth:
        needed = ["AUTH_SESSION_SECRET"]
        if config.auth.provider == "local":
            needed += ["AUTH_LOCAL_USERNAME", "AUTH_LOCAL_PASSWORD_HASH"]
        elif config.auth.provider == "oidc":
            needed += ["OIDC_ISSUER", "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET", "OIDC_REDIRECT_URI"]
        else:
            needed += ["FIREBASE_PROJECT_ID", "FIREBASE_WEB_API_KEY"]
        absent = [key for key in needed if not environment.get(key)]
        add(
            "auth.configuration",
            "warn" if absent else "pass",
            "Required authentication settings absent locally."
            if absent
            else "Required settings present; validity not established.",
            "Runtime-injected secrets may differ; no secret values are displayed.",
        )
        if environment.get("AUTH_COOKIE_SECURE") == "false":
            add("auth.cookies", "warn", "Secure cookies are disabled; review local-only use.")
    if config.admin and config.admin.enabled:
        add(
            "auth.admin",
            "unverified",
            "Declarative auth required; runtime admin authorization needs a dedicated check.",
        )
    if config.ai:
        for provider in config.ai.providers:
            if provider == "fake":
                continue
            key = {"openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY"}.get(provider)
            add(
                "ai." + provider,
                "warn" if key and not environment.get(key) else "unverified",
                "Credential validity and model access not tested; no paid model call is made.",
            )

    for area in ("database", "cache", "storage", "jobs", "scheduler"):
        capability = getattr(config, area)
        if capability is not None and getattr(capability, "enabled", True):
            add(
                area + ".runtime",
                "unverified",
                "Use explicit runtime diagnosis; configuration alone is not availability.",
            )
    if config.database:
        add(
            "database.migrations",
            "unverified",
            "Applied migrations and pgvector extension are not inferred from source files.",
        )
    if config.observability:
        mode = environment.get("TELEMETRY_EXPORTER", "console")
        invalid = mode not in {"none", "console", "otlp"} or (
            mode == "otlp" and not environment.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        )
        add(
            "observability.configuration",
            "fail" if invalid else "pass",
            "Telemetry settings invalid or incomplete."
            if invalid
            else "Exporter selection is structurally valid.",
        )
        add(
            "observability.export",
            "unverified",
            "Collector delivery is not proved by configuration.",
        )
    if config.cloud:
        for module in ("bootstrap", "service"):
            present = files.read(f"infra/{config.cloud.provider}/{module}/.terraform.lock.hcl")
            add(
                "infrastructure.lock." + module,
                "pass" if present else "fail",
                "Provider lock present." if present else "Provider lock missing.",
            )
        for check in ("terraform", "state", "dev-deployment"):
            add(
                "infrastructure." + check,
                "unverified",
                "No provider executable, remote state or cloud account accessed.",
                "Use isolated Terraform verification and an authorized cloud deployment check.",
            )

    ci = files.read(".github/workflows/ci.yml")
    add(
        "ci.validation",
        "pass" if ci else "fail",
        "Validation workflow present." if ci else "Validation workflow missing.",
    )
    if ci:
        add(
            "security.dependency-audit",
            "pass" if b"pip-audit" in ci and b"npm audit" in ci else "warn",
            "Audit steps detected; this is not an audit result.",
        )
    prod = files.read(".github/workflows/production.yml")
    if prod:
        try:
            workflow = parse_yaml(re.sub(r"(?m)^on\s*:", "'on':", prod.decode()))
            triggers = workflow.get("on")
            manual = isinstance(triggers, dict) and set(triggers) == {"workflow_dispatch"}
            add(
                "ci.production-trigger",
                "pass" if manual else "fail",
                "Production trigger is manual-only."
                if manual
                else "Production workflow has an unexpected trigger.",
            )
        except (HarnessError, UnicodeError):
            add("ci.production-trigger", "fail", "Production workflow cannot be safely parsed.")
        add(
            "ci.environment-protection",
            "unverified",
            "Actual GitHub Environment protection requires authenticated GitHub verification.",
        )
    for api in config.services:
        entry = files.read(f"services/{api}/app/main.py")
        try:
            if entry is None:
                raise ValueError
            ast.parse(entry)
            add(
                "backend.source:" + api,
                "pass",
                "Python entrypoint syntax valid; imports not executed.",
            )
        except (SyntaxError, ValueError, UnicodeError):
            add(
                "backend.source:" + api,
                "fail",
                "Backend entrypoint missing or invalid Python syntax.",
            )
        source = files.read(f"services/{api}/app/infrastructure/bootstrap.py") or b""
        if b"CORSMiddleware" in source and (b'"*"' in source or b"'*'" in source):
            add(
                "security.cors",
                "warn",
                "Possible wildcard CORS detected; review backend configuration.",
            )
    for web in config.apps:
        try:
            package = json.loads(files.read(f"apps/{web}/package.json") or b"null")
            lock = json.loads(files.read(f"apps/{web}/package-lock.json") or b"null")
            consistent = all(
                package.get(key, {}) == lock["packages"][""].get(key, {})
                for key in ("dependencies", "devDependencies")
            )
            add(
                "frontend.lock:" + web,
                "pass" if consistent else "fail",
                "Package manifest matches lock root."
                if consistent
                else "Package manifest and lock disagree.",
            )
        except (ValueError, TypeError, KeyError, AttributeError, UnicodeError, RecursionError):
            add("frontend.lock:" + web, "fail", "Package manifest or lock missing/invalid.")
    add(
        "security.secrets",
        "unverified",
        "Run the tracked-file security baseline; doctor never prints .env contents.",
    )
    add(
        "browser.inspection",
        "unverified",
        "Use the host browser-inspect skill for available console/network inspection.",
    )
    return findings, fixes, config


def dispatch(args):
    if args.approve and not args.fix:
        raise HarnessError("--approve requires --fix")
    if (args.api_url or args.web_url or args.compose_project) and not args.runtime:
        raise HarnessError("Runtime endpoint options require --runtime")
    project = args.project
    if project.name == "project.yaml":
        project = project.parent
    files = ProjectFiles(project)
    try:
        findings, fixes, config = inspect_project(files)
        if args.runtime and config:
            from harness.doctor_runtime import inspect_runtime

            findings += inspect_runtime(files, config, args)
        proposed = (
            [
                {"path": name, "operation": "restore-missing", "sha256": digest(data)}
                for name, data in sorted(fixes.items())
            ]
            if args.fix
            else []
        )
        applied = []
        if args.fix:
            print("Repair preview (missing files only): " + json.dumps(proposed), file=sys.stderr)
            if proposed and args.approve:
                # Journal the reviewed absent-file set; never back up or expose credentials.
                receipt = ".harness/doctor-backups/" + uuid.uuid4().hex + ".json"
                write_configuration(
                    files.root / receipt,
                    (
                        json.dumps(
                            {
                                "kind": "missing-file-restoration",
                                "before": "absent",
                                "files": proposed,
                            },
                            indent=2,
                        )
                        + "\n"
                    ).encode(),
                )
                for name, payload in sorted(fixes.items()):
                    if files.read(name) is not None:
                        raise HarnessError(
                            "Repair target changed after preview; nothing overwritten"
                        )
                    write_configuration(files.root / name, payload)
                    applied.append(name)
                findings, _, config = inspect_project(files)
                if args.runtime and config:
                    from harness.doctor_runtime import inspect_runtime

                    findings += inspect_runtime(files, config, args)
            elif proposed:
                print("Preview only. Review, then repeat with --fix --approve.", file=sys.stderr)
        counts = {
            status: sum(item.status == status for item in findings)
            for status in ("pass", "warn", "fail", "unverified")
        }
        report = {
            "schema_version": 1,
            "read_only": not bool(applied),
            "findings": [asdict(item) for item in findings],
            "counts": counts,
            "proposed_repairs": proposed,
            "applied_repairs": applied,
        }
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            for item in findings:
                print(f"[{item.status.upper()}] {item.id}: {item.message}")
                if item.action:
                    print("  " + item.action)
            print("Summary: " + ", ".join(f"{key}={value}" for key, value in counts.items()))
        return (
            1
            if counts["fail"]
            else 2
            if args.strict and (counts["warn"] or counts["unverified"])
            else 0
        )
    finally:
        files.close()
