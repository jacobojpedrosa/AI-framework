"""Authentication and explicit admin registration; generation does not access credentials."""

from importlib.resources import files

import yaml

from harness.config.models import ProjectConfig


def add_auth(config: ProjectConfig, rendered: dict[str, bytes], visit, api: str) -> None:
    assert config.auth is not None
    templates = files("harness.templates")
    prefix = f"services/{api}/"
    admin = bool(config.admin and config.admin.enabled)
    resources = sorted(config.admin.resources) if admin else []
    visit(templates.joinpath("auth"), overlay=True)
    if config.auth.provider != "local":
        visit(templates.joinpath("auth_jwt"), overlay=True)
    if admin:
        visit(templates.joinpath("admin"), overlay=True)
    if "records" in resources:
        visit(templates.joinpath("admin_records"), overlay=True)
    rendered[prefix + "app/infrastructure/auth_selection.py"] = (
        f'PROVIDER = "{config.auth.provider}"\n'
        f'AUTHORIZATION = "{config.auth.authorization}"\n'
        f"ADMIN_ENABLED = {admin}\n"
        f"ADMIN_RESOURCES = {tuple(resources)!r}\n".replace("'", '"')
    ).encode()
    variant = config.auth.provider + ("-admin" if admin else "")
    for extension in ("in", "txt"):
        name = f"requirements-auth.{extension}"
        rendered[prefix + name] = templates.joinpath(
            "auth_locks", variant, name + ".tmpl"
        ).read_bytes()
        for stem in ("requirements", "requirements-dev"):
            rendered[prefix + f"{stem}.{extension}"] += f"\n-r {name}\n".encode()
    dockerfile = prefix + "Dockerfile"
    rendered[dockerfile] = rendered[dockerfile].replace(
        b"COPY requirements.txt .", b"COPY requirements.txt requirements-auth.txt ./"
    )
    pyproject = prefix + "pyproject.toml"
    if b"known-first-party" not in rendered[pyproject]:
        rendered[pyproject] += b'\n[tool.ruff.lint.isort]\nknown-first-party = ["app", "tests"]\n'
    bootstrap = prefix + "app/infrastructure/bootstrap.py"
    text = (
        rendered[bootstrap]
        .decode()
        .replace(
            "from app.application.readiness import CheckReadiness\n",
            "from app.application.readiness import CheckReadiness\n"
            "from app.infrastructure.auth_bootstrap import AuthConfigurationProbe, install_auth\n",
        )
    )
    text = (
        text.replace(
            "        readiness = CheckReadiness(SERVICE_NAME, "
            '{"process": ProcessProbe()}, SystemClock())',
            '        probes = {"process": ProcessProbe()}\n'
            "        readiness = CheckReadiness(SERVICE_NAME, probes, SystemClock())",
        )
        .replace(
            "        readiness = CheckReadiness(SERVICE_NAME, probes, SystemClock())",
            '        probes["auth_configuration"] = AuthConfigurationProbe()\n'
            "        readiness = CheckReadiness(SERVICE_NAME, probes, SystemClock())",
        )
        .replace("    app.include_router", "    install_auth(app)\n    app.include_router")
    )
    rendered[bootstrap] = text.encode()
    path = prefix + "tests/test_readiness.py"
    rendered[path] = rendered[path].replace(
        b"with TestClient(create_app()) as client:",
        b'use_case = CheckReadiness(SERVICE_NAME, {"process": StaticProbe()}, FrozenClock())\n'
        b"    with TestClient(create_app(use_case)) as client:",
    )
    if admin:
        path = prefix + "tests/test_health.py"
        rendered[path] = rendered[path].replace(
            b'assert client.get("/admin").status_code == 404',
            b'assert client.get("/admin/", follow_redirects=False).status_code == 303',
        )
    variables = {"AUTH_SESSION_SECRET": "", "AUTH_COOKIE_SECURE": "true"}
    if config.auth.provider == "local":
        variables.update(
            AUTH_LOCAL_USERNAME="",
            AUTH_LOCAL_PASSWORD_HASH="",
            AUTH_LOCAL_ROLES="admin",
            AUTH_LOCAL_PERMISSIONS="",
        )
    else:
        variables["AUTH_ADMIN_SUBJECTS"] = ""
        if config.auth.provider == "oidc":
            variables.update(
                OIDC_ISSUER="", OIDC_CLIENT_ID="", OIDC_CLIENT_SECRET="", OIDC_REDIRECT_URI=""
            )
        else:
            variables.update(
                FIREBASE_PROJECT_ID="", FIREBASE_WEB_API_KEY="", FIREBASE_AUTH_DOMAIN=""
            )
    compose = yaml.safe_load(rendered["compose.yaml"])
    env = compose["services"]["api"].setdefault("environment", {})
    env.update({key: "${" + key + ":-" + value + "}" for key, value in variables.items()})
    rendered["compose.yaml"] = yaml.safe_dump(compose, sort_keys=False).encode()
    rendered[".env.example"] += (
        "\n# Auth: no default password; see the API AUTH.md.\n"
        + "\n".join(key + "=" + value for key, value in variables.items())
        + "\n"
    ).encode()
    rendered["README.md"] += (
        f"\n## Authentication and administration\n\nSee `services/{api}/AUTH.md`. "
        "Configure credentials before signing in at `/auth/login`. "
        "Only explicitly registered admin resources are exposed.\n"
    ).encode()
