"""A bounded collection prototype renderer, using the standard standalone skeleton."""

import hashlib
import json
from importlib.resources import files
from pathlib import Path

from harness import __version__
from harness.config.models import ProjectConfig
from harness.errors import HarnessError
from harness.product import ProductDefinition, definition_files, load_product, missing_questions
from harness.scaffolding.fullstack import render_project, write_project

PROTOTYPE_VERSION = "1.0.0"


def render_prototype(product: ProductDefinition, source: Path) -> dict[str, bytes]:
    questions = missing_questions(product)
    if questions:
        raise HarnessError("Product decisions missing: " + ", ".join(questions))
    if len(product.entities) != 1 or set(product.entities[0].fields) != {
        "title",
        "description",
        "status",
    }:
        raise HarnessError("Prototype supports one entity with title, description and status")
    if set(product.screens) != {"list", "detail", "create"}:
        raise HarnessError("Prototype supports list, detail and create screens only")
    if product.integrations or product.ai_capabilities:
        raise HarnessError("Prototype does not implement external integrations or AI capabilities")
    entity = product.entities[0]
    if any(item.status not in entity.statuses for item in product.seed):
        raise HarnessError("Seed status must belong to the declared entity statuses")
    config = ProjectConfig.model_validate(
        {
            "schema_version": 1,
            "project": {"name": product.name},
            "architecture": {"golden_path": "fullstack-ai", "hexagonal_services": True},
            "apps": {"web": {"framework": "react"}},
            "services": {"api": {"framework": "fastapi"}},
        }
    )
    rendered = render_project(config)
    substitutions = {
        "@@PROJECT@@": product.name,
        "@@STATUS_VALUES@@": '",\n    "'.join(entity.statuses),
    }

    def visit(directory, prefix=""):
        for entry in sorted(directory.iterdir(), key=lambda item: item.name):
            if entry.is_dir():
                visit(entry, prefix + entry.name + "/")
            elif entry.name.endswith(".tmpl"):
                text = entry.read_text()
                for token, value in substitutions.items():
                    text = text.replace(token, value)
                if "@@" in text:
                    raise HarnessError("Unresolved prototype template token")
                rendered[prefix + entry.name.removesuffix(".tmpl")] = text.encode()

    visit(files("harness.templates").joinpath("prototype"))
    frontend = {
        "title": product.title,
        "summary": product.summary,
        "entity": entity.model_dump(),
        "accent": product.design.accent,
    }
    backend = {"statuses": entity.statuses, "seed": [item.model_dump() for item in product.seed]}
    for name, data in (
        ("apps/web/src/product.json", frontend),
        ("services/api/app/infrastructure/product.json", backend),
    ):
        rendered[name] = (json.dumps(data, indent=2, ensure_ascii=True) + "\n").encode()
    for name, data in definition_files(product, source).items():
        rendered["product/" + name] = data
    rendered["skills/project-design/SKILL.md"] = (
        files("harness.data").joinpath("skills/project-design/SKILL.md").read_bytes()
    )
    rendered["schemas/product.schema.json"] = (
        json.dumps(ProductDefinition.model_json_schema(), indent=2) + "\n"
    ).encode()
    rendered[".gitignore"] += b"playwright-report/\ntest-results/\n.playwright/\n"
    rendered["apps/web/.prettierignore"] += (
        b"src/product.json\nplaywright-report\ntest-results\n.playwright\n"
    )
    rendered["Makefile"] += (
        b"\n.PHONY: e2e\ne2e:\n"
        b"\tcd apps/web && E2E_BASE_URL=http://127.0.0.1:$${WEB_PORT:-5173} npm run test:e2e\n"
    )
    rendered["README.md"] += b"\nSee PROTOTYPE.md for product flows, limits and browser tests.\n"
    manifest = json.loads(rendered.pop(".harness/scaffold.json"))
    manifest.update(
        {
            "harness_version": __version__,
            "template": "collection-prototype",
            "prototype_version": PROTOTYPE_VERSION,
            "product_sha256": hashlib.sha256(rendered["product/product.yaml"]).hexdigest(),
            "files": {
                name: hashlib.sha256(data).hexdigest() for name, data in sorted(rendered.items())
            },
        }
    )
    rendered[".harness/scaffold.json"] = (
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    ).encode()
    return rendered


def dispatch_prototype(args) -> int:
    rendered = render_prototype(load_product(args.spec), args.spec)
    if not args.dry_run and not args.approve:
        raise HarnessError("Prototype generation requires --approve for the reviewed definition")
    generated = write_project(rendered, args.output, dry_run=args.dry_run)
    print(
        "\n".join(generated)
        if args.dry_run
        else f"Generated {len(generated)} files. See PROTOTYPE.md."
    )
    return 0
