"""Maintainer-only Taskiq lock resolution, constrained by all previous optional locks."""

import argparse
import os
import re
import subprocess
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uv", default="uv")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    uv = str(Path(args.uv).resolve()) if "/" in args.uv else args.uv
    templates = root / "src/harness/templates"
    constraints = set()
    for group in ("fullstack_ai", "persistence_locks", "ai_locks", "auth_locks"):
        for path in (templates / group).rglob("requirements*.txt.tmpl"):
            constraints.update(re.findall(r"^([a-zA-Z0-9_.-]+==[^\s;]+)", path.read_text(), re.M))
    destination = templates / "jobs_locks"
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="harness-jobs-lock-") as temporary:
        work = Path(temporary)
        source = "taskiq==0.12.6\ntaskiq-redis==1.2.3\n"
        (work / "requirements-jobs.in").write_text(source)
        (destination / "requirements-jobs.in.tmpl").write_text(source)
        (work / "constraints.txt").write_text("\n".join(sorted(constraints)) + "\n")
        command = [
            uv,
            "pip",
            "compile",
            "requirements-jobs.in",
            "--python-version",
            "3.12",
            "--universal",
            "--generate-hashes",
            "--no-header",
            "--no-annotate",
            "--constraint",
            "constraints.txt",
            "--output-file",
            "requirements-jobs.txt",
        ]
        if args.offline:
            command.append("--offline")
        subprocess.run(
            command,
            cwd=work,
            check=True,
            stdout=subprocess.DEVNULL,
            env=dict(os.environ, UV_CACHE_DIR=str(root / ".uv-cache")),
        )
        (destination / "requirements-jobs.txt.tmpl").write_bytes(
            (work / "requirements-jobs.txt").read_bytes()
        )


if __name__ == "__main__":
    main()
