"""HTTP end-to-end check of the current candidate, using a disposable Compose stack."""

import json
import os
import socket
import subprocess
import uuid
from urllib.request import urlopen


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return str(sock.getsockname()[1])


def main():
    web, api = free_port(), free_port()
    while api == web:
        api = free_port()
    env = dict(os.environ, WEB_PORT=web, API_PORT=api)
    compose = ["docker", "compose", "-p", "harness-update-e2e-" + uuid.uuid4().hex[:10]]
    try:
        subprocess.run(
            [*compose, "up", "--detach", "--wait", "--wait-timeout", "120"],
            env=env,
            check=True,
            timeout=180,
        )
        for port in (web, api):
            for endpoint, status in (("health", "ok"), ("readiness", "ready")):
                with urlopen(f"http://127.0.0.1:{port}/api/{endpoint}", timeout=10) as response:
                    assert json.load(response)["status"] == status
        with urlopen(f"http://127.0.0.1:{web}/", timeout=10) as response:
            assert b'<div id="root">' in response.read()
    finally:
        subprocess.run(
            [*compose, "down", "--volumes", "--remove-orphans"], env=env, check=True, timeout=90
        )


if __name__ == "__main__":
    main()
