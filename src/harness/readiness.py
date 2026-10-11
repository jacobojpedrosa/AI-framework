"""Read-only production evidence inventory; never authorizes a deployment."""

import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from harness.doctor import ProjectFiles, digest, inspect_project

REQUIRED = (
    "identity_access",
    "secrets_tls",
    "dependency_audit",
    "restore_drill",
    "migration_rehearsal",
    "deployment_rollback",
    "monitoring_alerts",
    "performance",
    "tests_contracts_e2e",
    "release_approval",
)


def report(root):
    files = ProjectFiles(root)
    try:
        findings, _, config = inspect_project(files)
        manifest = files.read(".harness/scaffold.json")
        manifest_hash = digest(manifest) if manifest else None
        checks = []
        required = list(REQUIRED)
        if config and config.ai:
            required.append("ai_quality")
        for name in required:
            # Records are evidence supplied by the operator, not assertions verified by Harness.
            path = f".harness/readiness/{name}.json"
            raw = files.read(path)
            status = "missing"
            if raw is not None:
                try:
                    item = json.loads(raw)
                    recorded = datetime.fromisoformat(item.get("recorded_at", ""))
                    now = datetime.now(UTC)
                    valid = (
                        item.get("schema_version") == 1
                        and item.get("check") == name
                        and item.get("status") in {"pass", "fail"}
                        and isinstance(item.get("reviewer"), str)
                        and bool(item["reviewer"].strip())
                        and isinstance(item.get("scope"), str)
                        and bool(item["scope"].strip())
                        and recorded.tzinfo is not None
                        and now - timedelta(days=30) <= recorded <= now
                        and manifest_hash is not None
                        and item.get("manifest_sha256") == manifest_hash
                    )
                    status = "attested-" + item["status"] if valid else "invalid"
                except (ValueError, TypeError, AttributeError, RecursionError):
                    status = "invalid"
            checks.append(
                {
                    "check": name,
                    "status": status,
                    "path": path,
                    "sha256": digest(raw) if raw is not None else None,
                }
            )
        failures = any(f.status == "fail" for f in findings)
        complete = not failures and all(c["status"] == "attested-pass" for c in checks)
        return {
            "schema_version": 1,
            "read_only": True,
            "status": "requires-independent-review" if complete else "blocked",
            "production_authorized": False,
            "manifest_sha256": manifest_hash,
            "evidence_is_operator_attested": True,
            "doctor": [asdict(f) for f in findings],
            "checks": checks,
            "limitations": [
                "Evidence scope, age and truth require independent review.",
                "No cloud, identity, backup or production validation performed.",
            ],
        }
    finally:
        files.close()


def dispatch(args):
    result = report(args.project)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if result["status"] == "blocked" else 0
