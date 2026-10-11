"""Verify SDK adapters offline in generated Docker projects; never calls model APIs.

Only dependency installation uses the network. Synthetic HTTP transports handle
all provider tests. Unique test projects and their volumes are removed in finally.
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
    "fake": ["fake"],
    "openai": ["openai"],
    "gemini": ["gemini"],
    "vertex": ["vertex"],
    "all": ["fake", "openai", "gemini", "vertex"],
    "all-persistence": ["fake", "openai", "gemini", "vertex"],
}


def verify(name, report_dir, web_port, api_port):
    providers = VARIANTS[name]
    data = {
        "schema_version": 1,
        "project": {"name": "ai-smoke"},
        "architecture": {"golden_path": "fullstack-ai", "hexagonal_services": True},
        "apps": {"web": {"framework": "react"}},
        "services": {"api": {"framework": "fastapi"}},
        "ai": {"providers": providers},
    }
    if name == "all-persistence":
        data.update(
            database={"provider": "postgres", "vector": "pgvector"}, cache={"provider": "redis"}
        )
    env = dict(os.environ)
    for key in (
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "OPENAI_MODEL",
        "GEMINI_MODEL",
        "VERTEX_MODEL",
        "AI_PROVIDER",
        "GOOGLE_API_KEY",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_LOCATION",
        "DATABASE_URL",
        "REDIS_URL",
        "COMPOSE_FILE",
        "COMPOSE_PROFILES",
    ):
        env.pop(key, None)
    env.update(
        COMPOSE_PROJECT_NAME="harness-ai-" + uuid.uuid4().hex[:12],
        WEB_PORT=str(web_port),
        API_PORT=str(api_port),
    )
    with tempfile.TemporaryDirectory(prefix="harness-ai-") as temporary:
        destination = Path(temporary).resolve() / "sample"
        scaffold(ProjectConfig.model_validate(data), destination)
        with (report_dir / (name + ".log")).open("w") as log:

            def run(*command, check=True, capture=False, input=None):
                return subprocess.run(
                    command,
                    cwd=destination,
                    env=env,
                    check=check,
                    stdout=subprocess.PIPE if capture else log,
                    stderr=log,
                    text=True,
                    input=input,
                )

            try:
                if name == "all-persistence":
                    run("make", "migrate")
                run("make", "up")
                for port in (web_port, api_port):
                    try:
                        response = urlopen(f"http://127.0.0.1:{port}/api/readiness", timeout=10)
                    except HTTPError as error:
                        response = error
                    with response:
                        assert response.status == (200 if "fake" in providers else 503)
                        payload = json.load(response)
                        assert {
                            "name": "ai_configuration",
                            "available": "fake" in providers,
                        } in payload["checks"]
                run("make", "test", "lint")
                if name == "all-persistence":
                    run("make", "test-integration", "build")
                result = run(
                    "docker",
                    "compose",
                    "run",
                    "--rm",
                    "--no-deps",
                    "-T",
                    "api",
                    "python",
                    "-m",
                    "app.infrastructure.ai_cli",
                    "check",
                    check=False,
                    capture=True,
                )
                assert result.returncode == (0 if "fake" in providers else 1)
                if "fake" in providers:
                    result = run(
                        "docker",
                        "compose",
                        "run",
                        "--rm",
                        "--no-deps",
                        "-T",
                        "api",
                        "python",
                        "-m",
                        "app.infrastructure.ai_cli",
                        "generate",
                        capture=True,
                        input="test input",
                    )
                    assert json.loads(result.stdout)["text"] == "Fake response."
                log.write(
                    "\nPASS: SDK contracts and local diagnostics; no real provider requests\n"
                )
            finally:
                run("docker", "compose", "down", "--volumes", "--remove-orphans")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=VARIANTS, action="append")
    parser.add_argument("--report-dir", type=Path, default=Path("output/ai-verification"))
    parser.add_argument("--web-port", type=int, default=15173)
    parser.add_argument("--api-port", type=int, default=18080)
    args = parser.parse_args()
    args.report_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    for name in args.variant or VARIANTS:
        print("Verifying " + name, flush=True)
        try:
            verify(name, args.report_dir, args.web_port, args.api_port)
            results[name] = "passed"
        except Exception:
            results[name] = "failed"
            raise
        finally:
            (args.report_dir / "results.json").write_text(json.dumps(results, indent=2) + "\n")
        print("Passed " + name, flush=True)


if __name__ == "__main__":
    main()
