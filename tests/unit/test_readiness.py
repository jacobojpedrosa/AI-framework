import importlib.util
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta

import pytest

from harness.config.loader import load_project
from harness.doctor import digest
from harness.readiness import REQUIRED, report
from harness.scaffolding.fullstack import scaffold


@pytest.fixture
def project(tmp_path, repo_root):
    root = tmp_path / "sample"
    scaffold(load_project(repo_root / "examples/ai/project.yaml"), root)
    return root


def test_readiness_blocks_missing_evidence_and_is_read_only(project):
    before = {p: p.read_bytes() for p in project.rglob("*") if p.is_file()}
    result = report(project)
    assert result["status"] == "blocked"
    assert result["production_authorized"] is False
    assert "ai_quality" in {c["check"] for c in result["checks"]}
    assert before == {p: p.read_bytes() for p in project.rglob("*") if p.is_file()}


def records(project):
    folder = project / ".harness/readiness"
    folder.mkdir()
    for name in (*REQUIRED, "ai_quality"):
        (folder / f"{name}.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "check": name,
                    "status": "pass",
                    "reviewer": "Test",
                    "scope": "Synthetic fixture only",
                    "recorded_at": datetime.now(UTC).isoformat(),
                    "manifest_sha256": digest((project / ".harness/scaffold.json").read_bytes()),
                }
            )
        )
    return folder


def test_attestations_never_authorize_production(project):
    records(project)
    result = report(project)
    assert result["status"] == "requires-independent-review"
    assert result["production_authorized"] is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "fail"),
        ("manifest_sha256", "wrong"),
        ("recorded_at", "invalid"),
        ("reviewer", ""),
        ("recorded_at", (datetime.now(UTC) - timedelta(days=31)).isoformat()),
    ],
)
def test_invalid_stale_or_failed_evidence_blocks(project, field, value):
    folder = records(project)
    path = folder / "restore_drill.json"
    item = json.loads(path.read_text())
    item[field] = value
    path.write_text(json.dumps(item))
    assert report(project)["status"] == "blocked"


def test_generated_evals_pass_fail_and_omit_prompts(project):
    api = project / "services/api"
    assert "COPY --chown=app:app evals ./evals" in (api / "Dockerfile").read_text()
    command = [sys.executable, "-m", "app.infrastructure.ai_evals", "evals/smoke.json"]
    result = subprocess.run(
        command, cwd=api, capture_output=True, text=True, env={"AI_PROVIDER": "fake"}
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["synthetic"] is True
    assert "Synthetic smoke input" not in result.stdout
    path = api / "evals/smoke.json"
    data = json.loads(path.read_text())
    data["cases"][0]["expected"] = "wrong"
    path.write_text(json.dumps(data))
    result = subprocess.run(
        command, cwd=api, capture_output=True, text=True, env={"AI_PROVIDER": "fake"}
    )
    assert result.returncode == 1
    assert json.loads(result.stdout)["status"] == "fail"


def test_live_eval_needs_explicit_approval(project):
    result = subprocess.run(
        [sys.executable, "-m", "app.infrastructure.ai_evals", "evals/smoke.json"],
        cwd=project / "services/api",
        capture_output=True,
        text=True,
        env={"AI_PROVIDER": "openai", "OPENAI_MODEL": "test-model", "OPENAI_API_KEY": "secret"},
    )
    assert result.returncode == 1
    assert "secret" not in result.stdout


def test_baseline_refuses_remote_or_unbounded_requests(project):
    spec = importlib.util.spec_from_file_location(
        "baseline", project / "scripts/performance_baseline.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for origin, samples in (
        ("https://example.com", 20),
        ("http://127.0.0.1", 1000),
        ("http://user:pass@localhost", 20),
    ):
        with pytest.raises(ValueError):
            module.measure(origin, samples)
