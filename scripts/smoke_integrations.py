"""Exercise official development tools in a new generated project (network required).

Creates a real OpenSpec change, validates it and archives it with the official CLI.
Never invokes a model or changes a user's existing project.
"""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from harness.config.loader import load_project
from harness.integrations import PINS, initialize_integrations, tool_environment
from harness.scaffolding.fullstack import scaffold


def verify(project: Path) -> dict:
    tooling = project / ".harness/tooling"
    env = tool_environment(tooling)
    cli = tooling / "node_modules/.bin/openspec"
    outputs = {}

    def run(label, *args):
        result = subprocess.run(
            [str(cli), *args],
            cwd=project,
            env=env,
            text=True,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            check=True,
            timeout=60,
        )
        outputs[label] = result.stdout.strip()
        return result.stdout

    receipt = json.loads((project / ".harness/integrations.json").read_text())
    assert receipt["pins"] == PINS
    for name, digest in receipt["files"].items():
        assert hashlib.sha256((project / name).read_bytes()).hexdigest() == digest
    assert run("version", "--version").strip() == PINS["openspec"]
    for tool in (".claude", ".agents"):
        assert (project / tool / "skills/openspec-propose/SKILL.md").is_file()
    commands = project / ".claude/commands/agent-os"
    assert {path.stem for path in commands.glob("*.md")} == set(PINS["agent_os_commands"])
    source = tooling / f"agent-os-{PINS['agent_os']['commit']}"
    for name in PINS["agent_os_commands"]:
        assert (commands / f"{name}.md").read_bytes() == (
            source / "commands/agent-os" / f"{name}.md"
        ).read_bytes()
    run("new", "new", "change", "integration-check", "--json")
    change = project / "openspec/changes/integration-check"
    (change / "proposal.md").write_text(
        "## Why\nVerify the development tools integration.\n\n"
        "## What Changes\nRecord tool ownership as an example specification.\n\n"
        "## Capabilities\n### New Capabilities\n"
        "- `integration-check`: Keep engineering standards separate from change specifications.\n"
        "### Modified Capabilities\nNone.\n\n"
        "## Impact\nDevelopment documentation only; no application runtime changes.\n"
    )
    (change / "design.md").write_text(
        "## Context\nThe Harness integrates two upstream tools.\n\n"
        "## Goals / Non-Goals\nClarify ownership; do not add runtime dependencies.\n\n"
        "## Decisions\nAgent OS manages standards and OpenSpec manages changes.\n\n"
        "## Risks / Trade-offs\nVersion drift is controlled by exact pins.\n"
    )
    (change / "tasks.md").write_text(
        "## 1. Verification\n- [x] 1.1 Verify official tools and ownership.\n"
    )
    spec = change / "specs/integration-check/spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text(
        "## Purpose\n"
        "Keep standards and specification responsibilities explicit in generated projects.\n\n"
        "## ADDED Requirements\n\n### Requirement: Development ownership\n"
        "The project SHALL use Agent OS for standards and OpenSpec for change specifications.\n\n"
        "#### Scenario: A developer prepares a change\n"
        "- **WHEN** a developer creates an OpenSpec change\n"
        "- **THEN** its context references the Agent OS engineering standards\n"
    )
    run("instructions", "instructions", "proposal", "--change", "integration-check", "--json")
    assert "agent-os/standards/index.yml" in outputs["instructions"]
    run("validate", "validate", "integration-check", "--strict", "--json", "--no-interactive")
    run("status", "status", "--change", "integration-check", "--json")
    assert json.loads(outputs["status"])["isComplete"] is True
    run("archive", "archive", "integration-check", "--yes")
    assert (project / "openspec/specs/integration-check/spec.md").is_file()
    assert not change.exists()
    run("validate-specs", "validate", "--specs", "--strict", "--json", "--no-interactive")
    run("list", "list", "--json")
    return {"status": "passed", "pins": PINS, "runtime": receipt["runtime"], "outputs": outputs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New project directory")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    project = args.output.absolute()
    scaffold(load_project(root / "examples/observability/project.yaml"), project)
    initialize_integrations(project)
    result = verify(project)
    (project / ".harness/integration-smoke.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Official OpenSpec create/validate/archive and Agent OS provenance verified.")


if __name__ == "__main__":
    main()
