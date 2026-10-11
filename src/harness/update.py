"""Reviewable updates to the installed, pinned template bundle in a separate Git worktree."""

import hashlib
import json
import os
import re
import signal
import subprocess
import tempfile
import uuid
from dataclasses import asdict
from pathlib import Path, PurePosixPath

from harness import __version__
from harness.config.loader import parse_yaml, project_from_data
from harness.doctor import ProjectFiles, digest, inspect_project
from harness.errors import HarnessError
from harness.registry.compatibility import load_compatibility
from harness.scaffolding.fullstack import render_project

MANIFEST = ".harness/scaffold.json"


def git(root, *arguments):
    try:
        result = subprocess.run(
            ["git", "-c", "core.hooksPath=/dev/null", "-C", str(root), *arguments],
            capture_output=True,
            timeout=60,
            check=False,
            env={key: value for key, value in os.environ.items() if not key.startswith("GIT_")},
        )
    except (OSError, subprocess.TimeoutExpired):
        raise HarnessError("Git unavailable or timed out") from None
    if result.returncode:
        raise HarnessError("Git prerequisite or worktree operation failed; no merge performed")
    return result.stdout.decode().strip()


def safe_path(name):
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_./-]+", name):
        raise HarnessError("Invalid update metadata path")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] == ".git":
        raise HarnessError("Unsafe update metadata path")
    return name


def make_plan(root):
    """Three-way hash comparison: never infer permission to replace user modifications."""
    reader = ProjectFiles(root)
    try:
        raw = reader.read(MANIFEST)
        try:
            old = json.loads(raw or b"null")
            entries = old["files"]
            if old["manifest_version"] != 1 or old["template"] != "fullstack-ai-skeleton":
                raise ValueError
            if not isinstance(entries, dict) or not 1 <= len(entries) <= 2000:
                raise ValueError
            for name, checksum in entries.items():
                safe_path(name)
                if (
                    name == MANIFEST
                    or not isinstance(checksum, str)
                    or not re.fullmatch(r"[a-f0-9]{64}", checksum)
                ):
                    raise ValueError
            source_version = old["harness_version"]
            if not re.fullmatch(r"\d+\.\d+\.\d+", source_version):
                raise ValueError
            if tuple(map(int, source_version.split("."))) > tuple(map(int, __version__.split("."))):
                raise ValueError
        except (ValueError, TypeError, KeyError, RecursionError):
            raise HarnessError("Unsupported, newer or invalid scaffold manifest") from None
        config_raw = reader.read("project.yaml")
        if not config_raw or digest(config_raw) != entries.get("project.yaml"):
            raise HarnessError(
                "Configuration changed since generation; explicit migration required"
            )
        config = project_from_data(parse_yaml(config_raw.decode()))
        load_compatibility()
        target = render_project(config)
        # Preserve the exact reviewed configuration bytes.
        target["project.yaml"] = config_raw
        target_manifest = json.loads(target[MANIFEST])
        target_manifest["files"]["project.yaml"] = digest(config_raw)
        target[MANIFEST] = (json.dumps(target_manifest, indent=2, sort_keys=True) + "\n").encode()
        changes, conflicts, snapshot = [], [], {}
        for name in sorted(set(entries) | set(target)):
            safe_path(name)
            current = reader.read(name)
            current_hash = digest(current) if current is not None else None
            desired = target.get(name)
            desired_hash = digest(desired) if desired is not None else None
            baseline = digest(raw) if name == MANIFEST else entries.get(name)
            snapshot[name] = current_hash
            if current_hash == desired_hash or baseline == desired_hash:
                continue
            if current_hash != baseline:
                conflicts.append(name)
                continue
            changes.append({"path": name, "before": current_hash, "after": desired_hash})
        plan = {
            "schema_version": 1,
            "source_version": source_version,
            "target_version": __version__,
            "compatibility": "renderable-pinned-bundle",
            "changes": changes,
            "conflicts": conflicts,
            "snapshot": snapshot,
        }
        return plan, target
    finally:
        reader.close()


def read_checks(path):
    try:
        with Path(path).open() as stream:
            raw = stream.read(65537)
        if len(raw) > 65536:
            raise ValueError
        data = json.loads(raw)
        if set(data) != {"dependencies", "tests", "contracts", "e2e"}:
            raise ValueError
        for check in data.values():
            if set(check) != {"cwd", "argv"}:
                raise ValueError
            if check["cwd"] != ".":
                safe_path(check["cwd"])
            if (
                not isinstance(check["argv"], list)
                or not check["argv"]
                or any(
                    not isinstance(arg, str) or not arg or "\x00" in arg for arg in check["argv"]
                )
            ):
                raise ValueError
        return data
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        raise HarnessError(
            "Checks must define dependencies, tests, contracts and e2e argv/cwd"
        ) from None


def validate_candidate(root, checks):
    results = {}
    for name in ("dependencies", "tests", "contracts", "e2e"):
        print(f"Validating {name}", flush=True)
        check = checks[name]
        directory = root / check["cwd"]
        reader = ProjectFiles(directory)
        reader.close()
        # Reviewed local test commands can execute project code. Never use shell=True.
        with tempfile.TemporaryFile() as output:
            try:
                process = subprocess.Popen(
                    check["argv"],
                    cwd=directory,
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                try:
                    code = process.wait(timeout=600)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                    code = -1
                results[name] = "pass" if code == 0 else "fail"
            except OSError:
                results[name] = "fail"
        if results[name] != "pass":
            break
    reader = ProjectFiles(root)
    try:
        findings, _, _ = inspect_project(reader)
    finally:
        reader.close()
    results["doctor"] = "fail" if any(f.status == "fail" for f in findings) else "pass"
    return results, [asdict(f) for f in findings]


def dispatch(args):
    root = args.project.absolute()
    plan, target = make_plan(root)
    if args.target_version and args.target_version != __version__:
        raise HarnessError("Only the installed, pinned Harness bundle is an eligible target")
    checks = read_checks(args.checks) if args.checks else None
    plan["checks"] = checks
    plan["head"] = git(root, "rev-parse", "HEAD")
    if Path(git(root, "rev-parse", "--show-toplevel")).resolve() != root.resolve():
        raise HarnessError("Update requires the project at the Git repository root")
    if git(root, "status", "--porcelain", "--untracked-files=all"):
        raise HarnessError("Update requires a clean committed project, including untracked files")
    # Ignored generated files must not silently disappear from the isolated candidate.
    tracked = set(git(root, "ls-files").splitlines())
    if any(value is not None and name not in tracked for name, value in plan["snapshot"].items()):
        raise HarnessError("All existing managed files must be tracked before updating")
    token = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
    plan["approval"] = token
    print(json.dumps(plan, indent=2, sort_keys=True))
    if plan["conflicts"]:
        return 1
    if not args.apply:
        if args.approve:
            raise HarnessError("--approve requires --apply")
        return 0
    if args.approve != token or not checks:
        raise HarnessError("Apply requires the exact preview approval hash and all four checks")
    if not args.worktree:
        raise HarnessError("Apply requires a new --worktree directory outside the source project")
    destination = args.worktree.absolute()
    if destination.exists() or destination.is_relative_to(root) or root.is_relative_to(destination):
        raise HarnessError("Worktree must be a new separate directory")
    parent = ProjectFiles(destination.parent)
    parent.close()
    branch = "harness-update-" + uuid.uuid4().hex[:12]
    git(root, "worktree", "add", "-b", branch, str(destination), plan["head"])
    report = {
        "plan": plan,
        "branch": branch,
        "worktree": str(destination),
        "status": "failed",
        "human_review_required": True,
    }
    try:
        actual, _ = make_plan(destination)
        if actual["snapshot"] != plan["snapshot"]:
            raise HarnessError("Candidate no longer matches approved source")
        for change in plan["changes"]:
            path = destination / change["path"]
            if change["after"] is None:
                path.unlink()
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(target[change["path"]])
        before_validation, _ = make_plan(destination)
        results, findings = validate_candidate(destination, checks)
        after_validation, _ = make_plan(destination)
        unchanged = before_validation["snapshot"] == after_validation["snapshot"]
        report["managed_files_unchanged_by_checks"] = unchanged
        report.update(checks=results, doctor=findings)
        passed = (
            unchanged and len(results) == 5 and all(value == "pass" for value in results.values())
        )
        report["status"] = "ready-for-human-review" if passed else "failed"
    finally:
        report_path = destination / ".harness/update-report.json"
        report_path.parent.mkdir(exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(json.dumps({"report": str(report_path), "status": report["status"]}))
    return 0 if report["status"] == "ready-for-human-review" else 1
