import hashlib
import json
import subprocess
import sys

import pytest

from harness.config.loader import load_project
from harness.doctor import ProjectFiles, inspect_project
from harness.doctor_runtime import docker_observations, local_url, observe_http
from harness.errors import HarnessError
from harness.scaffolding.fullstack import scaffold


@pytest.fixture
def project(tmp_path, repo_root):
    folder = tmp_path / "project"
    scaffold(load_project(repo_root / "examples/cloud/project.yaml"), folder)
    return folder


def snapshot(folder):
    return {
        str(path.relative_to(folder)): (
            hashlib.sha256(path.read_bytes()).hexdigest(),
            path.stat().st_mtime_ns,
        )
        for path in folder.rglob("*")
        if path.is_file() and not path.is_symlink()
    }


def cli(project, *args):
    return subprocess.run(
        [sys.executable, "-m", "harness", "doctor", "--project", str(project), "--json", *args],
        capture_output=True,
        text=True,
    )


def findings(project):
    files = ProjectFiles(project)
    try:
        return inspect_project(files)
    finally:
        files.close()


def test_default_is_read_only_and_does_not_claim_remote_success(project):
    before = snapshot(project)
    result = cli(project)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["read_only"] is True
    assert report["counts"]["fail"] == 0
    assert report["counts"]["unverified"] > 0
    assert snapshot(project) == before
    assert cli(project, "--strict").returncode == 2


@pytest.mark.parametrize(
    "path,payload,identifier",
    [
        (
            "project.yaml",
            b"schema_version: invalid\npassword: very-secret-value\n",
            "project.config",
        ),
        ("services/api/app/main.py", b"def broken(\n", "backend.source:api"),
        ("apps/web/package.json", b"{invalid", "frontend.lock:web"),
        (
            ".env",
            b"TELEMETRY_EXPORTER=invalid\nTOKEN=very-secret-value\n",
            "observability.configuration",
        ),
        (
            ".github/workflows/production.yml",
            b"name: unsafe\non:\n  push:\n    branches: [main]\njobs: {}\n",
            "ci.production-trigger",
        ),
        ("README.md", b"AKIA" + b"A" * 16, "security.manifest-secrets"),
    ],
)
def test_introduced_faults_detected_without_mutation_or_secret_output(
    project, path, payload, identifier
):
    (project / path).write_bytes(payload)
    before = snapshot(project)
    result = cli(project)
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert any(item["id"] == identifier and item["status"] == "fail" for item in report["findings"])
    assert "very-secret-value" not in result.stdout + result.stderr
    assert "AKIA" + "A" * 16 not in result.stdout + result.stderr
    assert snapshot(project) == before


def test_missing_file_preview_then_approved_restoration(project):
    path = project / "Makefile"
    original = path.read_bytes()
    path.unlink()
    before = snapshot(project)
    result = cli(project, "--fix")
    assert result.returncode == 1
    assert json.loads(result.stdout)["proposed_repairs"][0]["path"] == "Makefile"
    assert snapshot(project) == before
    result = cli(project, "--fix", "--approve")
    assert result.returncode == 0, result.stderr
    assert path.read_bytes() == original
    assert json.loads(result.stdout)["applied_repairs"] == ["Makefile"]
    receipts = list((project / ".harness/doctor-backups").glob("*.json"))
    assert len(receipts) == 1 and json.loads(receipts[0].read_text())["before"] == "absent"


def test_modified_file_never_repaired(project):
    path = project / "Makefile"
    path.write_text("user-owned edit\n")
    before = snapshot(project)
    result = cli(project, "--fix", "--approve")
    assert result.returncode == 0
    assert json.loads(result.stdout)["applied_repairs"] == []
    assert snapshot(project) == before


def test_old_version_not_restored_from_new_templates(project):
    manifest_path = project / ".harness/scaffold.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["harness_version"] = "0.0.0"
    manifest_path.write_text(json.dumps(manifest))
    (project / "Makefile").unlink()
    report, fixes, _ = findings(project)
    assert not fixes
    assert any(item.id == "framework.version" and item.status == "warn" for item in report)


def test_symlink_and_manifest_traversal_are_rejected(project, tmp_path):
    outside = tmp_path / "private"
    outside.write_text("never-print-this-secret")
    (project / ".env").symlink_to(outside)
    result = cli(project)
    assert result.returncode == 1
    assert "never-print-this-secret" not in result.stdout + result.stderr
    (project / ".env").unlink()
    manifest = json.loads((project / ".harness/scaffold.json").read_text())
    manifest["files"]["../private"] = "a" * 64
    (project / ".harness/scaffold.json").write_text(json.dumps(manifest))
    result = cli(project)
    assert result.returncode == 1
    assert "never-print-this-secret" not in result.stdout + result.stderr


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "http://user:secret@127.0.0.1",
        "http://127.0.0.1:123/a",
        "http://127.0.0.1:123?token=secret",
        "file:///etc/passwd",
        "http://127.0.0.1:99999",
    ],
)
def test_runtime_requires_loopback_origins(url):
    with pytest.raises(HarnessError):
        local_url(url)


def test_runtime_faults_and_error_bodies_are_sanitized(monkeypatch):
    def fetch(url, **kwargs):
        if url.endswith("/api/health"):
            return 200, b'{"status":"ok","service":"api"}'
        if url.endswith("/api/readiness"):
            return (
                503,
                b'{"status":"unavailable","service":"api","checks":[{"available":false}],"secret":"sensitive-body"}',
            )
        if url.endswith("/"):
            return 200, b'<html><script src="/assets/missing.js"></script></html>'
        return 404, b"sensitive-body"

    monkeypatch.setattr("harness.doctor_runtime.fetch", fetch)
    result = observe_http("http://127.0.0.1:8000", "http://127.0.0.1:5173", {"api"})
    failed = {item.id for item in result if item.status == "fail"}
    assert {"backend.readiness", "backend.dependency.0", "frontend.asset.0"} <= failed
    assert "sensitive-body" not in repr(result)


def test_docker_inspection_is_scoped_read_only_and_redacts_logs(monkeypatch):
    calls = []

    def command(args):
        calls.append(args)
        if "ps" in args:
            return b"abcdef123456"
        if "inspect" in args:
            return b'{"Running":false,"Health":{"Status":"unhealthy"}}'
        return b"ERROR credential=do-not-print\nTraceback"

    monkeypatch.setattr("harness.doctor_runtime.shutil.which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr("harness.doctor_runtime.command", command)
    result = docker_observations("owned-project")
    assert any(item.status == "fail" for item in result)
    assert "do-not-print" not in repr(result)
    assert "label=com.docker.compose.project=owned-project" in calls[0]
    assert all(args[1] in {"ps", "inspect", "logs"} for args in calls)


def test_invalid_flags_and_missing_directory_do_not_create_files(tmp_path):
    absent = tmp_path / "absent"
    assert cli(absent).returncode == 1
    assert not absent.exists()
    assert cli(tmp_path, "--approve").returncode == 1
    assert cli(tmp_path, "--api-url", "http://127.0.0.1:1").returncode == 1


def test_diagnosis_never_executes_project_code(project, monkeypatch):
    (project / "services/api/app/main.py").write_text("raise RuntimeError('must-not-run')\n")

    def forbidden(*args, **kwargs):
        raise AssertionError("Static doctor must not execute commands")

    monkeypatch.setattr(subprocess, "run", forbidden)
    report, _, _ = findings(project)
    assert any(item.id == "backend.source:api" and item.status == "pass" for item in report)
