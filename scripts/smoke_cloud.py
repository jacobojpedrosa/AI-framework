"""Verify generated Terraform and the shared cloud container without cloud writes.

Plans use an empty local state, a fictitious project, an invalid token and a dead
HTTP proxy. This proves local planning/schema behavior, not GCP deployment access.
Azure uses mock-provider plan tests because real Azure plans require authentication.
"""

import argparse
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from harness.config.loader import load_project
from harness.scaffolding.fullstack import scaffold


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--terraform", default="terraform")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--provider", choices=("gcp", "azure"), default="gcp")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    terraform = str(Path(args.terraform).absolute()) if "/" in args.terraform else args.terraform
    project = args.output.absolute()
    example = "cloud-azure" if args.provider == "azure" else "cloud"
    scaffold(load_project(root / f"examples/{example}/project.yaml"), project)
    evidence = project / ".harness/cloud-verification"
    evidence.mkdir()
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(
            ("GOOGLE_", "GCLOUD_", "CLOUDSDK_", "ARM_", "AZURE_", "TF_VAR_", "TF_CLI_ARGS")
        )
    }
    cache = root / ".tools/terraform-plugins"
    cache.mkdir(exist_ok=True)
    env.update(CHECKPOINT_DISABLE="1", TF_IN_AUTOMATION="1", TF_PLUGIN_CACHE_DIR=str(cache))
    offline = dict(
        env,
        GOOGLE_OAUTH_ACCESS_TOKEN="harness-offline-plan-not-valid",
        HTTPS_PROXY="http://127.0.0.1:9",
        HTTP_PROXY="http://127.0.0.1:9",
        ALL_PROXY="http://127.0.0.1:9",
        NO_PROXY="",
    )
    checks = []

    def run(label, command, cwd=project, command_env=env, allowed=(0,), timeout=600):
        print(label, flush=True)
        result = subprocess.run(
            command,
            cwd=cwd,
            env=command_env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            timeout=timeout,
        )
        (evidence / f"{label}.log").write_text(result.stdout)
        if result.returncode not in allowed:
            raise RuntimeError(f"{label} failed; inspect its log")
        checks.append(label)
        return result.stdout

    version = json.loads(run("terraform-version", [terraform, "version", "-json"]))
    assert version["terraform_version"] == "1.15.8"
    for name in ("bootstrap", "service"):
        directory = project / f"infra/{args.provider}" / name
        run(name + "-fmt", [terraform, "fmt", "-check", "-recursive"], directory)
        run(
            name + "-init",
            [terraform, "init", "-backend=false", "-input=false", "-lockfile=readonly"],
            directory,
        )
        run(name + "-validate", [terraform, "validate", "-no-color"], directory, offline)
        if args.provider == "azure":
            run(
                name + "-mock-plans",
                [terraform, "test", "-no-color", "-verbose"],
                directory,
                offline,
            )
            continue
        run(
            name + "-plan",
            [
                terraform,
                "plan",
                "-input=false",
                "-refresh=false",
                "-lock=false",
                "-no-color",
                "-detailed-exitcode",
                "-var-file=dev.tfvars.example",
                "-out=validation.tfplan",
            ],
            directory,
            offline,
            allowed=(2,),
        )
        planned = json.loads(
            run(
                name + "-plan-json",
                [terraform, "show", "-json", "validation.tfplan"],
                directory,
                offline,
            )
        )
        changes = planned["resource_changes"]
        assert len(changes) == (4 if name == "bootstrap" else 2)
        assert all(change["change"]["actions"] == ["create"] for change in changes)
        if name == "service":
            service = next(
                change["change"]["after"]
                for change in changes
                if change["type"] == "google_cloud_run_v2_service"
            )
            assert service["invoker_iam_disabled"] is False
            assert service["template"][0]["scaling"][0]["max_instance_count"] == 2
            run("terraform-tests", [terraform, "test", "-no-color"], directory, offline)
        # Never leave a saved synthetic plan for somebody to apply by mistake.
        (directory / "validation.tfplan").unlink()
    name = "harness-cloud-" + uuid.uuid4().hex[:10]
    image = name + ":verification"
    run(
        "image-build",
        [
            "docker",
            "build",
            "--platform",
            "linux/amd64",
            "-f",
            "Dockerfile.cloud",
            "-t",
            image,
            ".",
        ],
        timeout=1200,
    )
    inspect = json.loads(run("image-inspect", ["docker", "image", "inspect", image]))[0]
    assert inspect["Architecture"] == "amd64"
    assert inspect["Config"]["User"] == "app"
    try:
        # A non-default PORT proves the entrypoint honors the runtime contract.
        run(
            "container-start",
            [
                "docker",
                "run",
                "--platform",
                "linux/amd64",
                "--detach",
                "--name",
                name,
                "--read-only",
                "--tmpfs",
                "/tmp",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "-e",
                "PORT=8091",
                "-p",
                "127.0.0.1::8091",
                image,
            ],
        )
        port = run("container-port", ["docker", "port", name, "8091/tcp"]).strip().rsplit(":", 1)[1]
        url = f"http://127.0.0.1:{port}"
        for attempt in range(60):
            try:
                with urllib.request.urlopen(url + "/api/readiness", timeout=2) as response:
                    assert response.status == 200
                break
            except (OSError, urllib.error.URLError):
                if attempt == 59:
                    raise
                time.sleep(1)
        with urllib.request.urlopen(url + "/api/health", timeout=3) as response:
            assert json.load(response)["status"] == "ok"
        with urllib.request.urlopen(url, timeout=3) as response:
            html = response.read().decode()
        assets = re.findall(r'(?:src|href)="(/assets/[^"]+)"', html)
        assert assets and "/src/main.tsx" not in html
        for asset in assets:
            with urllib.request.urlopen(url + asset, timeout=3) as response:
                assert response.status == 200
        with urllib.request.urlopen(url + "/api/openapi.json", timeout=3) as response:
            assert "/api/health" in json.load(response)["paths"]
        run("container-stop", ["docker", "stop", "--time", "10", name])
        logs = run("container-logs", ["docker", "logs", name])
        assert '"trace_id"' in logs
        assert '"http_request"' in logs
        (evidence / "results.json").write_text(
            json.dumps(
                {
                    "status": "passed",
                    "checks": checks,
                    "terraform": "1.15.8",
                    "provider": args.provider,
                    "provider_version": "5.9.0" if args.provider == "azure" else "8.6.0",
                    "plan_scope": (
                        "mock Azure provider plan tests; no authenticated plan"
                        if args.provider == "azure"
                        else "empty local state, invalid token, fictitious project, dead HTTP proxy"
                    ),
                    "cloud_deployed": False,
                    "container": "linux/amd64 non-root read-only, PORT=8091",
                    "served_assets": assets,
                },
                indent=2,
            )
            + "\n"
        )
    finally:
        run("container-remove", ["docker", "rm", "-f", name], allowed=(0, 1))
    print(f"Cloud path checked without cloud writes; evidence: {evidence}")


if __name__ == "__main__":
    main()
