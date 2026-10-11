"""Generate provider-specific Actions with isolated validation and deployment permissions."""

import json
from importlib.resources import files

import yaml

from harness.config.models import ProjectConfig

ACTIONS = {
    "checkout": "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
    "python": "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97",
    "node": "actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1",
    "terraform": "hashicorp/setup-terraform@dfe3c3f87815947d99a8997f908cb6525fc44e9e",
    "gcp_auth": "google-github-actions/auth@7c6bc770dae815cd3e89ee6cdf493a5fab2cc093",
    "gcloud": "google-github-actions/setup-gcloud@aa5489c8933f4cc7a4f7d45035b3b1440c9c10db",
    "azure_auth": "azure/login@a641126d1b8aa4d1fa005f4f92df94a3a4c4c906",
}


def checkout():
    return {"uses": ACTIONS["checkout"], "with": {"persist-credentials": False}}


def add_cicd(config: ProjectConfig, rendered: dict[str, bytes], api: str, web: str) -> None:
    provider = config.cloud.provider if config.cloud else "local"
    steps = [
        checkout(),
        {"uses": ACTIONS["python"], "with": {"python-version": "3.12.13"}},
        {"uses": ACTIONS["node"], "with": {"node-version": "24.2.0"}},
        {
            "name": "API dependencies",
            "working-directory": f"services/{api}",
            "run": "python -m pip install --require-hashes -r requirements-dev.txt",
        },
        {
            "name": "API lint and tests (including contracts)",
            "working-directory": f"services/{api}",
            "env": {"TELEMETRY_EXPORTER": "none"},
            "run": "python -m ruff check .\npython -m ruff format --check .\npython -m pytest",
        },
        {
            "name": "Web lint, tests and build",
            "working-directory": f"apps/{web}",
            "run": "npm ci --ignore-scripts --no-audit --no-fund\n"
            "npm run lint\nnpm test\nnpm run build",
        },
        {"name": "Tracked secret baseline", "run": "python .github/scripts/security.py"},
        {
            "name": "Python dependency audit",
            "run": "python -m venv /tmp/harness-audit\n"
            "/tmp/harness-audit/bin/pip install --require-hashes "
            "-r .github/requirements-security.txt\n"
            f"cd services/{api}\n"
            "/tmp/harness-audit/bin/pip-audit --disable-pip --no-deps -r requirements.txt",
        },
        {
            "name": "Web dependency audit",
            "working-directory": f"apps/{web}",
            "run": "npm audit --audit-level=high",
        },
        {"name": "Build containers", "run": "docker compose build"},
    ]
    if provider != "local":
        steps.extend(
            [
                {
                    "uses": ACTIONS["terraform"],
                    "with": {"terraform_version": "1.15.8", "terraform_wrapper": False},
                },
                {
                    "name": "Terraform schema and mock plans",
                    "run": f"terraform fmt -check -recursive infra/{provider}\n"
                    f"for module in bootstrap service; do\n"
                    f"  terraform -chdir=infra/{provider}/$module init "
                    "-backend=false -input=false -lockfile=readonly\n"
                    f"  terraform -chdir=infra/{provider}/$module validate\n"
                    f"  terraform -chdir=infra/{provider}/$module test\n"
                    "done",
                },
                {
                    "name": "Build cloud image",
                    "run": "docker build --platform linux/amd64 -f Dockerfile.cloud "
                    "-t harness-cloud:ci .",
                },
            ]
        )
    validate = {"runs-on": "ubuntu-24.04", "timeout-minutes": 30, "steps": steps}
    ci = {
        "name": "Validate and DEV",
        "on": {"pull_request": {}, "push": {"branches": ["develop", "main"]}},
        "permissions": {"contents": "read"},
        "jobs": {"validate": validate},
    }
    if provider != "local":
        if provider == "azure":
            ci["jobs"]["publish-dev"] = deployment(provider, "dev", publish=True)
        ci["jobs"]["deploy-dev"] = deployment(provider, "dev")
        prod = {
            "name": "Manual production deployment",
            "on": {
                "workflow_dispatch": {
                    "inputs": {
                        "image_digest": {
                            "description": "Reviewed PROD registry digest (sha256:...)",
                            "required": True,
                            "type": "string",
                        }
                    }
                }
            },
            "permissions": {"contents": "read"},
            "jobs": {"validate": validate, "deploy-prod": deployment(provider, "prod")},
        }
        rendered[".github/workflows/production.yml"] = yaml.safe_dump(
            prod, sort_keys=False
        ).encode()
    rendered[".github/workflows/ci.yml"] = yaml.safe_dump(ci, sort_keys=False).encode()
    rendered[".github/actionlint.yaml"] = (
        b"self-hosted-runner:\n  labels:\n    - harness-azure-internal\n"
    )
    for name in ("security.py", "deploy.py", "guard.py"):
        if provider == "local" and name != "security.py":
            continue
        rendered[f".github/scripts/{name}"] = (
            files("harness.templates").joinpath(f"cicd/{name}.tmpl").read_bytes()
        )
    rendered[".github/requirements-security.txt"] = (
        files("harness.templates").joinpath("cicd/requirements-security.txt.tmpl").read_bytes()
    )
    rendered[".github/action-pins.json"] = (json.dumps(ACTIONS, indent=2) + "\n").encode()
    rendered["CI_CD.md"] = files("harness.templates").joinpath("cicd/CI_CD.md.tmpl").read_bytes()
    rendered[".gitignore"] += b"\ngha-creds-*.json\n"
    if ".dockerignore" in rendered:
        rendered[".dockerignore"] += b"\ngha-creds-*.json\n.github/\n"
    rendered["README.md"] += b"\nGitHub Actions validation and deployment setup: CI_CD.md.\n"


def deployment(provider: str, stage: str, *, publish: bool = False) -> dict:
    prod = stage == "prod"
    event = "workflow_dispatch" if prod else "push"
    branch = "main" if prod else "develop"
    env = {
        "DEPLOY_PROVIDER": provider,
        "DEPLOY_STAGE": stage,
        "IMAGE_REPOSITORY": "${{ vars.IMAGE_REPOSITORY }}",
        "DEPLOY_SERVICE": "${{ vars.DEPLOY_SERVICE }}",
        "GCP_PROJECT": "${{ vars.GCP_PROJECT }}",
        "GCP_REGION": "${{ vars.GCP_REGION }}",
        "GCP_SERVICE_ACCOUNT": "${{ vars.GCP_SERVICE_ACCOUNT }}",
        "AZURE_SUBSCRIPTION_ID": "${{ vars.AZURE_SUBSCRIPTION_ID }}",
        "AZURE_RESOURCE_GROUP": "${{ vars.AZURE_RESOURCE_GROUP }}",
        "AZURE_REGISTRY_NAME": "${{ vars.AZURE_REGISTRY_NAME }}",
        "IMAGE_DIGEST": (
            "${{ inputs.image_digest }}"
            if prod
            else "${{ needs.publish-dev.outputs.image_digest }}"
            if provider == "azure" and not publish
            else ""
        ),
    }
    steps = [
        checkout(),
        {"uses": ACTIONS["python"], "with": {"python-version": "3.12.13"}},
        {
            "name": "Check event, inputs and environment protection",
            "env": {"ENVIRONMENT_READ_TOKEN": "${{ secrets.ENVIRONMENT_READ_TOKEN }}"},
            "run": "python .github/scripts/guard.py",
        },
    ]
    if not prod and (provider == "gcp" or publish):
        steps.append(
            {
                "name": "Build reviewed commit",
                "run": "docker build --platform linux/amd64 -f Dockerfile.cloud "
                "-t harness-release:ci .",
            }
        )
    if provider == "gcp":
        steps.extend(
            [
                {
                    "uses": ACTIONS["gcp_auth"],
                    "with": {
                        "project_id": "${{ vars.GCP_PROJECT }}",
                        "workload_identity_provider": "${{ vars.GCP_WORKLOAD_IDENTITY_PROVIDER }}",
                        "service_account": "${{ vars.GCP_SERVICE_ACCOUNT }}",
                    },
                },
                {"uses": ACTIONS["gcloud"]},
            ]
        )
    else:
        steps.append(
            {
                "uses": ACTIONS["azure_auth"],
                "with": {
                    "client-id": "${{ vars.AZURE_CLIENT_ID }}",
                    "tenant-id": "${{ vars.AZURE_TENANT_ID }}",
                    "subscription-id": "${{ vars.AZURE_SUBSCRIPTION_ID }}",
                },
            }
        )
    steps.append(
        {
            "name": "Publish, deploy digest and verify health",
            "id": "release",
            "run": "python .github/scripts/deploy.py" + (" --publish" if publish else ""),
        }
    )
    job = {
        "needs": ["validate", "publish-dev"]
        if provider == "azure" and not prod and not publish
        else ["validate"],
        "if": f"github.event_name == '{event}' && github.ref == 'refs/heads/{branch}' "
        f"&& vars.{stage.upper()}_DEPLOY_ENABLED == 'true'",
        "runs-on": ["self-hosted", "linux", "x64", "harness-azure-internal"]
        if provider == "azure" and not publish
        else "ubuntu-24.04",
        "environment": stage,
        "permissions": {"contents": "read", "id-token": "write"},
        "concurrency": {
            "group": f"publish-{stage}" if publish else f"deploy-{stage}",
            "cancel-in-progress": False,
        },
        "timeout-minutes": 30,
        "env": env,
        "steps": steps,
    }
    if publish:
        job["outputs"] = {"image_digest": "${{ steps.release.outputs.image_digest }}"}
    return job
