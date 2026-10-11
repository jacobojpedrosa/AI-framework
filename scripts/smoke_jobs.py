"""Gate 9 smoke: uniquely named temporary Docker projects, no cloud credentials.

Starts real worker and scheduler processes and removes only its test project volumes.
"""

import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import uuid
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener

from harness.config.models import ProjectConfig
from harness.scaffolding.fullstack import scaffold

WAIT_RESULT = """
import asyncio, json, sys
from app.infrastructure.taskiq_runtime import create_components
async def main():
    broker, queue, store = create_components()
    try:
        for _ in range(200):
            identifiers = [sys.argv[1]] if len(sys.argv) > 1 else []
            if not identifiers:
                for _, data in await store.client.xrange(broker.queue_name):
                    task = json.loads(data[b'data'])
                    if task['labels'].get('schedule_id') == 'heartbeat-default':
                        identifiers.append(task['task_id'])
            for identifier in identifiers:
                if await broker.result_backend.is_result_ready(identifier):
                    result = await broker.result_backend.get_result(identifier)
                    assert not result.is_err
                    print(json.dumps(result.return_value))
                    return
            await asyncio.sleep(.1)
        raise RuntimeError('Worker or scheduler did not produce a result')
    finally:
        await broker.shutdown()
        await store.client.aclose()
asyncio.run(main())
"""


def unused_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def verify(variant, reports):
    adapter = "memory" if variant == "memory" else "taskiq"
    data = {
        "schema_version": 1,
        "project": {"name": "jobs-smoke"},
        "architecture": {"golden_path": "fullstack-ai", "hexagonal_services": True},
        "apps": {"web": {"framework": "react"}},
        "services": {"api": {"framework": "fastapi"}},
        "jobs": {"enabled": True, "adapter": adapter},
        "scheduler": {"enabled": True, "adapter": adapter},
        "auth": {"provider": "local", "authorization": "permissions"},
        "admin": {"enabled": True, "resources": ["schedules"]},
    }
    if adapter == "taskiq":
        data["cache"] = {"provider": "redis"}
        data["jobs"]["broker"] = "redis"
        data["scheduler"]["store"] = "redis"
    if variant == "combined":
        data["ai"] = {"providers": ["fake", "openai", "gemini", "vertex"]}
        data["database"] = {"provider": "sqlite"}
    env = dict(os.environ)
    for key in list(env):
        if key.startswith(
            (
                "AUTH_",
                "OIDC_",
                "FIREBASE_",
                "JOBS_",
                "COMPOSE_",
                "AI_",
                "OPENAI_",
                "GEMINI_",
                "VERTEX_",
                "GOOGLE_",
            )
        ) or key in {"DATABASE_URL", "REDIS_URL", "TEST_REDIS_URL", "TEST_JOBS_REDIS_URL"}:
            del env[key]
    password = "synthetic-jobs-password"
    salt = "0123456789abcdef" * 2
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600_000).hex()
    port = unused_port()
    env.update(
        COMPOSE_PROJECT_NAME="harness-jobs-" + uuid.uuid4().hex[:12],
        API_PORT=str(port),
        WEB_PORT=str(unused_port()),
        AUTH_SESSION_SECRET=uuid.uuid4().hex * 2,
        AUTH_LOCAL_USERNAME="admin",
        AUTH_LOCAL_PASSWORD_HASH=f"pbkdf2_sha256:600000:{salt}:{digest}",
        AUTH_LOCAL_ROLES="admin",
        AUTH_COOKIE_SECURE="false",
        AUTH_LOCAL_PERMISSIONS="admin:access,schedules:read,schedules:write",
    )
    with tempfile.TemporaryDirectory(prefix="harness-jobs-") as temporary:
        destination = Path(temporary).resolve() / "sample"
        scaffold(ProjectConfig.model_validate(data), destination)
        with (reports / (variant + ".log")).open("w") as log:

            def run(*command, capture=False, check=True):
                result = subprocess.run(
                    command,
                    cwd=destination,
                    env=env,
                    check=check,
                    text=True,
                    stdout=subprocess.PIPE if capture else log,
                    stderr=log,
                )
                if capture:
                    log.write(result.stdout)
                    log.flush()
                return result

            def compose(*command, **kwargs):
                return run("docker", "compose", *command, **kwargs)

            def api(*command, **kwargs):
                return compose("exec", "-T", "api", *command, **kwargs)

            jar = CookieJar()
            opener = build_opener(HTTPCookieProcessor(jar))

            def http(path, data=None, headers=None):
                request = Request(
                    f"http://127.0.0.1:{port}" + path,
                    data=urlencode(data).encode() if data is not None else None,
                    headers=headers or {},
                )
                try:
                    response = opener.open(request, timeout=10)
                except HTTPError as error:
                    response = error
                with response:
                    return response.status, response.read().decode(), response.url

            try:
                targets = ["api"] + (["worker", "scheduler"] if adapter == "taskiq" else [])
                compose("up", "--build", "--detach", "--wait", "--wait-timeout", "120", *targets)
                if variant == "combined":
                    api("python", "-m", "app.infrastructure.migrate")
                status, body, url = http("/admin/schedules")
                assert status == 200 and url.endswith("/auth/login")
                token = re.search(r'name="csrf" value="([^"]+)"', body).group(1)
                assert (
                    http("/auth/login", {"username": "admin", "password": password, "csrf": token})[
                        0
                    ]
                    == 200
                )
                assert http("/admin/users")[0] == 404
                assert http("/admin/schedules")[0] == 200
                headers = {
                    "X-CSRFToken": next(
                        c.value for c in jar if c.name == "starlette_admin_csrftoken"
                    )
                }
                schedule = {"name": "heartbeat-default", "enabled": "true", "interval_seconds": "1"}
                assert http("/admin/schedules", schedule)[0] == 403
                assert http("/admin/schedules", schedule | {"job": "os.system"}, headers)[0] == 400
                listing = run(sys.executable, "-m", "harness", "jobs", "list", capture=True)
                assert json.loads(listing.stdout)["jobs"] == ["heartbeat"]
                result = run(
                    sys.executable, "-m", "harness", "jobs", "run", "heartbeat", capture=True
                )
                receipt = json.loads(result.stdout)
                if adapter == "taskiq":
                    result = api("python", "-c", WAIT_RESULT, receipt["task_id"], capture=True)
                    assert json.loads(result.stdout)["status"] == "ok"
                else:
                    assert receipt["status"] == "completed"
                assert http("/admin/schedules", schedule, headers)[0] == 200
                if adapter == "taskiq":
                    result = api("python", "-c", WAIT_RESULT, capture=True)
                    assert json.loads(result.stdout)["job"] == "heartbeat"
                result = run(sys.executable, "-m", "harness", "schedules", "list", capture=True)
                assert json.loads(result.stdout)["schedules"][0]["enabled"] == (adapter == "taskiq")
                schedule["enabled"] = "false"
                assert http("/admin/schedules", schedule, headers)[0] == 200
                test_env = (
                    [
                        "-e",
                        "TEST_REDIS_URL=redis://cache:6379/0",
                        "-e",
                        "TEST_JOBS_REDIS_URL=redis://jobs-redis:6379/0",
                    ]
                    if adapter == "taskiq"
                    else []
                )
                compose("exec", "-T", *test_env, "api", "python", "-m", "pytest", "-q")
                api("python", "-m", "ruff", "check", ".")
                api("python", "-m", "ruff", "format", "--check", ".")
                log.write(
                    "\nPASS: jobs CLI, worker consumption, schedules and authenticated management\n"
                )
            finally:
                compose("logs", "--tail", "80", check=False)
                compose("down", "--volumes", "--remove-orphans")
    return {"variant": variant, "status": "passed"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--variants",
        nargs="+",
        choices=["memory", "taskiq", "combined"],
        default=["memory", "taskiq", "combined"],
    )
    parser.add_argument("--reports", type=Path, default=Path("output/jobs-verification"))
    args = parser.parse_args()
    args.reports.mkdir(parents=True, exist_ok=True)
    results = []
    for variant in args.variants:
        results.append(verify(variant, args.reports.resolve()))
        print("PASS " + variant, flush=True)
    (args.reports / "results.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
