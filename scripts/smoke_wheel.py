"""Install a wheel with locked runtime dependencies and test it outside the repo.

Usage: python scripts/smoke_wheel.py --uv .tools/bin/uv
Requires the dependencies to have been cached by uv sync; makes no network calls.
"""

import argparse
import os
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

from harness import __version__


def run(command: list[str], cwd: Path, env: dict[str, str], quiet: bool = False) -> None:
    subprocess.run(
        command, cwd=cwd, env=env, check=True, stdout=subprocess.DEVNULL if quiet else None
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uv", default="uv")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    uv = str(Path(args.uv).resolve()) if "/" in args.uv else args.uv
    wheel = root / f"dist/development_harness_internal-{__version__}-py3-none-any.whl"
    with zipfile.ZipFile(wheel) as archive:
        wheel_names = archive.namelist()
        assert "harness/data/compatibility.yaml" in wheel_names
        assert "harness/data/tooling/pins.json" in wheel_names
        assert "harness/data/tooling/package-lock.json" in wheel_names
        assert "harness/data/skills/project-design/SKILL.md" in wheel_names
        for skill in ("backend-diagnose", "frontend-diagnose", "browser-inspect"):
            assert f"harness/data/skills/{skill}/SKILL.md" in wheel_names
        assert "harness/templates/cloud_locks/google.lock.hcl.tmpl" in wheel_names
        assert "harness/templates/cloud_locks/azurerm.lock.hcl.tmpl" in wheel_names
        assert not any("node_modules" in name for name in wheel_names)
    with tarfile.open(root / f"dist/development_harness_internal-{__version__}.tar.gz") as archive:
        source_names = archive.getnames()
    forbidden = {".tools", ".venv", ".venv312", ".uv-cache", "__pycache__", ".env"}
    assert not any(
        part in forbidden for name in (*wheel_names, *source_names) for part in Path(name).parts
    ), "Distribution contains local-only files"
    env = dict(os.environ, UV_CACHE_DIR=str(root / ".uv-cache"))
    env.pop("PYTHONPATH", None)
    with tempfile.TemporaryDirectory(prefix="harness-wheel-") as temporary:
        outside = Path(temporary).resolve()
        requirements = outside / "requirements.txt"
        run(
            [
                uv,
                "export",
                "--locked",
                "--offline",
                "--no-dev",
                "--no-emit-project",
                "--format",
                "requirements-txt",
                "--output-file",
                str(requirements),
            ],
            root,
            env,
            quiet=True,
        )
        venv = outside / "venv"
        run([uv, "venv", "--offline", "--python", sys.executable, str(venv)], outside, env)
        python = str(venv / "bin/python")
        run([uv, "pip", "sync", "--offline", "--python", python, str(requirements)], outside, env)
        run(
            [uv, "pip", "install", "--offline", "--no-deps", "--python", python, str(wheel)],
            outside,
            env,
        )
        cli = str(venv / "bin/harness")
        run([cli, "--help"], outside, env)
        run([cli, "update", "--help"], outside, env, quiet=True)
        run([cli, "readiness", "--help"], outside, env, quiet=True)
        run([cli, "init", "demo", "--name", "wheel-demo"], outside, env)
        run([cli, "validate", "demo/project.yaml"], outside, env)
        run(
            [
                cli,
                "scaffold",
                str(root / "examples/specifications/fullstack-ai/expected-project.yaml"),
                "--output",
                "generated",
            ],
            outside,
            env,
        )
        assert (outside / "generated/services/api/tests/contracts/test_health_ports.py").is_file()
        run([cli, "doctor", "--project", "generated", "--json"], outside, env, quiet=True)
        run(
            [
                cli,
                "scaffold",
                str(root / "examples/persistence/project.yaml"),
                "--output",
                "persistent",
            ],
            outside,
            env,
        )
        persistent = outside / "persistent/services/api"
        assert (persistent / "migrations/versions/0002_vectors.py").is_file()
        assert "redis==8.1.0" in (persistent / "requirements.txt").read_text()
        run(
            [cli, "scaffold", str(root / "examples/ai/project.yaml"), "--output", "ai-project"],
            outside,
            env,
        )
        ai_project = outside / "ai-project/services/api"
        assert "openai==3.19.0" in (ai_project / "requirements.txt").read_text()
        assert (ai_project / "AI.md").is_file()
        run(
            [cli, "scaffold", str(root / "examples/jobs/project.yaml"), "--output", "jobs-project"],
            outside,
            env,
        )
        jobs_project = outside / "jobs-project/services/api"
        assert "taskiq==0.12.6" in (jobs_project / "requirements-jobs.txt").read_text()
        assert (jobs_project / "app/adapters/admin_schedules.py").is_file()
        run(
            [
                cli,
                "scaffold",
                str(root / "examples/observability/project.yaml"),
                "--output",
                "observed-project",
            ],
            outside,
            env,
        )
        observed = outside / "observed-project"
        assert (observed / "services/api/OBSERVABILITY.md").is_file()
        assert (
            "opentelemetry-sdk==1.44.0"
            in (observed / "services/api/requirements-telemetry.txt").read_text()
        )
        assert (observed / "apps/web/src/telemetry.ts").is_file()
        assert (observed / "DEVELOPMENT_TOOLS.md").is_file()
        run([cli, "integrations", "init", "--project", str(observed), "--dry-run"], outside, env)
        product_spec = root / "examples/product-design/feedback.yaml"
        run(
            [cli, "scaffold", str(root / "examples/cloud/project.yaml"), "--output", "cloud"],
            outside,
            env,
        )
        assert (outside / "cloud/infra/gcp/service/.terraform.lock.hcl").is_file()
        assert (outside / "cloud/infra/README.md").is_file()
        run(
            [cli, "init", "azure-config", "--name", "azure-demo", "--environment", "azure"],
            outside,
            env,
        )
        run([cli, "scaffold", "azure-config/project.yaml", "--output", "azure"], outside, env)
        assert (outside / "azure/infra/azure/service/.terraform.lock.hcl").is_file()
        assert (outside / "azure/.github/workflows/production.yml").is_file()
        assert (outside / "azure/.github/scripts/guard.py").is_file()
        assert not (outside / "azure/infra/gcp").exists()
        assert "internal ingress only" in (outside / "azure/infra/README.md").read_text()
        run(
            [cli, "project-design", str(product_spec), "--output", "definition", "--json"],
            outside,
            env,
        )
        run(
            [cli, "prototype", "definition/product.yaml", "--output", "prototype", "--approve"],
            outside,
            env,
        )
        assert (outside / "prototype/apps/web/e2e/collection.spec.ts").is_file()
        assert (outside / "prototype/services/api/app/application/items.py").is_file()
        run(
            [
                python,
                "-S",
                "-c",
                "from app.application.jobs import JobRegistry, heartbeat; "
                "from app.ports.jobs import JobQueuePort, SchedulerPort; "
                "import asyncio; assert asyncio.run(heartbeat())['status'] == 'ok'",
            ],
            jobs_project,
            env,
        )
        run(
            [
                python,
                "-S",
                "-c",
                "from app.adapters.fake_ai import FakeAI; from app.domain.ai import TextRequest; "
                "from app.application.generate_text import GenerateText; "
                "assert GenerateText(FakeAI()).execute(TextRequest('test')).provider == 'fake'",
            ],
            ai_project,
            env,
        )
        run(
            [
                python,
                "-S",
                "-c",
                "from app.domain.records import Record; "
                "from app.ports.repository import Repository; "
                "from app.ports.vectors import VectorStore; "
                "from app.ports.cache import Cache",
            ],
            persistent,
            env,
        )
        run(
            [python, "-S", "-c", "from app.application.readiness import CheckReadiness"],
            outside / "generated/services/api",
            env,
        )
        (outside / "spec.yaml").write_text("spec_version: 1\nweb: true\n", encoding="utf-8")
        run(
            [
                cli,
                "setup",
                "spec.yaml",
                "--project",
                "demo/project.yaml",
                "--non-interactive",
                "--write",
                "--approve",
            ],
            outside,
            env,
        )
        run([cli, "validate", "demo/project.yaml"], outside, env)
        run(
            [
                python,
                "-c",
                "from harness.registry.compatibility import load_compatibility; "
                "assert {'openspec', 'agent-os', 'fastapi'} <= "
                "load_compatibility().integrations.keys(); "
                "import harness; assert 'site-packages' in harness.__file__; "
                "print('Wheel and packaged metadata verified outside the repository')",
            ],
            outside,
            env,
        )


if __name__ == "__main__":
    main()
