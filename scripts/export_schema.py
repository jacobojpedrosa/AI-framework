"""Regenerate the declarative schema after model changes."""

import json
from pathlib import Path

from harness.config.models import ProjectConfig
from harness.infrastructure import Infrastructure
from harness.product import ProductDefinition
from harness.resolution.specification import Specification

for name, model in (
    ("project", ProjectConfig),
    ("specification", Specification),
    ("product", ProductDefinition),
    ("infrastructure", Infrastructure),
):
    schema = model.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    target = Path(__file__).resolve().parents[1] / "schemas" / f"{name}.schema.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
