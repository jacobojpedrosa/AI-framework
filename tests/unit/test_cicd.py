import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest
import yaml

from harness.config.loader import load_project
from harness.scaffolding.fullstack import render_project


@pytest.fixture
def helper_modules(tmp_path, repo_root, monkeypatch):
    folder = repo_root / "src/harness/templates/cicd"
    modules = {}
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in ("deploy", "guard", "security"):
        path = tmp_path / (name + ".py")
        path.write_bytes((folder / (name + ".py.tmpl")).read_bytes())
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
        modules[name] = module
    return modules


@pytest.mark.parametrize("provider", ["local", "gcp", "azure"])
def test_workflow_triggers_permissions_and_pins(repo_root, provider):
    config = load_project(repo_root / "examples/cloud/project.yaml")
    if provider == "local":
        config = config.model_copy(update={"cloud": None, "iac": None})
    elif provider == "azure":
        config = load_project(repo_root / "examples/cloud-azure/project.yaml")
    rendered = render_project(config)
    ci = yaml.safe_load(rendered[".github/workflows/ci.yml"])
    assert set(ci["on"]) == {"pull_request", "push"}
    assert ci["on"]["push"]["branches"] == ["develop", "main"]
    assert ci["permissions"] == {"contents": "read"}
    assert "id-token" not in ci["jobs"]["validate"].get("permissions", {})
    assert ci["jobs"]["validate"]["runs-on"] == "ubuntu-24.04"
    for job in ci["jobs"].values():
        for step in job["steps"]:
            if "uses" in step:
                assert re.fullmatch(r"[A-Za-z0-9_/-]+@[a-f0-9]{40}", step["uses"])
            if step.get("uses", "").startswith("actions/checkout@"):
                assert step["with"]["persist-credentials"] is False
    if provider == "local":
        assert set(ci["jobs"]) == {"validate"}
        assert ".github/workflows/production.yml" not in rendered
        return
    dev = ci["jobs"]["deploy-dev"]
    assert dev["needs"] == (["validate", "publish-dev"] if provider == "azure" else ["validate"])
    if provider == "azure":
        publisher = ci["jobs"]["publish-dev"]
        assert publisher["runs-on"] == "ubuntu-24.04"
        assert "--publish" in publisher["steps"][-1]["run"]
        assert "needs.publish-dev.outputs.image_digest" in dev["env"]["IMAGE_DIGEST"]
        assert not any("docker build" in step.get("run", "") for step in dev["steps"])
    assert "github.event_name == 'push'" in dev["if"]
    assert "refs/heads/develop" in dev["if"]
    assert "DEV_DEPLOY_ENABLED == 'true'" in dev["if"]
    prod = yaml.safe_load(rendered[".github/workflows/production.yml"])
    assert set(prod["on"]) == {"workflow_dispatch"}
    job = prod["jobs"]["deploy-prod"]
    assert "github.event_name == 'workflow_dispatch'" in job["if"]
    assert "refs/heads/main" in job["if"]
    assert job["environment"] == "prod"
    assert job["concurrency"]["cancel-in-progress"] is False
    assert job["permissions"] == {"contents": "read", "id-token": "write"}
    assert not any(step.get("name") == "Build reviewed commit" for step in job["steps"])
    guard = next(i for i, s in enumerate(job["steps"]) if "guard.py" in s.get("run", ""))
    auth = next(
        i
        for i, s in enumerate(job["steps"])
        if any(
            s.get("uses", "").startswith(prefix)
            for prefix in ("azure/login@", "google-github-actions/auth@")
        )
    )
    assert guard < auth
    assert job["runs-on"] == (
        ["self-hosted", "linux", "x64", "harness-azure-internal"]
        if provider == "azure"
        else "ubuntu-24.04"
    )
    assert b"gha-creds-*.json" in rendered[".dockerignore"]


@pytest.mark.parametrize(
    "event,ref,stage,accepted",
    [
        ("push", "refs/heads/develop", "dev", True),
        ("push", "refs/heads/main", "prod", False),
        ("pull_request", "refs/heads/develop", "dev", False),
        ("workflow_dispatch", "refs/heads/develop", "prod", False),
        ("workflow_dispatch", "refs/heads/main", "prod", True),
    ],
)
def test_event_guard(helper_modules, event, ref, stage, accepted):
    env = {
        "GITHUB_EVENT_NAME": event,
        "GITHUB_REF": ref,
        "DEPLOY_STAGE": stage,
        "IMAGE_DIGEST": "sha256:" + "a" * 64,
    }
    if accepted:
        helper_modules["guard"].check_event(env)
    else:
        with pytest.raises(ValueError):
            helper_modules["guard"].check_event(env)


def test_production_protection_is_fail_closed(helper_modules):
    guard = helper_modules["guard"]
    doc = {
        "can_admins_bypass": False,
        "protection_rules": [
            {"type": "required_reviewers", "prevent_self_review": True, "reviewers": [{"id": 1}]}
        ],
        "deployment_branch_policy": {"custom_branch_policies": True, "protected_branches": False},
    }
    policies = {"branch_policies": [{"name": "main", "type": "branch"}]}
    assert guard.protected_environment(doc, policies)
    for key in doc:
        broken = dict(doc)
        del broken[key]
        assert not guard.protected_environment(broken, policies)
    assert not guard.protected_environment(
        doc, {"branch_policies": [{"name": "*", "type": "branch"}]}
    )
    doc["protection_rules"][0]["prevent_self_review"] = False
    assert not guard.protected_environment(doc, policies)


@pytest.mark.parametrize("provider", ["gcp", "azure"])
def test_deploy_commands_are_explicit_and_reject_mutable_images(helper_modules, provider):
    deploy = helper_modules["deploy"]
    env = {
        "DEPLOY_PROVIDER": provider,
        "DEPLOY_STAGE": "dev",
        "DEPLOY_SERVICE": "app-dev",
        "GCP_PROJECT": "harness-example",
        "GCP_REGION": "europe-west1",
        "GCP_SERVICE_ACCOUNT": "deployer@harness-example.iam.gserviceaccount.com",
        "AZURE_SUBSCRIPTION_ID": "00000000-0000-0000-0000-000000000000",
        "AZURE_RESOURCE_GROUP": "example-dev",
        "AZURE_REGISTRY_NAME": "exampleregistry",
    }
    env["IMAGE_REPOSITORY"] = (
        "europe-west1-docker.pkg.dev/harness-example/repo/application"
        if provider == "gcp"
        else "exampleregistry.azurecr.io/application"
    )
    config = deploy.configuration(env)
    image = env["IMAGE_REPOSITORY"] + "@sha256:" + "a" * 64
    update, describe = deploy.deploy_commands(config, image)
    assert image in update
    assert "create" not in update and "deploy" not in update
    assert "--project" in update if provider == "gcp" else "--subscription" in update
    assert "describe" in describe if provider == "gcp" else "show" in describe
    for bad in (env["IMAGE_REPOSITORY"] + ":latest", "evil.example/application@sha256:" + "a" * 64):
        with pytest.raises(ValueError):
            deploy.deploy_commands(config, bad)
    env["IMAGE_REPOSITORY"] = "foreign.example/application"
    with pytest.raises(ValueError):
        deploy.configuration(env)


def test_health_uses_correct_readiness_contract(helper_modules, monkeypatch):
    import io

    deploy = helper_modules["deploy"]
    seen = []

    def response(request, timeout):
        seen.append(request.full_url)
        body = {"status": "ready" if request.full_url.endswith("readiness") else "ok"}
        stream = io.BytesIO(json.dumps(body).encode())
        stream.status = 200
        return stream

    monkeypatch.setattr(deploy.urllib.request, "urlopen", response)
    deploy.health("https://test.example")
    assert seen == ["https://test.example/api/health", "https://test.example/api/readiness"]


def test_secret_baseline_never_prints_values(helper_modules, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("leaked.txt").write_text("AKIA" + "A" * 16)
    Path("terraform.tfvars").write_text("project_id = 123")
    Path("safe.txt").write_text("ordinary source")
    assert helper_modules["security"].findings(["leaked.txt", "terraform.tfvars", "safe.txt"]) == [
        "leaked.txt",
        "terraform.tfvars",
    ]


@pytest.mark.parametrize("provider", ["gcp", "azure"])
def test_health_must_match_the_new_revision(helper_modules, provider):
    deploy = helper_modules["deploy"]
    image = "registry/application@sha256:" + "a" * 64
    if provider == "gcp":
        state = {
            "spec": {"template": {"spec": {"containers": [{"image": image}]}}},
            "status": {
                "conditions": [{"type": "Ready", "status": "True"}],
                "latestReadyRevisionName": "new",
                "latestCreatedRevisionName": "new",
                "traffic": [{"revisionName": "new", "percent": 100}],
                "url": "https://service-abc.a.run.app",
            },
        }
    else:
        state = {
            "properties": {
                "template": {"containers": [{"image": image}]},
                "configuration": {
                    "ingress": {
                        "external": False,
                        "allowInsecure": False,
                        "fqdn": "service.internal.example.westeurope.azurecontainerapps.io",
                    }
                },
                "provisioningState": "Succeeded",
                "latestReadyRevisionName": "new",
                "latestRevisionName": "new",
            }
        }
    assert deploy.verify_state({"provider": provider}, state, image).startswith("https://")
    state["status" if provider == "gcp" else "properties"]["latestReadyRevisionName"] = "old"
    with pytest.raises(ValueError, match="new .* revision"):
        deploy.verify_state({"provider": provider}, state, image)


def test_production_digest_is_required(helper_modules):
    for digest in ("latest", "sha256:bad", "", "sha256:" + "a" * 63):
        with pytest.raises(ValueError, match="immutable"):
            helper_modules["guard"].check_event(
                {
                    "DEPLOY_STAGE": "prod",
                    "GITHUB_EVENT_NAME": "workflow_dispatch",
                    "GITHUB_REF": "refs/heads/main",
                    "IMAGE_DIGEST": digest,
                }
            )
