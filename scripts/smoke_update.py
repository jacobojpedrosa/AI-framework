"""Demonstrate approved branch isolation and real generated-project gates.

Requires Docker/Make. Creates a synthetic older dependency baseline in a new
local Git fixture; never operates on a user's repository or existing stack.
"""

import argparse
import contextlib
import io
import json
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

from harness.config.loader import load_project
from harness.doctor import digest
from harness.errors import HarnessError
from harness.scaffolding.fullstack import scaffold
from harness.update import MANIFEST, dispatch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    output = parser.parse_args().output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[1]
    source = output / "source"
    scaffold(
        load_project(root / "examples/specifications/fullstack-ai/expected-project.yaml"), source
    )
    manifest = json.loads((source / MANIFEST).read_text())
    manifest["harness_version"] = "0.14.0"
    dependency = "services/api/requirements.in"
    data = (source / dependency).read_bytes().replace(b"0.141.1", b"0.140.0")
    (source / dependency).write_bytes(data)
    manifest["files"][dependency] = digest(data)
    (source / MANIFEST).write_text(json.dumps(manifest))
    for args in (
        ["init"],
        ["add", "."],
        [
            "-c",
            "user.name=Harness smoke",
            "-c",
            "user.email=smoke@example.invalid",
            "commit",
            "-m",
            "Synthetic update baseline",
        ],
    ):
        subprocess.run(["git", "-C", str(source), *args], check=True, capture_output=True)
    checks = output / "checks.json"
    checks.write_text(
        json.dumps(
            {
                "dependencies": {"cwd": ".", "argv": ["make", "build"]},
                "tests": {"cwd": ".", "argv": ["make", "test"]},
                "contracts": {"cwd": ".", "argv": ["make", "test-contracts"]},
                "e2e": {
                    "cwd": ".",
                    "argv": [sys.executable, str(root / "scripts/update_http_e2e.py")],
                },
            },
            indent=2,
        )
    )
    args = Namespace(
        project=source,
        target_version=None,
        checks=checks,
        apply=False,
        approve=None,
        worktree=output / "candidate",
    )
    preview = io.StringIO()
    with contextlib.redirect_stdout(preview):
        assert dispatch(args) == 0
    plan = json.loads(preview.getvalue())
    (output / "preview.json").write_text(preview.getvalue())
    before = (source / MANIFEST).read_bytes()
    args.apply, args.approve = True, plan["approval"]
    print("Running dependency build, project tests, contracts and HTTP E2E", flush=True)
    assert dispatch(args) == 0
    assert (source / MANIFEST).read_bytes() == before
    args.apply, args.approve, args.target_version = False, None, "999.0.0"
    try:
        dispatch(args)
    except HarnessError:
        (output / "incompatible.json").write_text(
            json.dumps({"target": "999.0.0", "rejected": True})
        )
    else:
        raise AssertionError("Incompatible target accepted")
    print("Compatible candidate validated; incompatible target rejected; source unchanged")


if __name__ == "__main__":
    main()
