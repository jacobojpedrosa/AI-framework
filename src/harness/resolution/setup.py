"""CLI interaction around the pure resolver and explicit write gate."""

import difflib
import json
import os
import sys
from pathlib import Path
from typing import Any

from harness.config.loader import parse_yaml, project_from_data, read_text
from harness.errors import ConfigurationError, HarnessError
from harness.registry.capabilities import default_capabilities
from harness.resolution.resolver import missing_questions, resolve
from harness.resolution.specification import (
    Specification,
    load_specification,
    specification_from_data,
)
from harness.resolution.writer import write_configuration

QUESTIONS = {
    "environment": "Deployment environment [local/gcp/azure; AWS pending]: ",
    "name": "Project name (lowercase, e.g. my-project): ",
    "web": "Does the project need a web app? [yes/no]: ",
    "services": "Independent API service names, comma separated (or '-' for none): ",
}


def _answer(field: str) -> Any:
    print(QUESTIONS[field], end="", file=sys.stderr, flush=True)
    try:
        value = input().strip()
    except (EOFError, KeyboardInterrupt):
        raise HarnessError("Setup cancelled; no configuration written") from None
    if field == "web":
        if value.lower() not in ("yes", "y", "no", "n", "si", "sí", "s"):
            raise ConfigurationError("web: answer yes or no")
        return value.lower() not in ("no", "n")
    if field == "services":
        return [] if value == "-" else [part.strip() for part in value.split(",")]
    return value


def setup(args) -> int:
    if args.approve and not args.write:
        raise HarnessError("--approve requires --write")
    existing = None
    snapshot = None
    if args.project:
        source = read_text(args.project)
        existing = project_from_data(parse_yaml(source))
        snapshot = source.encode("utf-8")
    spec = load_specification(args.spec) if args.spec else Specification()
    interactive = not args.non_interactive and sys.stdin.isatty()
    environment = getattr(args, "environment", None)
    if environment is not None:
        if spec.environment is not None and spec.environment != environment:
            raise ConfigurationError("--environment conflicts with the specification")
        spec = specification_from_data(
            dict(spec.model_dump(exclude_unset=True), environment=environment)
        )
    elif interactive and spec.environment is None and not existing and not spec.capabilities.cloud:
        spec = specification_from_data(
            dict(spec.model_dump(exclude_unset=True), environment=_answer("environment"))
        )
    missing = missing_questions(spec, existing)
    if missing and interactive:
        values = spec.model_dump(exclude_unset=True)
        for field in missing:
            values[field] = _answer(field)
        spec = specification_from_data(values)
        missing = missing_questions(spec, existing)
    if missing:
        if args.json:
            print(json.dumps({"status": "incomplete", "missing": list(missing)}, sort_keys=True))
        raise ConfigurationError("Missing architecture choices: " + ", ".join(missing))

    proposal = resolve(spec, existing)
    target = args.output or args.project or Path("project.yaml")
    same_target = bool(args.project and os.path.abspath(target) == os.path.abspath(args.project))
    unchanged = bool(
        same_target and existing and proposal.config.model_dump() == existing.model_dump()
    )
    yaml_text = proposal.yaml()
    # The serialized result must satisfy the same bounded loader as user files.
    project_from_data(parse_yaml(yaml_text))
    changes = (
        []
        if unchanged
        else list(
            difflib.unified_diff(
                source.splitlines(keepends=True) if existing else [],
                yaml_text.splitlines(keepends=True),
                fromfile="current",
                tofile="proposed",
            )
        )
    )
    if args.json:
        catalog = default_capabilities()
        print(
            json.dumps(
                {
                    "status": "proposed",
                    "output": str(target),
                    "golden_path": proposal.config.architecture.golden_path,
                    "reasons": proposal.reasons,
                    "rationale": proposal.rationale,
                    "capabilities": [
                        {"id": identifier, "status": catalog.get(identifier).status}
                        for identifier in proposal.capabilities
                    ],
                    "config": proposal.configuration(),
                    "diff": "".join(changes),
                },
                sort_keys=True,
                indent=2,
            )
        )
    else:
        print(yaml_text, end="")
        print("Output: " + json.dumps(str(target)), file=sys.stderr)
        for reason in proposal.reasons:
            print(reason, file=sys.stderr)
        if proposal.rationale:
            print("Rationale: " + json.dumps(proposal.rationale), file=sys.stderr)
        if existing and changes:
            # Preserve lines while escaping terminal control sequences from source comments.
            safe_diff = "".join(
                char if char.isprintable() or char in "\n\t" else f"\\u{ord(char):04x}"
                for char in "".join(changes)
            )
            print("Changes:\n" + safe_diff, file=sys.stderr)
    if not args.write:
        print("Preview only. Use --write to save the reviewed proposal.", file=sys.stderr)
        return 0
    if unchanged:
        print("No semantic changes; existing file preserved byte-for-byte.", file=sys.stderr)
        return 0
    if not args.approve:
        if not interactive:
            raise HarnessError(
                "Writing requires approval: review the preview, then use --write --approve"
            )
        print("Write this proposal? [y/N]: ", end="", file=sys.stderr, flush=True)
        try:
            approved = input().strip().lower() in ("yes", "y", "si", "sí", "s")
        except (EOFError, KeyboardInterrupt):
            approved = False
        if not approved:
            raise HarnessError("Setup cancelled; no configuration written")
    backup = write_configuration(
        target,
        yaml_text.encode("utf-8"),
        expected=snapshot if same_target else None,
    )
    print(
        "Configuration written. No applications generated or integrations installed.",
        file=sys.stderr,
    )
    if backup:
        print("Original backup: " + json.dumps(str(backup)), file=sys.stderr)
    return 0
