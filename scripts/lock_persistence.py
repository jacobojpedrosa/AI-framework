"""Explicit maintainer operation: resolve/hash optional generated API dependencies.

Requires network or a populated uv cache. Never called by scaffold.
"""

import argparse
import os
import subprocess
import tempfile
from pathlib import Path

VARIANTS = {
    "redis": ["redis==8.1.0"],
    "sql": ["SQLAlchemy==2.0.54", "alembic==1.20.0"],
    "sql-redis": ["SQLAlchemy==2.0.54", "alembic==1.20.0", "redis==8.1.0"],
    "postgres": ["SQLAlchemy==2.0.54", "alembic==1.20.0", "psycopg[binary]==3.3.6"],
    "postgres-redis": [
        "SQLAlchemy==2.0.54",
        "alembic==1.20.0",
        "psycopg[binary]==3.3.6",
        "redis==8.1.0",
    ],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uv", default="uv")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    uv = str(Path(args.uv).resolve()) if "/" in args.uv else args.uv
    templates = root / "src/harness/templates"
    base = templates / "fullstack_ai/services/__API__"
    env = dict(os.environ, UV_CACHE_DIR=str(root / ".uv-cache"))
    for variant, dependencies in VARIANTS.items():
        destination = templates / "persistence_locks" / variant
        destination.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="harness-lock-") as temporary:
            work = Path(temporary)
            for stem in ("requirements", "requirements-dev"):
                text = (base / f"{stem}.in.tmpl").read_text()
                if stem == "requirements":
                    text += "\n" + "\n".join(dependencies) + "\n"
                (work / f"{stem}.in").write_text(text)
                (work / "base-constraints.txt").write_text((base / f"{stem}.txt.tmpl").read_text())
                (destination / f"{stem}.in.tmpl").write_text(text)
                command = [
                    uv,
                    "pip",
                    "compile",
                    f"{stem}.in",
                    "--python-version",
                    "3.12",
                    "--universal",
                    "--generate-hashes",
                    "--no-header",
                    "--no-annotate",
                    "--constraint",
                    "base-constraints.txt",
                    "--output-file",
                    f"{stem}.txt",
                ]
                if stem == "requirements-dev":
                    command += ["--constraint", "requirements.txt"]
                subprocess.run(command, cwd=work, env=env, check=True, stdout=subprocess.DEVNULL)
                (destination / f"{stem}.txt.tmpl").write_text((work / f"{stem}.txt").read_text())
        print(f"Locked {variant}", flush=True)


if __name__ == "__main__":
    main()
