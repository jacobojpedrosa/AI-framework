import pytest
from pydantic import ValidationError

from harness.errors import RegistryError
from harness.registry.capabilities import Capability, CapabilityRegistry, default_capabilities
from harness.registry.compatibility import CompatibilityEntry, load_compatibility
from harness.registry.integrations import Integration, IntegrationRegistry, default_integrations


def test_packaged_catalog_and_matrix_are_consistent():
    integrations = default_integrations()
    capabilities = default_capabilities()
    capabilities.validate_integrations(integrations)
    matrix = load_compatibility()
    assert len(matrix.integrations) == len(integrations.entries())
    for entry in capabilities.entries():
        implemented = entry.id.startswith(
            ("database.", "ai.", "jobs.", "scheduler.")
        ) or entry.id in {"cache.redis", "observability.opentelemetry"}
        assert entry.status == ("experimental" if implemented else "planned")
    for identifier, entry in matrix.integrations.items():
        if identifier in {
            "react",
            "fastapi",
            "docker-compose",
            "sqlite",
            "postgres",
            "pgvector",
            "redis",
            "openai",
            "gemini",
            "vertex",
            "taskiq",
            "opentelemetry",
            "openspec",
            "agent-os",
            "playwright",
            "terraform",
        }:
            assert entry.status == "experimental"
            assert entry.tested_version and entry.evidence and entry.platforms
        else:
            assert entry.tested_version is None
    assert matrix.integrations["gcp"].status == "experimental"
    assert matrix.integrations["gcp"].runtimes["terraform-google-provider"] == "8.6.0"
    assert matrix.integrations["gcp"].evidence and matrix.integrations["gcp"].platforms
    assert matrix.integrations["azure"].status == "experimental"
    assert matrix.integrations["azure"].runtimes["terraform-azurerm-provider"] == "5.9.0"
    assert matrix.integrations["azure"].evidence and matrix.integrations["azure"].platforms
    assert capabilities.get("database.pgvector").requires == ("database.postgres",)


def test_duplicate_identifiers_and_missing_lookup():
    registry = IntegrationRegistry([Integration(id="redis")])
    with pytest.raises(RegistryError, match="Duplicate"):
        registry.register(Integration(id="redis"))
    with pytest.raises(RegistryError, match="Unknown"):
        registry.get("missing")


@pytest.mark.parametrize(
    "entries",
    [
        [Capability(id="a", requires=("b",))],
        [Capability(id="a", conflicts=("b",))],
        [Capability(id="a", requires=("a",))],
        [Capability(id="a", requires=("b",)), Capability(id="b", requires=("a",))],
        [Capability(id="a", requires=("b",), conflicts=("b",)), Capability(id="b")],
        [Capability(id="a", requires=("b", "b")), Capability(id="b")],
    ],
)
def test_invalid_graph(entries):
    with pytest.raises(RegistryError):
        CapabilityRegistry(entries).validate()


def test_capability_cannot_claim_unavailable_integration():
    registry = CapabilityRegistry([Capability(id="ai.missing", integration="missing")])
    with pytest.raises(RegistryError):
        registry.validate_integrations(default_integrations())
    registry = CapabilityRegistry(
        [Capability(id="ai.openai", integration="openai", status="supported")]
    )
    with pytest.raises(RegistryError):
        registry.validate_integrations(default_integrations())


def test_supported_requires_evidence_and_exact_version():
    data = dict(status="supported", source="https://example.com")
    with pytest.raises(ValidationError):
        CompatibilityEntry.model_validate(data)
    data.update(
        supported="==1.2.3",
        tested_version="1.2.3",
        verified_at="2026-09-22",
        evidence=["ci/run/1"],
        platforms=["linux"],
        runtimes={"python": "3.12"},
    )
    assert CompatibilityEntry.model_validate(data).tested_version == "1.2.3"
    for field, value in [
        ("supported", ">=1"),
        ("verified_at", "not-a-date"),
        ("evidence", [""]),
        ("platforms", []),
    ]:
        with pytest.raises(ValidationError):
            CompatibilityEntry.model_validate({**data, field: value})


def test_matrix_rejects_mismatch():
    matrix = load_compatibility()
    with pytest.raises(RegistryError):
        matrix.validate_registry(IntegrationRegistry())
    entries = [
        Integration(id=e.id, status="experimental") for e in default_integrations().entries()
    ]
    with pytest.raises(RegistryError, match="status"):
        matrix.validate_registry(IntegrationRegistry(entries))
