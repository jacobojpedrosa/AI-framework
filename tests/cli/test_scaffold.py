import subprocess
import sys


def test_cli_scaffold(repo_root, tmp_path):
    config = repo_root / "examples/specifications/fullstack-ai/expected-project.yaml"
    args = [sys.executable, "-m", "harness", "scaffold", str(config), "--output", "sample"]
    preview = subprocess.run(args + ["--dry-run"], cwd=tmp_path, capture_output=True, text=True)
    assert preview.returncode == 0, preview.stderr
    assert "compose.yaml" in preview.stdout
    assert not (tmp_path / "sample").exists()
    generated = subprocess.run(args, cwd=tmp_path, capture_output=True, text=True)
    assert generated.returncode == 0, generated.stderr
    assert (tmp_path / "sample/Makefile").is_file()
    repeated = subprocess.run(args, cwd=tmp_path, capture_output=True, text=True)
    assert repeated.returncode == 1
    assert "already exists" in repeated.stderr
