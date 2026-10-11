import base64
import hashlib
import json

import pytest
import yaml

from harness.cli import main
from harness.errors import ConfigurationError, HarnessError
from harness.product import (
    ProductDefinition,
    collect_references,
    definition_files,
    load_product,
    missing_questions,
)
from harness.prototype import render_prototype
from harness.scaffolding.fullstack import write_project


@pytest.fixture
def product_source(repo_root):
    return repo_root / "examples/product-design/feedback.yaml"


def test_questions_only_cover_missing_decisions(product_source):
    product = load_product(product_source)
    assert missing_questions(product) == {}
    partial = ProductDefinition(title="Known", integrations=[], ai_capabilities=[])
    questions = missing_questions(partial)
    assert {"title", "integrations", "ai_capabilities"}.isdisjoint(questions)
    assert {"name", "personas", "entities", "constraints"} <= questions.keys()


def test_design_partial_reports_questions_without_code(tmp_path, capsys):
    source = tmp_path / "partial.yaml"
    source.write_text("product_version: 1\ntitle: Known\n")
    destination = tmp_path / "definition"
    assert main(["project-design", str(source), "--output", str(destination), "--json"]) == 2
    report = json.loads(capsys.readouterr().out)
    assert not report["ready"]
    assert "title" not in report["questions"]
    assert set(p.name for p in destination.iterdir()) == {
        "PRODUCT.md",
        "product.yaml",
        "references.json",
    }


@pytest.mark.parametrize(
    "change",
    [
        {"product_version": True},
        {"name": "../escape"},
        {"unexpected": "value"},
        {"screens": ["list", "list"]},
        {"title": "   "},
        {"flows": [{"name": "Unknown", "steps": ["list", "not-declared"]}]},
    ],
)
def test_invalid_definition_rejected(tmp_path, product_source, change):
    data = yaml.safe_load(product_source.read_text())
    data.update(change)
    source = tmp_path / "bad.yaml"
    source.write_text(yaml.safe_dump(data))
    with pytest.raises(ConfigurationError):
        load_product(source)


def test_local_reference_copied_and_rebased(tmp_path, product_source):
    image = tmp_path / "reference.png"
    image.write_bytes(
        base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="
        )
    )
    data = load_product(product_source).model_dump()
    data["design"]["references"] = [
        {"source": "reference.png", "notes": "User-supplied color reference"}
    ]
    product = ProductDefinition.model_validate(data)
    rendered = definition_files(product, tmp_path / "product.yaml")
    destination = tmp_path / "portable"
    write_project(rendered, destination)
    exported = load_product(destination / "product.yaml")
    evidence, assets = collect_references(exported, destination / "product.yaml")
    assert assets["references/0.png"] == image.read_bytes()
    assert evidence[0]["sha256"] == hashlib.sha256(image.read_bytes()).hexdigest()
    assert evidence[0]["state"] == "host-review-required"


@pytest.mark.parametrize(
    "source",
    [
        "../outside.png",
        "/private/tmp/out.png",
        "file:///etc/passwd",
        "https://user:pass@example.com/a",
        "http://example.com/a",
    ],
)
def test_unsafe_reference_locations_rejected(product_source, source):
    data = load_product(product_source).model_dump()
    data["design"]["references"] = [{"source": source}]
    with pytest.raises(ValueError):
        ProductDefinition.model_validate(data)


@pytest.mark.parametrize("kind", ["symlink", "oversize", "signature", "svg"])
def test_unsafe_local_reference_rejected(tmp_path, product_source, kind):
    path = tmp_path / ("image.svg" if kind == "svg" else "image.png")
    if kind == "symlink":
        outside = tmp_path / "secret"
        outside.write_bytes(b"secret")
        path.symlink_to(outside)
    else:
        path.write_bytes(
            b"\x89PNG\r\n\x1a\n" + b"x" * (5 * 1024 * 1024)
            if kind == "oversize"
            else b"not an image"
        )
    data = load_product(product_source).model_dump()
    data["design"]["references"] = [{"source": path.name}]
    with pytest.raises(HarnessError):
        collect_references(ProductDefinition.model_validate(data), tmp_path / "product.yaml")


def test_https_reference_retained_without_download(product_source):
    data = load_product(product_source).model_dump()
    data["design"]["references"] = [{"source": "https://example.invalid/design"}]
    evidence, assets = collect_references(ProductDefinition.model_validate(data), product_source)
    assert not assets
    assert evidence[0]["source"] == "https://example.invalid/design"
    assert evidence[0]["state"] == "host-review-required"


def test_render_is_deterministic_standalone_and_traceable(product_source):
    product = load_product(product_source)
    result = render_prototype(product, product_source)
    assert result == render_prototype(product, product_source)
    manifest = json.loads(result[".harness/scaffold.json"])
    assert manifest["template"] == "collection-prototype"
    assert set(manifest["files"]) == set(result) - {".harness/scaffold.json"}
    for name, digest in manifest["files"].items():
        assert hashlib.sha256(result[name]).hexdigest() == digest
    assert manifest["product_sha256"] == hashlib.sha256(result["product/product.yaml"]).hexdigest()
    frontend = json.loads(result["apps/web/src/product.json"])
    assert frontend["title"] == product.title
    assert frontend["accent"] == product.design.accent
    assert b"from harness" not in result["services/api/app/infrastructure/bootstrap.py"]
    assert b"@@" not in b"".join(result.values())


@pytest.mark.parametrize(
    "kind", ["entities", "fields", "screens", "integrations", "ai", "seed", "missing"]
)
def test_unsupported_product_never_silently_degrades(product_source, kind):
    data = load_product(product_source).model_dump()
    if kind == "entities":
        data["entities"].append({**data["entities"][0], "name": "another"})
    elif kind == "fields":
        data["entities"][0]["fields"].append("amount")
    elif kind == "screens":
        data["screens"].append("dashboard")
    elif kind == "integrations":
        data["integrations"] = ["payments"]
    elif kind == "ai":
        data["ai_capabilities"] = ["summarize"]
    elif kind == "seed":
        data["seed"][0]["status"] = "unknown"
    else:
        data["personas"] = None
    with pytest.raises(HarnessError):
        render_prototype(ProductDefinition.model_validate(data), product_source)


def test_prototype_preview_approval_and_existing_files(product_source, tmp_path):
    output = tmp_path / "prototype"
    arguments = ["prototype", str(product_source), "--output", str(output)]
    assert main([*arguments, "--dry-run"]) == 0
    assert not output.exists()
    assert main(arguments) == 1
    assert not output.exists()
    assert main([*arguments, "--approve"]) == 0
    before = (output / ".harness/scaffold.json").read_bytes()
    assert main([*arguments, "--approve"]) == 1
    assert (output / ".harness/scaffold.json").read_bytes() == before


def test_writer_rejects_traversal_before_creating_directory(tmp_path):
    with pytest.raises(HarnessError, match="Unsafe"):
        write_project({"../escape": b"no"}, tmp_path / "new")
    assert not (tmp_path / "new").exists()
