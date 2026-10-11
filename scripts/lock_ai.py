"""Maintainer-only resolution of AI SDK + persistence dependency combinations."""

import argparse
import os
import subprocess
import tempfile
from pathlib import Path

SDKS = {
    "openai": ["openai==3.19.0"],
    "google": ["google-genai==2.25.0", "httpx==0.28.1"],
    "both": ["openai==3.19.0", "google-genai==2.25.0", "httpx==0.28.1"],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uv", default="uv")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    uv = str(Path(args.uv).resolve()) if "/" in args.uv else args.uv
    templates = root / "src/harness/templates"
    sources = {"base": templates / "fullstack_ai/services/__API__"}
    sources.update({p.name: p for p in (templates / "persistence_locks").iterdir() if p.is_dir()})
    for storage, base in sources.items():
        for sdk, dependencies in SDKS.items():
            destination = templates / "ai_locks" / (storage + "-" + sdk)
            destination.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="harness-ai-lock-") as temporary:
                work = Path(temporary)
                for stem in ("requirements", "requirements-dev"):
                    text = (base / f"{stem}.in.tmpl").read_text()
                    if stem == "requirements":
                        text += "\n" + "\n".join(dependencies) + "\n"
                    (work / f"{stem}.in").write_text(text)
                    (destination / f"{stem}.in.tmpl").write_text(text)
                    (work / "constraints.txt").write_text((base / f"{stem}.txt.tmpl").read_text())
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
                        "constraints.txt",
                        "--output-file",
                        f"{stem}.txt",
                    ]
                    if stem == "requirements-dev":
                        command += ["--constraint", "requirements.txt"]
                    subprocess.run(
                        command,
                        cwd=work,
                        check=True,
                        env=dict(os.environ, UV_CACHE_DIR=str(root / ".uv-cache")),
                        stdout=subprocess.DEVNULL,
                    )
                    (destination / f"{stem}.txt.tmpl").write_text(
                        (work / f"{stem}.txt").read_text()
                    )
            print("Locked " + storage + "-" + sdk, flush=True)


if __name__ == "__main__":
    main()
