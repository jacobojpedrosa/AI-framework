"""Maintainer-only Python and browser OpenTelemetry lock generation."""

import argparse
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uv", default="uv")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    uv = str(Path(args.uv).resolve()) if "/" in args.uv else args.uv
    templates = root / "src/harness/templates"
    constraints = set()
    for group in ("fullstack_ai", "persistence_locks", "ai_locks", "auth_locks", "jobs_locks"):
        for path in (templates / group).rglob("requirements*.txt.tmpl"):
            constraints.update(re.findall(r"^([a-zA-Z0-9_.-]+==[^\s;]+)", path.read_text(), re.M))
    destination = templates / "observability_locks"
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="harness-telemetry-lock-") as temporary:
        work = Path(temporary)
        source = "opentelemetry-sdk==1.44.0\nopentelemetry-exporter-otlp-proto-http==1.44.0\n"
        (work / "requirements-telemetry.in").write_text(source)
        (destination / "requirements-telemetry.in.tmpl").write_text(source)
        (work / "constraints.txt").write_text("\n".join(sorted(constraints)) + "\n")
        subprocess.run(
            [
                uv,
                "pip",
                "compile",
                "requirements-telemetry.in",
                "--python-version",
                "3.12",
                "--universal",
                "--generate-hashes",
                "--no-header",
                "--no-annotate",
                "--constraint",
                "constraints.txt",
                "--output-file",
                "requirements-telemetry.txt",
            ],
            cwd=work,
            check=True,
            stdout=subprocess.DEVNULL,
            env=dict(os.environ, UV_CACHE_DIR=str(root / ".uv-cache")),
        )
        (destination / "requirements-telemetry.txt.tmpl").write_bytes(
            (work / "requirements-telemetry.txt").read_bytes()
        )
        web = templates / "fullstack_ai/apps/__WEB__"
        package = json.loads((web / "package.json.tmpl").read_text())
        package["dependencies"].update(
            {"@opentelemetry/api": "1.9.1", "@opentelemetry/sdk-trace-base": "2.11.0"}
        )
        (work / "package.json").write_text(json.dumps(package, indent=2) + "\n")
        (work / "package-lock.json").write_bytes((web / "package-lock.json.tmpl").read_bytes())
        subprocess.run(
            [
                "npm",
                "install",
                "--package-lock-only",
                "--ignore-scripts",
                "--no-audit",
                "--no-fund",
            ],
            cwd=work,
            check=True,
        )
        for name in ("package.json", "package-lock.json"):
            (destination / (name + ".tmpl")).write_bytes((work / name).read_bytes())


if __name__ == "__main__":
    main()
