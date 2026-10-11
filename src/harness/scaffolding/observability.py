"""Optional vendor-neutral diagnostics and browser/API trace propagation."""

from importlib.resources import files

import yaml

from harness.config.models import ProjectConfig


def add_observability(config: ProjectConfig, rendered: dict[str, bytes], visit, api: str, web: str):
    templates = files("harness.templates")
    prefix = f"services/{api}/"
    visit(templates.joinpath("observability"), overlay=True)
    visit(templates.joinpath("observability_web"), overlay=True)
    for extension in ("in", "txt"):
        name = f"requirements-telemetry.{extension}"
        rendered[prefix + name] = templates.joinpath(
            "observability_locks", name + ".tmpl"
        ).read_bytes()
        for stem in ("requirements", "requirements-dev"):
            rendered[prefix + f"{stem}.{extension}"] += f"\n-r {name}\n".encode()
    for name in ("package.json", "package-lock.json"):
        rendered[f"apps/{web}/{name}"] = templates.joinpath(
            "observability_locks", name + ".tmpl"
        ).read_bytes()
    path = prefix + "Dockerfile"
    rendered[path] = (
        rendered[path]
        .replace(b"COPY requirements.txt ", b"COPY requirements.txt requirements-telemetry.txt ")
        .replace(
            b'"--port", "8000"]',
            b'"--port", "8000", "--no-access-log", "--log-config", '
            b'"app/infrastructure/logging.json"]',
        )
    )
    path = prefix + "app/infrastructure/bootstrap.py"
    text = rendered[path].decode()
    imports = [line for line in text.splitlines() if line.startswith("from app.infrastructure.")]
    new_import = "from app.infrastructure.telemetry import install_observability"
    if imports:
        start = text.index(imports[0])
        end = text.index(imports[-1]) + len(imports[-1])
        text = text[:start] + "\n".join(sorted([*imports, new_import])) + text[end:]
    else:
        marker = "from app.application.readiness import CheckReadiness\n"
        text = text.replace(marker, marker + new_import + "\n")
    rendered[path] = text.replace(
        "    return app", "    install_observability(app)\n    return app"
    ).encode()
    path = prefix + "pyproject.toml"
    if b"known-first-party" not in rendered[path]:
        rendered[path] += b'\n[tool.ruff.lint.isort]\nknown-first-party = ["app", "tests"]\n'
    path = f"apps/{web}/src/api.ts"
    rendered[path] = b'import { tracedHealthFetch } from "./telemetry.ts";\n\n' + rendered[
        path
    ].replace(b'fetch("/api/health", { signal })', b"tracedHealthFetch(signal)")
    compose = yaml.safe_load(rendered["compose.yaml"])
    compose["services"]["api"].setdefault("environment", {}).update(
        {
            "TELEMETRY_EXPORTER": "${TELEMETRY_EXPORTER:-console}",
            "TELEMETRY_SAMPLE_RATIO": "${TELEMETRY_SAMPLE_RATIO:-1}",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "${OTEL_EXPORTER_OTLP_ENDPOINT:-}",
            "OTEL_EXPORTER_OTLP_HEADERS": "${OTEL_EXPORTER_OTLP_HEADERS:-}",
        }
    )
    rendered["compose.yaml"] = yaml.safe_dump(compose, sort_keys=False).encode()
    rendered[".env.example"] += (
        b"\n# OTLP/HTTP supports any standards-compatible collector. No browser credentials.\n"
        b"TELEMETRY_EXPORTER=console\nTELEMETRY_SAMPLE_RATIO=1\n"
        b"OTEL_EXPORTER_OTLP_ENDPOINT=\nOTEL_EXPORTER_OTLP_HEADERS=\n"
    )
    rendered["README.md"] += (
        f"\n## Observability\n\nSee `services/{api}/OBSERVABILITY.md` for JSON logs, "
        "traces, metrics and OTLP. Health endpoints remain `/api/health` and `/api/readiness`.\n"
    ).encode()
