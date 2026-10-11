"""Opt-in local runtime observations; no starts, exec, log output or remote credentials."""

import json
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from harness.doctor import Finding
from harness.errors import HarnessError

MAX_RESPONSE = 256 * 1024


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def local_url(value):
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except (ValueError, TypeError, AttributeError):
        raise HarnessError("Invalid diagnostic endpoint") from None
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or port is not None
        and not 1 <= port <= 65535
    ):
        raise HarnessError(
            "Runtime diagnosis accepts loopback origins only, without credentials or paths"
        )
    return value.rstrip("/")


def fetch(url, *, body=True):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    request = urllib.request.Request(url, headers={"Accept": "application/json,text/html,*/*"})
    try:
        response = opener.open(request, timeout=3)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        data = response.read(MAX_RESPONSE + 1) if body else b""
        if len(data) > MAX_RESPONSE:
            raise ValueError("Response too large")
        return response.status, data


def observe_http(api, web, services):
    findings = []

    def add(name, status, message):
        findings.append(Finding(name, status, message))

    if api:
        for path, expected in (("/api/health", "ok"), ("/api/readiness", "ready")):
            name = "backend." + path.rsplit("/", 1)[-1]
            try:
                status, body = fetch(api + path)
                result = json.loads(body)
                valid = (
                    status == 200
                    and isinstance(result, dict)
                    and result.get("status") == expected
                    and result.get("service") in services
                )
                add(
                    name,
                    "pass" if valid else "fail",
                    "Endpoint contract satisfied."
                    if valid
                    else "Endpoint unhealthy or response contract invalid.",
                )
                if path.endswith("readiness") and isinstance(result, dict):
                    checks = result.get("checks", [])
                    if isinstance(checks, list):
                        for index, check in enumerate(checks[:32]):
                            available = isinstance(check, dict) and check.get("available") is True
                            add(
                                f"backend.dependency.{index}",
                                "pass" if available else "fail",
                                "Readiness probe available."
                                if available
                                else "Readiness probe unavailable.",
                            )
            except (OSError, ValueError, TypeError, urllib.error.URLError):
                add(
                    name,
                    "fail",
                    "Endpoint unavailable, oversized or invalid; response body withheld.",
                )
    else:
        add("backend.discovery", "unverified", "No API endpoint discovered; supply --api-url.")
    if web:
        try:
            status, body = fetch(web + "/")
            html = body.decode("utf-8", errors="replace")
            valid = status == 200 and "<html" in html.lower()
            add(
                "frontend.http",
                "pass" if valid else "fail",
                "HTML served." if valid else "Frontend did not return HTML successfully.",
            )
            parser = AssetParser()
            parser.feed(html)
            for index, path in enumerate(parser.assets[:8]):
                status, _ = fetch(web + path, body=False)
                add(
                    f"frontend.asset.{index}",
                    "pass" if status == 200 else "fail",
                    "Referenced asset served." if status == 200 else "Referenced asset failed.",
                )
        except (OSError, ValueError, urllib.error.URLError):
            add("frontend.http", "fail", "Frontend or referenced asset is unavailable.")
    else:
        add(
            "frontend.discovery", "unverified", "No frontend endpoint discovered; supply --web-url."
        )
    return findings


class AssetParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.assets = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        path = (
            values.get("src") if tag == "script" else values.get("href") if tag == "link" else None
        )
        if path and re.fullmatch(r"/(?:assets|src)/[A-Za-z0-9_./-]+", path) and ".." not in path:
            self.assets.append(path)


def command(arguments):
    with tempfile.TemporaryFile() as output:
        try:
            result = subprocess.run(
                arguments,
                stdout=output,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode:
            return None
        output.seek(0)
        return output.read(256 * 1024)


def docker_observations(project):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,99}", project):
        raise HarnessError("Invalid Compose project selector")
    docker = shutil.which("docker")
    if not docker:
        return [Finding("process.docker", "unverified", "Docker CLI unavailable.")]
    output = command(
        [
            docker,
            "ps",
            "--all",
            "--filter",
            "label=com.docker.compose.project=" + project,
            "--format",
            "{{.ID}}",
        ]
    )
    if output is None:
        return [
            Finding("process.docker", "unverified", "Docker status unavailable; no daemon started.")
        ]
    identifiers = output.decode(errors="replace").split()
    if not identifiers:
        return [
            Finding(
                "process.docker", "warn", "No containers found for the selected Compose project."
            )
        ]
    findings = []
    for index, identifier in enumerate(identifiers[:32]):
        if not re.fullmatch(r"[a-f0-9]{12,64}", identifier):
            continue
        state = command([docker, "inspect", "--format", "{{json .State}}", identifier])
        try:
            state = json.loads(state) if state else {}
            running = state.get("Running") is True
            healthy = state.get("Health", {}).get("Status")
            findings.append(
                Finding(
                    f"process.container.{index}",
                    "fail"
                    if not running or healthy == "unhealthy"
                    else "warn"
                    if healthy == "starting"
                    else "pass",
                    "Selected container running." if running else "Selected container not running.",
                )
            )
        except (ValueError, TypeError, AttributeError):
            findings.append(
                Finding(f"process.container.{index}", "unverified", "Container state unreadable.")
            )
        logs = command([docker, "logs", "--tail", "100", "--since", "15m", identifier])
        if logs is not None:
            errors = len(re.findall(rb"(?i)traceback|\berror\b|connection refused", logs))
            findings.append(
                Finding(
                    f"logs.container.{index}",
                    "warn" if errors else "pass",
                    f"{errors} error markers in bounded recent logs; raw logs withheld.",
                    "Use backend-diagnose/frontend-diagnose for targeted source correlation."
                    if errors
                    else "",
                )
            )
    return findings


def inspect_runtime(files, config, args):
    preview = {}
    try:
        data = files.read(".harness/preview.json")
        if data:
            preview = json.loads(data)
        if not isinstance(preview, dict) or any(
            key in preview and not isinstance(preview[key], str)
            for key in ("api_url", "web_url", "compose_project")
        ):
            raise ValueError
    except (ValueError, TypeError, RecursionError):
        preview = {}
    # No implicit port guessing: an unrelated app could own 8000 or 5173.
    api = args.api_url or preview.get("api_url")
    web = args.web_url or preview.get("web_url")
    if api:
        api = local_url(api)
    if web:
        web = local_url(web)
    findings = observe_http(api, web, set(config.services))
    project = args.compose_project or preview.get("compose_project") or config.project.name
    findings += docker_observations(project)
    return findings
