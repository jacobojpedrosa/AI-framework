"""Gate 10: execute the actual web SDK through Vite's proxy into an instrumented API.

Checks matching client/server trace and parent IDs, JSON logs, metrics and health.
Only uniquely named temporary Docker projects and their own volumes are removed.
"""

import argparse
import json
import os
import socket
import subprocess
import tempfile
import uuid
from pathlib import Path

from harness.config.models import ProjectConfig
from harness.scaffolding.fullstack import scaffold

WEB_REQUEST = """
import { checkApi } from './src/api.ts';
const original = globalThis.fetch;
globalThis.fetch = (url, options) => original('http://127.0.0.1:5173' + url, options);
const service = await checkApi();
if (service !== 'api') throw new Error('Unexpected service');
await new Promise(resolve => setTimeout(resolve, 50));
"""


def unused_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def verify(name, report_dir):
    data = {
        "schema_version": 1,
        "project": {"name": "telemetry-smoke"},
        "architecture": {"golden_path": "fullstack-ai", "hexagonal_services": True},
        "apps": {"web": {"framework": "react"}},
        "services": {"api": {"framework": "fastapi"}},
        "observability": {"provider": "opentelemetry"},
    }
    if name == "combined":
        data.update(
            database={"provider": "sqlite"},
            cache={"provider": "redis"},
            ai={"providers": ["fake", "openai", "gemini", "vertex"]},
            jobs={"enabled": True, "adapter": "taskiq", "broker": "redis"},
            scheduler={"enabled": True, "adapter": "taskiq", "store": "redis"},
            auth={"provider": "local", "authorization": "permissions"},
            admin={"enabled": True, "resources": ["schedules"]},
        )
    env = dict(os.environ)
    for key in list(env):
        if key.startswith(
            (
                "OTEL_",
                "TELEMETRY_",
                "AUTH_",
                "COMPOSE_",
                "JOBS_",
                "AI_",
                "OPENAI_",
                "GEMINI_",
                "VERTEX_",
                "GOOGLE_",
            )
        ):
            del env[key]
    for key in ("DATABASE_URL", "REDIS_URL"):
        env.pop(key, None)
    env.update(
        COMPOSE_PROJECT_NAME="harness-telemetry-" + uuid.uuid4().hex[:12],
        API_PORT=str(unused_port()),
        WEB_PORT=str(unused_port()),
        TELEMETRY_EXPORTER="console",
        OTEL_BSP_SCHEDULE_DELAY="100",
    )
    with tempfile.TemporaryDirectory(prefix="harness-telemetry-") as temporary:
        destination = Path(temporary).resolve() / "sample"
        scaffold(ProjectConfig.model_validate(data), destination)
        with (report_dir / (name + ".log")).open("w") as log:

            def run(*command, capture=False, check=True):
                result = subprocess.run(
                    ["docker", "compose", *command],
                    cwd=destination,
                    env=env,
                    check=check,
                    text=True,
                    stderr=log,
                    stdout=subprocess.PIPE if capture else log,
                )
                if capture:
                    log.write(result.stdout)
                    log.flush()
                return result

            try:
                run("up", "--build", "--detach", "--wait", "--wait-timeout", "120")
                if name == "combined":
                    run("exec", "-T", "api", "python", "-m", "app.infrastructure.migrate")
                test_env = (
                    [
                        "-e",
                        "TEST_REDIS_URL=redis://cache:6379/0",
                        "-e",
                        "TEST_JOBS_REDIS_URL=redis://jobs-redis:6379/0",
                    ]
                    if name == "combined"
                    else []
                )
                run("exec", "-T", *test_env, "api", "python", "-m", "pytest", "-q")
                run("exec", "-T", "api", "python", "-m", "ruff", "check", ".")
                run("exec", "-T", "api", "python", "-m", "ruff", "format", "--check", ".")
                run("exec", "-T", "web", "npm", "test")
                run("exec", "-T", "web", "npm", "run", "lint")
                run("exec", "-T", "web", "npm", "run", "build")
                response = run(
                    "exec",
                    "-T",
                    "web",
                    "node",
                    "--input-type=module",
                    "-e",
                    WEB_REQUEST,
                    capture=True,
                )
                client = next(
                    json.loads(line)
                    for line in response.stdout.splitlines()
                    if line.startswith('{"event":"web_span"')
                )
                # Graceful shutdown flushes spans and the final metric collection.
                run("stop", "api")
                logs = run("logs", "--no-log-prefix", "--no-color", "api", capture=True).stdout
                events = []
                for line in logs.splitlines():
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
                server = next(
                    item
                    for item in events
                    if item.get("kind") == "SpanKind.SERVER"
                    and item["context"]["trace_id"] == "0x" + client["trace_id"]
                )
                assert server["parent_id"] == "0x" + client["span_id"]
                assert server["attributes"]["http.route"] == "/api/health"
                request_log = next(
                    item
                    for item in events
                    if item.get("event") == "http_request"
                    and item["trace_id"] == client["trace_id"]
                )
                assert request_log["status"] == 200 and request_log["request_id"]
                assert any("resource_metrics" in item for item in events)
                proof = {
                    "variant": name,
                    "client": client,
                    "server": server,
                    "request_log": request_log,
                    "status": "passed",
                }
                (report_dir / (name + "-trace.json")).write_text(json.dumps(proof, indent=2) + "\n")
            finally:
                run("logs", "--tail", "20", check=False)
                run("down", "--volumes", "--remove-orphans")
    return {"variant": name, "status": "passed"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--variants", nargs="+", choices=["base", "combined"], default=["base", "combined"]
    )
    parser.add_argument("--reports", type=Path, default=Path("output/observability-verification"))
    args = parser.parse_args()
    args.reports.mkdir(parents=True, exist_ok=True)
    results = []
    for name in args.variants:
        results.append(verify(name, args.reports.resolve()))
        print("PASS " + name, flush=True)
    (args.reports / "results.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
