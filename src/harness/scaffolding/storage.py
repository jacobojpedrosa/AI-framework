from importlib.resources import files

from harness.config.models import ProjectConfig
from harness.errors import HarnessError


def add_storage(config: ProjectConfig, rendered: dict[str, bytes], visit, api: str) -> None:
    assert config.storage is not None
    if config.storage.provider not in {"local", "s3"}:
        raise HarnessError(
            "Storage provider not implemented in this phase: " + config.storage.provider
        )
    templates = files("harness.templates")
    prefix = f"services/{api}/"
    visit(templates.joinpath("storage"), overlay=True)
    if config.storage.provider == "s3":
        visit(templates.joinpath("storage_s3"), overlay=True)
    settings = rendered[prefix + "app/infrastructure/storage_settings.py"].decode()
    rendered[prefix + "app/infrastructure/storage_settings.py"] = settings.replace(
        "STORAGE_PROVIDER_TOKEN", config.storage.provider
    ).encode()
    bootstrap = prefix + "app/infrastructure/bootstrap.py"
    text = rendered[bootstrap].decode()
    text = text.replace(
        "from app.application.readiness import CheckReadiness\n",
        "from app.application.readiness import CheckReadiness\n"
        "from app.infrastructure.storage_settings import PROVIDER, ROOT, BUCKET, MAX_BYTES\n",
    )
    text = text.replace(
        "    app.state.resources = resources\n",
        "    app.state.resources = resources\n"
        '    if PROVIDER == "local":\n'
        "        from app.adapters.local_storage import LocalStorage\n"
        "        app.state.storage = LocalStorage(ROOT, MAX_BYTES)\n"
        '    elif PROVIDER == "s3":\n'
        "        import boto3\n"
        "        from app.adapters.s3_storage import S3Storage\n"
        '        app.state.storage = S3Storage(boto3.client("s3"), BUCKET, MAX_BYTES)\n',
    )
    rendered[bootstrap] = text.encode()
    compose = rendered["compose.yaml"].decode()
    rendered["compose.yaml"] = (
        compose + "\n# File storage uses STORAGE_* environment variables; "
        "credentials stay external.\n"
    ).encode()
    rendered[".env.example"] += (
        b"\nSTORAGE_MAX_BYTES=25000000\nSTORAGE_LOCAL_ROOT=/app/data/files\nSTORAGE_S3_BUCKET=\n"
    )
    rendered["README.md"] += (
        b"\n## File storage\n\nThe service exposes an explicit storage port "
        b"with tenant-scoped keys. "
        b"Local storage is atomic and path-safe; S3 uses an injected boto-compatible client.\n"
    )
