import hashlib
import json

import pytest
import yaml

from harness.config.loader import load_project
from harness.config.models import ProjectConfig
from harness.scaffolding.fullstack import render_project


@pytest.mark.parametrize("provider", [None, "memory", "sqlite", "postgres", "pgvector"])
@pytest.mark.parametrize("cache", [False, True])
def test_optional_persistence_artifacts_and_compose(repo_root, provider, cache):
    data = load_project(
        repo_root / "examples/specifications/fullstack-ai/expected-project.yaml"
    ).model_dump(exclude_none=True)
    if provider:
        data["database"] = {"provider": "postgres" if provider == "pgvector" else provider}
        if provider == "pgvector":
            data["database"]["vector"] = "pgvector"
    if cache:
        data["cache"] = {"provider": "redis"}
    config = ProjectConfig.model_validate(data)
    rendered = render_project(config)
    assert rendered == render_project(config)
    prefix = "services/api/"
    assert (prefix + "app/ports/repository.py" in rendered) == bool(provider)
    sql = provider in {"sqlite", "postgres", "pgvector"}
    assert (prefix + "migrations/env.py" in rendered) == sql
    assert (prefix + "app/adapters/pgvector_store.py" in rendered) == (provider == "pgvector")
    assert (prefix + "app/adapters/redis_cache.py" in rendered) == cache
    requirements = rendered[prefix + "requirements.txt"]
    assert (b"sqlalchemy==" in requirements) == sql
    assert (b"psycopg==" in requirements) == (provider in {"postgres", "pgvector"})
    assert (b"redis==" in requirements) == cache
    compose = yaml.safe_load(rendered["compose.yaml"])
    assert ("db" in compose["services"]) == (provider in {"postgres", "pgvector"})
    assert ("cache" in compose["services"]) == cache
    for service in ("db", "cache"):
        if service in compose["services"]:
            assert "ports" not in compose["services"][service]
            assert "@sha256:" in compose["services"][service]["image"]
    for name, payload in rendered.items():
        if name.endswith(".py"):
            compile(payload, name, "exec")
    manifest = json.loads(rendered[".harness/scaffold.json"])
    for name, digest in manifest["files"].items():
        assert hashlib.sha256(rendered[name]).hexdigest() == digest


def test_persistence_templates_do_not_import_harness(repo_root):
    for group in ("persistence", "repository", "sql", "vector", "cache"):
        for path in (repo_root / "src/harness/templates" / group).rglob("*.py.tmpl"):
            assert "from harness" not in path.read_text()
            assert "import harness" not in path.read_text()


def test_dependency_lock_inputs_are_exact_and_match_versions(repo_root):
    root = repo_root / "src/harness/templates/persistence_locks"
    for variant in root.iterdir():
        for stem in ("requirements", "requirements-dev"):
            lock = (variant / f"{stem}.txt.tmpl").read_text()
            assert "--hash=sha256:" in lock
            assert "/Users/" not in lock
            inputs = (variant / f"{stem}.in.tmpl").read_text()
            for line in inputs.splitlines():
                if line.strip() and not line.startswith("-r "):
                    assert "==" in line
                    name, version = line.split("==")
                    name = name.split("[")[0].lower()
                    assert f"{name}=={version}" in lock
