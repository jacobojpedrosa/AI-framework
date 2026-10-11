"""Generate and verify a disposable standalone stack; requires Docker and Make.

Run with the harness environment: python scripts/smoke_scaffold.py.
Only this run's uniquely named Compose project is removed, including on failure.
"""

import argparse
import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from urllib.request import urlopen

from harness.config.loader import load_project
from harness.scaffolding.fullstack import scaffold


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=root / "examples/specifications/fullstack-ai/expected-project.yaml",
    )
    parser.add_argument("--web-port", type=int, default=15173)
    parser.add_argument("--api-port", type=int, default=18080)
    args = parser.parse_args()
    config = load_project(args.config)
    env = dict(
        os.environ,
        COMPOSE_PROJECT_NAME="harness-smoke-" + uuid.uuid4().hex[:12],
        WEB_PORT=str(args.web_port),
        API_PORT=str(args.api_port),
    )
    with tempfile.TemporaryDirectory(prefix="harness-scaffold-") as temporary:
        destination = Path(temporary).resolve() / "sample"
        scaffold(config, destination)
        try:
            targets = ["up", "test", "lint", "build"]
            if config.database and config.database.provider in {"sqlite", "postgres"}:
                targets.insert(0, "migrate")
            if config.architecture.hexagonal_services:
                targets.append("test-contracts")
            if config.cache or (config.database and config.database.provider == "postgres"):
                targets.append("test-integration")
            subprocess.run(["make", *targets], cwd=destination, env=env, check=True)
            for port in (args.web_port, args.api_port):
                with urlopen(f"http://127.0.0.1:{port}/api/health", timeout=10) as response:
                    assert json.load(response) == {
                        "status": "ok",
                        "service": next(iter(config.services)),
                    }
                if config.architecture.hexagonal_services:
                    with urlopen(f"http://127.0.0.1:{port}/api/readiness", timeout=10) as response:
                        assert json.load(response)["status"] == "ready"
            print("Standalone stack and HTTP checks passed", flush=True)
        finally:
            subprocess.run(
                ["docker", "compose", "down", "--volumes", "--remove-orphans"],
                cwd=destination,
                env=env,
                check=True,
            )


if __name__ == "__main__":
    main()
