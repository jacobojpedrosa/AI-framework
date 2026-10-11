"""Generate a prototype and verify real Docker web/API and Chromium flows.

Requires Docker, Node/npm and browser download access. Uses a new output directory
and removes only its uniquely named Compose stack.
"""

import argparse
import json
import os
import socket
import subprocess
import uuid
from pathlib import Path

from harness.product import definition_files, load_product
from harness.prototype import render_prototype
from harness.scaffolding.fullstack import write_project


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return str(sock.getsockname()[1])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    source = root / "examples/product-design/feedback.yaml"
    project = args.output.absolute()
    product = load_product(source)
    write_project(render_prototype(product, source), project)
    write_project(definition_files(product, source), project / ".harness/design-review")
    web = project / "apps/web"
    evidence = project / ".harness/verification"
    evidence.mkdir()
    name = "harness-prototype-" + uuid.uuid4().hex[:10]
    api_port, web_port = free_port(), free_port()
    while web_port == api_port:
        web_port = free_port()
    env = dict(
        os.environ,
        API_PORT=api_port,
        WEB_PORT=web_port,
        COMPOSE_PROJECT_NAME=name,
        E2E_BASE_URL=f"http://127.0.0.1:{web_port}",
        PLAYWRIGHT_BROWSERS_PATH=str(root / ".tools/playwright-1.64.0"),
    )
    compose = ["docker", "compose", "-p", name]
    completed = []

    def run(label, command, cwd=project, timeout=600):
        print(label, flush=True)
        with (evidence / f"{label}.log").open("w") as log:
            subprocess.run(
                command,
                cwd=cwd,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                check=True,
                timeout=timeout,
            )
        completed.append(label)

    try:
        run("up", [*compose, "up", "--build", "--detach", "--wait", "--wait-timeout", "120"])
        run("api-tests", [*compose, "exec", "-T", "api", "python", "-m", "pytest", "-q"])
        run("api-lint", [*compose, "exec", "-T", "api", "python", "-m", "ruff", "check", "."])
        run(
            "api-format",
            [*compose, "exec", "-T", "api", "python", "-m", "ruff", "format", "--check", "."],
        )
        run(
            "web-install",
            [
                "npm",
                "ci",
                "--ignore-scripts",
                "--no-audit",
                "--no-fund",
                "--cache",
                str(root / ".tools/npm-cache"),
            ],
            web,
        )
        for action in ("test", "lint", "build"):
            run("web-" + action, ["npm", "run", action], web)
        run("browser-install", ["npx", "--no-install", "playwright", "install", "chromium"], web)
        run("browser-tests", ["npm", "run", "test:e2e"], web)
        capture = """
import { chromium } from '@playwright/test';
const browser = await chromium.launch();
const views = [['desktop', {width:1440,height:1000}], ['mobile',{width:390,height:844}]];
for (const [name, viewport] of views) {
  const page = await browser.newPage({viewport});
  await page.goto(process.env.E2E_BASE_URL);
  await page.getByRole('heading', {name:'All feedback', exact:true}).waitFor();
  await page.getByRole('status').waitFor({state:'detached'});
  await page.screenshot({path:'../../.harness/verification/' + name + '.png', fullPage:true});
  await page.close();
}
await browser.close();
"""
        run("reset-api", [*compose, "restart", "api"])
        run("ready", [*compose, "up", "--detach", "--wait", "--wait-timeout", "60"])
        run("screenshots", ["node", "--input-type=module", "-e", capture], web)
        result = {
            "status": "passed",
            "checks": completed,
            "compose_project": name,
            "browser": "Playwright 1.64.0 Chromium desktop and mobile emulation",
            "screenshots": ["desktop.png", "mobile.png"],
        }
        (evidence / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    finally:
        run("down", [*compose, "down", "--remove-orphans"], timeout=120)
    print(f"Prototype verified; evidence in {evidence}")


if __name__ == "__main__":
    main()
