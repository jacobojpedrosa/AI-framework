"""Generate local/GCP/Azure examples and check every workflow with actionlint 1.7.12."""

import argparse
import json
import subprocess
from pathlib import Path

from harness.config.loader import load_project
from harness.scaffolding.fullstack import scaffold


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--actionlint", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    binary = str(args.actionlint.resolve())
    version = subprocess.run([binary, "-version"], check=True, capture_output=True, text=True)
    if not version.stdout.startswith("1.7.12"):
        raise RuntimeError("Use the verified actionlint 1.7.12 release")
    root = Path(__file__).resolve().parents[1]
    results = {}
    for provider, example in {
        "local": "specifications/fullstack-ai/expected-project.yaml",
        "gcp": "cloud/project.yaml",
        "azure": "cloud-azure/project.yaml",
    }.items():
        project = args.output.resolve() / provider
        scaffold(load_project(root / "examples" / example), project)
        workflows = sorted((project / ".github/workflows").glob("*.yml"))
        result = subprocess.run(
            [
                binary,
                "-config-file",
                str(project / ".github/actionlint.yaml"),
                "-shellcheck=",
                "-pyflakes=",
                *map(str, workflows),
            ],
            capture_output=True,
            text=True,
        )
        (project / ".harness/actionlint.log").write_text(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(f"Workflow validation failed for {provider}")
        results[provider] = [path.name for path in workflows]
    (args.output / "results.json").write_text(
        json.dumps(
            {
                "actionlint": "1.7.12",
                "workflows": results,
                "remote_actions_run": False,
                "cloud_deployed": False,
                "shellcheck": False,
                "python_helpers": "covered by Core tests",
            },
            indent=2,
        )
        + "\n"
    )
    print("All generated workflows pass actionlint; no workflows dispatched.")


if __name__ == "__main__":
    main()
