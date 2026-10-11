"""Generate the Gate 17 sample, run offline AI evals and measure a disposable local API."""

import argparse
import json
import os
import socket
import subprocess
import time
from pathlib import Path
from urllib.request import urlopen

from harness.config.loader import load_project
from harness.readiness import report
from harness.scaffolding.fullstack import scaffold


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--python", type=Path, required=True, help="Environment with generated API dependencies"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    destination = args.output.absolute()
    scaffold(load_project(root / "examples/ai/project.yaml"), destination)
    api = destination / "services/api"
    python = str(args.python.absolute())
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(
            ("OPENAI_", "GEMINI_", "GOOGLE_", "VERTEX_", "AI_", "OTEL_", "TELEMETRY_")
        )
    }
    env["AI_PROVIDER"] = "fake"
    evidence = destination / ".harness/verification"
    evidence.mkdir()
    with (evidence / "tests.log").open("w") as log:
        subprocess.run(
            [python, "-m", "pytest", "-q"],
            cwd=api,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
            timeout=120,
        )
    result = subprocess.run(
        [python, "-m", "app.infrastructure.ai_evals", "evals/smoke.json"],
        cwd=api,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    (evidence / "ai-evals.json").write_text(result.stdout)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(
        [python, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=api,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError("Temporary API exited")
            try:
                with urlopen(origin + "/api/health", timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("Temporary API did not become ready")
        result = subprocess.run(
            [python, "scripts/performance_baseline.py", origin, "--samples", "30"],
            cwd=destination,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        (evidence / "performance.json").write_text(result.stdout)
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    readiness = report(destination)
    (evidence / "production-readiness.json").write_text(json.dumps(readiness, indent=2) + "\n")
    assert readiness["status"] == "blocked"
    assert readiness["production_authorized"] is False
    print(
        json.dumps(
            {
                "evidence": str(evidence),
                "production": readiness["status"],
                "performance": json.loads((evidence / "performance.json").read_text()),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
