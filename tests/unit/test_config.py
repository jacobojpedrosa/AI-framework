import json

import pytest
import yaml
from pydantic import ValidationError

from harness.config import loader
from harness.config.loader import load_project, parse_yaml
from harness.config.models import ProjectConfig
from harness.errors import ConfigurationError


@pytest.mark.parametrize(
    "golden_path", ["simple-web", "ai-service", "fullstack-ai", "service-platform"]
)
def test_known_topologies(config_data, golden_path):
    config_data["architecture"]["golden_path"] = golden_path
    model = ProjectConfig.model_validate(config_data)
    assert model.architecture.golden_path == golden_path
    assert model.admin is None
    assert model.ai is None


@pytest.mark.parametrize("value", [True, 1.0, "1", 2, None])
def test_schema_version_is_exact_integer(config_data, value):
    config_data["schema_version"] = value
    with pytest.raises(ValidationError):
        ProjectConfig.model_validate(config_data)


@pytest.mark.parametrize(
    "name", ["../oops", "hello/world", "has space", "UPPER", "a\n", "a" * 64, ""]
)
def test_unsafe_names(config_data, name):
    config_data["project"]["name"] = name
    with pytest.raises(ValidationError):
        ProjectConfig.model_validate(config_data)


@pytest.mark.parametrize(
    "changes",
    [
        {"database": {"provider": "sqlite", "vector": "pgvector"}},
        {"admin": {"enabled": True}},
        {"admin": {"enabled": True}, "auth": {"provider": "local"}, "services": {}},
        {"jobs": {"enabled": True, "adapter": "taskiq"}},
        {"jobs": {"enabled": True, "adapter": "taskiq", "broker": "redis"}},
        {"jobs": {"adapter": "memory", "broker": "redis"}},
        {"scheduler": {"enabled": True, "adapter": "taskiq", "store": "redis"}},
        {"scheduler": {"adapter": "memory", "store": "redis"}},
        {"cloud": {"provider": "aws", "target": "cloud-run"}},
        {"ai": {"providers": ["openai", "openai"]}},
        {"ai": {"providers": []}},
        {"admin": {"enabled": "true"}},
        {"auth": {"provider": "local", "password": "secret"}},
        {"services": {"../bad": {"framework": "fastapi"}}},
        {"unknown": "secret"},
    ],
)
def test_invalid_combinations(config_data, changes):
    config_data.update(changes)
    with pytest.raises(ValidationError):
        ProjectConfig.model_validate(config_data)


@pytest.mark.parametrize("provider", ["local", "oidc", "firebase"])
def test_admin_requires_explicit_auth_without_exposing_resources(config_data, provider):
    config_data.update(admin={"enabled": True}, auth={"provider": provider})
    model = ProjectConfig.model_validate(config_data)
    assert model.admin.resources == []
    assert model.auth.authorization == "authentication"


def test_fullstack_example(repo_root):
    model = load_project(repo_root / "examples/fullstack/project.yaml")
    assert model.jobs.enabled and model.scheduler.enabled
    assert model.database.vector == "pgvector"


@pytest.mark.parametrize(
    "source",
    [
        "",
        "[]",
        "plain string",
        "---\nx: 1\n---\nx: 2",
        "x: [",
        "x: 1\nx: 2",
        "nested:\n  x: 1\n  x: 2",
        "1: hello",
        "x: !!python/object/apply:os.system ['touch bad']",
        "x: &a [1]\ny: *a",
        "x: &a [*a]",
        "x: {<<: {a: 1}}",
    ],
)
def test_unsafe_or_invalid_yaml(source):
    with pytest.raises(ConfigurationError):
        parse_yaml(source)


def test_size_limit(tmp_path):
    path = tmp_path / "project.yaml"
    path.write_bytes(b"a" * (loader.MAX_BYTES + 1))
    with pytest.raises(ConfigurationError, match="size limit"):
        load_project(path)
    with pytest.raises(ConfigurationError, match="size limit"):
        parse_yaml("é" * loader.MAX_BYTES)


def test_depth_limit():
    with pytest.raises(ConfigurationError, match="nesting limit"):
        parse_yaml("x: " + "[" * 100 + "0" + "]" * 100)


def test_node_limit():
    with pytest.raises(ConfigurationError, match="node limit"):
        parse_yaml("x: [" + ",".join("0" for _ in range(loader.MAX_NODES)) + "]")


def test_missing_directory_and_non_utf8(tmp_path):
    for path in (tmp_path, tmp_path / "missing"):
        with pytest.raises(ConfigurationError):
            load_project(path)
    path = tmp_path / "bad.yaml"
    path.write_bytes(b"\xff")
    with pytest.raises(ConfigurationError, match="UTF-8"):
        load_project(path)


def test_errors_do_not_reveal_input_or_unknown_keys(config_data, tmp_path):
    secret = "sk-do-not-print-this-value"
    config_data.update({secret: secret, "ai": {"providers": [secret]}})
    config_data["project"]["name"] = secret + "!"
    path = tmp_path / "project.yaml"
    path.write_text(yaml.safe_dump(config_data))
    with pytest.raises(ConfigurationError) as caught:
        load_project(path)
    assert secret not in str(caught.value)
    assert "project.name" in str(caught.value)
    assert "ai.providers.0" in str(caught.value)


def test_syntax_errors_do_not_echo_source():
    with pytest.raises(ConfigurationError) as caught:
        parse_yaml('password: ["a-super-secret-value"')
    assert "a-super-secret-value" not in str(caught.value)
    assert "line" in str(caught.value)


@pytest.mark.parametrize("source", ["value: 2026-99-99", "value: " + "9" * 5000])
def test_scalar_constructor_errors_are_sanitized(source):
    with pytest.raises(ConfigurationError, match="scalar value"):
        parse_yaml(source)


def test_environment_is_not_interpolated(monkeypatch):
    monkeypatch.setenv("HARNESS_TEST_SECRET", "do-not-read")
    assert parse_yaml("value: ${HARNESS_TEST_SECRET}")["value"] == "${HARNESS_TEST_SECRET}"


def test_json_schema_matches_source(repo_root):
    expected = ProjectConfig.model_json_schema()
    expected["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    actual = json.loads((repo_root / "schemas/project.schema.json").read_text())
    assert actual == expected
