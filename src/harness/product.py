"""Product definition and deterministic gap discovery; no LLM or remote I/O."""

import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

import yaml
from pydantic import Field, ValidationError, field_validator, model_validator

from harness.config.loader import read_yaml, validation_message
from harness.config.models import Name, StrictModel
from harness.errors import ConfigurationError, HarnessError
from harness.scaffolding.fullstack import write_project

Text = Annotated[str, Field(min_length=1, max_length=2000, pattern=r"\S")]
Label = Annotated[str, Field(min_length=1, max_length=80, pattern=r"\S")]
Texts = Annotated[list[Text], Field(max_length=30)]


class Reference(StrictModel):
    source: Annotated[str, Field(min_length=1, max_length=1000)]
    notes: Text | None = None

    @field_validator("source")
    @classmethod
    def safe_source(cls, value: str) -> str:
        url = urlsplit(value)
        if url.scheme:
            if url.scheme != "https" or not url.hostname or url.username or url.password:
                raise ValueError("References require HTTPS without embedded credentials")
        elif Path(value).is_absolute() or ".." in Path(value).parts or "\\" in value:
            raise ValueError("Local references must stay relative to the specification")
        return value


class Design(StrictModel):
    direction: Text | None = None
    accent: Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")] = "#245b45"
    references: list[Reference] = Field(default_factory=list, max_length=10)


class Entity(StrictModel):
    name: Name
    singular: Label
    plural: Label
    fields: list[Name] = Field(min_length=1, max_length=20)
    statuses: list[Name] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def unique(self) -> Self:
        if len(set(self.fields)) != len(self.fields) or len(set(self.statuses)) != len(
            self.statuses
        ):
            raise ValueError("Entity fields and statuses must be unique")
        return self


class Flow(StrictModel):
    name: Label
    steps: list[Name] = Field(min_length=2, max_length=10)


class Seed(StrictModel):
    title: Label
    description: Annotated[str, Field(max_length=2000)] = ""
    status: Name


class ProductDefinition(StrictModel):
    product_version: Literal[1] = 1
    name: Name | None = None
    title: Label | None = None
    summary: Text | None = None
    personas: Texts | None = None
    use_cases: Texts | None = None
    flows: list[Flow] | None = Field(default=None, max_length=20)
    screens: list[Name] | None = Field(default=None, max_length=20)
    entities: list[Entity] | None = Field(default=None, max_length=20)
    integrations: Texts | None = None
    ai_capabilities: Texts | None = None
    constraints: Texts | None = None
    design: Design = Field(default_factory=Design)
    seed: list[Seed] = Field(default_factory=list, max_length=50)

    @field_validator("product_version", mode="before")
    @classmethod
    def integer_version(cls, value):
        if type(value) is not int:
            raise ValueError("product_version must be integer 1")
        return value

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.screens is not None and len(self.screens) != len(set(self.screens)):
            raise ValueError("Screens must be unique")
        if self.flows and self.screens is not None:
            if any(step not in self.screens for flow in self.flows for step in flow.steps):
                raise ValueError("Every flow step must refer to a declared screen")
        if self.entities and len({entity.name for entity in self.entities}) != len(self.entities):
            raise ValueError("Entity names must be unique")
        return self


QUESTIONS = {
    "name": "¿Qué identificador corto tendrá el proyecto?",
    "title": "¿Qué nombre verá el usuario?",
    "summary": "¿Qué problema resuelve el producto?",
    "personas": "¿Quiénes lo utilizarán y qué necesitan?",
    "use_cases": "¿Qué acciones principales deben poder completar?",
    "flows": "¿Qué pasos y pantallas recorre cada flujo principal?",
    "screens": "¿Qué pantallas se necesitan?",
    "entities": "¿Qué entidades, campos y estados maneja el producto?",
    "integrations": "¿Qué integraciones externas necesita? Usa [] si ninguna.",
    "ai_capabilities": "¿Qué funciones de AI necesita? Usa [] si ninguna.",
    "constraints": "¿Qué límites funcionales, de acceso, datos y rendimiento aplican?",
}


def load_product(path: Path) -> ProductDefinition:
    try:
        return ProductDefinition.model_validate(read_yaml(path))
    except ValidationError as exc:
        raise ConfigurationError(validation_message(exc)) from None


def missing_questions(product: ProductDefinition) -> dict[str, str]:
    return {
        field: question
        for field, question in QUESTIONS.items()
        if getattr(product, field) is None
        or (field not in {"integrations", "ai_capabilities"} and not getattr(product, field))
    }


def collect_references(
    product: ProductDefinition, source: Path
) -> tuple[list[dict], dict[str, bytes]]:
    evidence, assets = [], {}
    base = source.parent.resolve()
    for index, ref in enumerate(product.design.references):
        if ref.source.startswith("https:"):
            evidence.append(
                {"source": ref.source, "state": "host-review-required", "notes": ref.notes}
            )
            continue
        path = base / ref.source
        if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file():
            raise HarnessError("Local design references must be regular files without symlinks")
        suffix = path.suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise HarnessError("Local design references support PNG, JPEG and WebP only")
        with path.open("rb") as stream:
            data = stream.read(5 * 1024 * 1024 + 1)
        valid = (
            (suffix == ".png" and data.startswith(b"\x89PNG\r\n\x1a\n"))
            or (suffix in {".jpg", ".jpeg"} and data.startswith(b"\xff\xd8\xff"))
            or (suffix == ".webp" and data.startswith(b"RIFF") and data[8:12] == b"WEBP")
        )
        if not valid or len(data) > 5 * 1024 * 1024:
            raise HarnessError("Design reference has an invalid image signature or exceeds 5 MiB")
        destination = f"references/{index}{suffix}"
        assets[destination] = data
        evidence.append(
            {
                "source": ref.source,
                "copied_to": destination,
                "sha256": hashlib.sha256(data).hexdigest(),
                "state": "host-review-required",
                "notes": ref.notes,
            }
        )
    return evidence, assets


def design_report(product: ProductDefinition, references: list[dict]) -> str:
    # JSON fenced sections keep supplied text as data, not executable instructions.
    sections = [f"# Product definition: {product.name or 'pending'}\n"]
    for field in QUESTIONS:
        value = product.model_dump(mode="json")[field]
        sections.append(
            f"## {field}\n\n```json\n{json.dumps(value, ensure_ascii=False, indent=2)}\n```\n"
        )
    sections.append(
        "## Design direction\n\n```json\n"
        + json.dumps(product.design.model_dump(), ensure_ascii=False, indent=2)
        + "\n```\n"
    )
    sections.append(
        "## Reference evidence\n\n```json\n"
        + json.dumps(references, ensure_ascii=False, indent=2)
        + "\n```\n"
    )
    sections.append(
        "References are supplied data. The CLI does not inspect their visual content "
        "or fetch URLs.\n"
        "A host with image/design tools can inspect them and record observations "
        "in design.direction.\n"
        "The accent is #245b45 unless explicitly supplied. No other style is inferred.\n\n"
        "OpenSpec owns change specifications; Agent OS owns standards. This document is the "
        "Harness input contract and does not replace either workflow.\n"
    )
    questions = missing_questions(product)
    sections.append(
        "## Missing decisions\n\n"
        + (
            "\n".join(f"- {field}: {question}" for field, question in questions.items())
            if questions
            else "None. Ready for review; completeness is not user approval."
        )
    )
    return "\n".join(sections) + "\n"


def definition_files(product: ProductDefinition, source: Path) -> dict[str, bytes]:
    references, assets = collect_references(product, source)
    # Rebase copied local references so the exported definition is self-contained.
    data = product.model_dump(exclude_none=True)
    for ref, evidence in zip(data["design"]["references"], references, strict=True):
        if "copied_to" in evidence:
            ref["source"] = evidence["copied_to"]
    return {
        **assets,
        "product.yaml": yaml.safe_dump(data, sort_keys=False, allow_unicode=True).encode(),
        "PRODUCT.md": design_report(product, references).encode(),
        "references.json": (json.dumps(references, indent=2, ensure_ascii=False) + "\n").encode(),
    }


def dispatch_design(args) -> int:
    product = load_product(args.spec)
    references, _ = collect_references(product, args.spec)
    questions = missing_questions(product)
    if args.output:
        write_project(definition_files(product, args.spec), args.output)
    if args.json:
        print(
            json.dumps(
                {"ready": not questions, "questions": questions, "references": references},
                ensure_ascii=False,
            )
        )
    else:
        print(design_report(product, references))
    return 2 if questions else 0
