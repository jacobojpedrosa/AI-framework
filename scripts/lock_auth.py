"""Resolve small optional auth overlays against every previously pinned dependency."""

import argparse
import os
import re
import subprocess
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uv", default="uv")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    uv = str(Path(args.uv).resolve()) if "/" in args.uv else args.uv
    templates = root / "src/harness/templates"
    constraints = set()
    for group in ("fullstack_ai", "persistence_locks", "ai_locks"):
        for path in (templates / group).rglob("requirements*.txt.tmpl"):
            constraints.update(re.findall(r"^([a-zA-Z0-9_.-]+==[^\s;]+)", path.read_text(), re.M))
    for provider in ("local", "oidc", "firebase"):
        for admin in (False, True):
            variant = provider + ("-admin" if admin else "")
            dependencies = ["itsdangerous==2.2.0"]
            if provider != "local":
                dependencies += ["PyJWT[crypto]==2.15.0"]
            if provider == "oidc":
                dependencies += ["authlib==1.8.0", "httpx==0.28.1"]
            if admin:
                dependencies += ["starlette-admin==1.0.1"]
            destination = templates / "auth_locks" / variant
            destination.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="harness-auth-lock-") as temporary:
                work = Path(temporary)
                source = "\n".join(dependencies) + "\n"
                (work / "requirements-auth.in").write_text(source)
                (destination / "requirements-auth.in.tmpl").write_text(source)
                (work / "constraints.txt").write_text("\n".join(sorted(constraints)) + "\n")
                subprocess.run(
                    [
                        uv,
                        "pip",
                        "compile",
                        "requirements-auth.in",
                        "--offline",
                        "--python-version",
                        "3.12",
                        "--universal",
                        "--generate-hashes",
                        "--no-header",
                        "--no-annotate",
                        "--constraint",
                        "constraints.txt",
                        "--output-file",
                        "requirements-auth.txt",
                    ],
                    cwd=work,
                    check=True,
                    stdout=subprocess.DEVNULL,
                    env=dict(os.environ, UV_CACHE_DIR=str(root / ".uv-cache")),
                )
                (destination / "requirements-auth.txt.tmpl").write_bytes(
                    (work / "requirements-auth.txt").read_bytes()
                )
            print("Locked " + variant, flush=True)


if __name__ == "__main__":
    main()
