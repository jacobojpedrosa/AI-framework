"""Explicit maintenance of the prototype's pinned Playwright dependency."""

import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "src/harness/templates/fullstack_ai/apps/__WEB__"
TARGET = ROOT / "src/harness/templates/prototype/apps/web"
package = json.loads((BASE / "package.json.tmpl").read_text())
package["devDependencies"]["@playwright/test"] = "1.64.0"
package["scripts"]["test:e2e"] = "playwright test"
with tempfile.TemporaryDirectory(prefix="harness-prototype-lock-") as directory:
    temp = Path(directory)
    (temp / "package.json").write_text(json.dumps(package, indent=2) + "\n")
    (temp / "package-lock.json").write_bytes((BASE / "package-lock.json.tmpl").read_bytes())
    subprocess.run(
        [
            "npm",
            "install",
            "--package-lock-only",
            "--ignore-scripts",
            "--no-audit",
            "--no-fund",
            "--cache",
            str(temp / "cache"),
        ],
        cwd=temp,
        check=True,
        timeout=180,
    )
    for name in ("package.json", "package-lock.json"):
        (TARGET / f"{name}.tmpl").write_bytes((temp / name).read_bytes())
