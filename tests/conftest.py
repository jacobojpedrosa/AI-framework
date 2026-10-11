from pathlib import Path

import pytest


@pytest.fixture
def config_data():
    return {
        "schema_version": 1,
        "project": {"name": "test-project"},
        "architecture": {"golden_path": "ai-service"},
        "services": {"api": {"framework": "fastapi"}},
    }


@pytest.fixture
def repo_root():
    return Path(__file__).resolve().parents[1]
