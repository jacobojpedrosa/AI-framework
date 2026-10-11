"""Exercise every persistence variant on disposable local Docker services.

Each run owns its generated directory, Compose project and volumes. Cleanup
removes only these temporary volumes, even on failure. Logs remain in --report-dir.
"""

import argparse
import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from harness.config.models import ProjectConfig
from harness.scaffolding.fullstack import scaffold

VARIANTS = {
    "memory": ("memory", False, False),
    "sqlite": ("sqlite", False, False),
    "postgres": ("postgres", False, False),
    "vector": ("postgres", True, False),
    "redis": (None, False, True),
    "memory-redis": ("memory", False, True),
    "sqlite-redis": ("sqlite", False, True),
    "postgres-redis": ("postgres", False, True),
    "vector-redis": ("postgres", True, True),
}


def readiness(port: int) -> tuple[int, dict]:
    try:
        response = urlopen(f"http://127.0.0.1:{port}/api/readiness", timeout=15)
    except HTTPError as error:
        response = error
    with response:
        return response.status, json.load(response)


def verify(name: str, report_dir: Path, web_port: int, api_port: int) -> None:
    provider, vector, cache = VARIANTS[name]
    sql = provider in {"sqlite", "postgres"}
    data = {
        "schema_version": 1,
        "project": {"name": "persistence-smoke"},
        "architecture": {"golden_path": "fullstack-ai", "hexagonal_services": True},
        "apps": {"web": {"framework": "react"}},
        "services": {"api": {"framework": "fastapi"}},
    }
    if provider:
        data["database"] = {"provider": provider}
        if vector:
            data["database"]["vector"] = "pgvector"
    if cache:
        data["cache"] = {"provider": "redis"}
    env = dict(os.environ)
    for key in ("DATABASE_URL", "REDIS_URL", "COMPOSE_FILE", "COMPOSE_PROFILES"):
        env.pop(key, None)
    env.update(
        COMPOSE_PROJECT_NAME="harness-persistence-" + uuid.uuid4().hex[:12],
        WEB_PORT=str(web_port),
        API_PORT=str(api_port),
    )
    with tempfile.TemporaryDirectory(prefix="harness-persistence-") as temporary:
        destination = Path(temporary).resolve() / "sample"
        scaffold(ProjectConfig.model_validate(data), destination)
        with (report_dir / (name + ".log")).open("w") as log:

            def run(*command):
                subprocess.run(
                    command,
                    cwd=destination,
                    env=env,
                    check=True,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )

            def python(code):
                run("docker", "compose", "run", "--rm", "--no-deps", "api", "python", "-c", code)

            try:
                run("make", "up")
                status, _ = readiness(web_port)
                assert status == (503 if sql else 200), (name, status)
                if sql:
                    run("make", "migrate")
                    run("make", "migrate")
                for port in (api_port, web_port):
                    status, payload = readiness(port)
                    assert status == 200 and payload["status"] == "ready", (name, payload)
                run(
                    "docker", "compose", "run", "--rm", "--no-deps", "api", "python", "-m", "pytest"
                )
                if provider == "postgres" or cache:
                    run("make", "test-integration")
                run(
                    "docker",
                    "compose",
                    "run",
                    "--rm",
                    "--no-deps",
                    "api",
                    "python",
                    "-m",
                    "ruff",
                    "check",
                    ".",
                )
                run(
                    "docker",
                    "compose",
                    "run",
                    "--rm",
                    "--no-deps",
                    "api",
                    "python",
                    "-m",
                    "ruff",
                    "format",
                    "--check",
                    ".",
                )
                if sql:
                    setup = (
                        "from app.infrastructure.resources import create_resources; "
                        "from app.domain.records import Record; r=create_resources(); "
                    )
                    python(setup + "r.repository.put(Record('restart', 'kept')); r.close()")
                    run("make", "down")
                    run("make", "up")
                    python(
                        setup
                        + "assert r.repository.get('restart') == Record('restart', 'kept'); "
                        + "r.close()"
                    )
                    # Rollback checks only run on this script's isolated disposable databases.
                    run(
                        "docker",
                        "compose",
                        "run",
                        "--rm",
                        "--no-deps",
                        "api",
                        "python",
                        "-m",
                        "alembic",
                        "downgrade",
                        "base",
                    )
                    assert readiness(api_port)[0] == 503
                    run("make", "migrate")
                    assert readiness(api_port)[0] == 200
                log.write(
                    "\nPASS: contracts, readiness, migration lifecycle and cleanup boundary\n"
                )
            finally:
                run("docker", "compose", "down", "--volumes", "--remove-orphans")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=VARIANTS, action="append")
    parser.add_argument("--report-dir", type=Path, default=Path("output/persistence-verification"))
    parser.add_argument("--web-port", type=int, default=15173)
    parser.add_argument("--api-port", type=int, default=18080)
    args = parser.parse_args()
    args.report_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    for variant in args.variant or VARIANTS:
        print("Verifying " + variant, flush=True)
        try:
            verify(variant, args.report_dir, args.web_port, args.api_port)
            results[variant] = "passed"
        except Exception:
            results[variant] = "failed"
            raise
        finally:
            (args.report_dir / "results.json").write_text(json.dumps(results, indent=2) + "\n")
        print("Passed " + variant, flush=True)


if __name__ == "__main__":
    main()
