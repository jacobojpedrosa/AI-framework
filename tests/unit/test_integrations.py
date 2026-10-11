import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path

import pytest

from harness import integrations
from harness.cli import main
from harness.config.loader import load_project
from harness.errors import HarnessError
from harness.scaffolding.fullstack import scaffold


@pytest.fixture
def project(tmp_path, repo_root):
    destination = tmp_path.resolve() / "generated project"
    scaffold(
        load_project(repo_root / "examples/specifications/fullstack-ai/expected-project.yaml"),
        destination,
    )
    return destination


def snapshot(project):
    return {str(p.relative_to(project)): p.read_bytes() for p in project.rglob("*") if p.is_file()}


def fake_prepare(stage):
    for relative in integrations.TARGETS:
        target = stage / relative
        target.mkdir(parents=True)
        (target / "official.txt").write_text(relative)
    return {"node": "v24.2.0", "npm": "11.7.0"}


def test_dry_run_is_offline_read_only(project, monkeypatch, capsys):
    before = snapshot(project)
    monkeypatch.setattr(integrations, "_prepare", lambda _: pytest.fail("Installer called"))
    assert main(["integrations", "init", "--project", str(project), "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["pins"] == integrations.PINS
    assert before == snapshot(project)


@pytest.mark.parametrize("relative", (*integrations.TARGETS, integrations.RECEIPT))
@pytest.mark.parametrize("symlink", (False, True))
def test_existing_destinations_are_preserved(project, relative, symlink):
    target = project / relative
    if symlink:
        target.symlink_to(project / "absent")
    else:
        target.mkdir()
        (target / "user.txt").write_text("preserve me")
    with pytest.raises(HarnessError, match="Already exists"):
        integrations.initialize_integrations(project)
    assert target.is_symlink() if symlink else (target / "user.txt").read_text() == "preserve me"


def test_symlink_ancestor_rejected(project):
    link = project.parent / "alias"
    link.symlink_to(project.parent, target_is_directory=True)
    with pytest.raises(HarnessError, match="symlink-free"):
        integrations.initialize_integrations(link / project.name)


@pytest.mark.parametrize("relative", (".harness", ".harness/scaffold.json", "project.yaml"))
def test_symlink_metadata_rejected(project, relative):
    target = project / relative
    moved = target.with_name(target.name + "-original")
    target.rename(moved)
    target.symlink_to(moved)
    with pytest.raises(HarnessError, match="symlinked"):
        integrations.initialize_integrations(project)


def test_missing_project_is_not_created(tmp_path):
    target = tmp_path / "absent"
    with pytest.raises(HarnessError, match="generated"):
        integrations.initialize_integrations(target)
    assert not target.exists()


def test_success_receipt_and_repeated_install(project, monkeypatch):
    before = snapshot(project)
    monkeypatch.setattr(integrations, "_prepare", fake_prepare)
    integrations.initialize_integrations(project)
    receipt = json.loads((project / integrations.RECEIPT).read_text())
    assert receipt["pins"] == integrations.PINS
    assert len(receipt["files"]) == 4
    for name, digest in receipt["files"].items():
        assert hashlib.sha256((project / name).read_bytes()).hexdigest() == digest
    for name, data in before.items():
        assert (project / name).read_bytes() == data
    after = snapshot(project)
    with pytest.raises(HarnessError, match="Already exists"):
        integrations.initialize_integrations(project)
    assert snapshot(project) == after
    assert not list((project / ".harness").glob("integration-*"))


def test_installer_failure_publishes_nothing(project, monkeypatch):
    before = snapshot(project)

    def fail(stage):
        fake_prepare(stage)
        raise HarnessError("upstream failed")

    monkeypatch.setattr(integrations, "_prepare", fail)
    with pytest.raises(HarnessError, match="upstream failed"):
        integrations.initialize_integrations(project)
    assert snapshot(project) == before
    assert not list((project / ".harness").glob("integration-*"))


def test_publish_collision_rolls_back_only_own_directories(project, monkeypatch):
    monkeypatch.setattr(integrations, "_prepare", fake_prepare)
    replace = integrations.os.replace

    def collide(source, destination):
        replace(source, destination)
        if destination == project / "openspec":
            (project / "agent-os").mkdir()
            (project / "agent-os/user.txt").write_text("external concurrent write")

    monkeypatch.setattr(integrations.os, "replace", collide)
    with pytest.raises(FileExistsError):
        integrations.initialize_integrations(project)
    assert (project / "agent-os/user.txt").read_text() == "external concurrent write"
    assert not (project / "openspec").exists()
    assert not (project / ".harness/tooling").exists()
    assert not (project / integrations.RECEIPT).exists()


def test_install_lock_preserved(project):
    lock = project / ".harness/integrations.installing"
    lock.touch()
    with pytest.raises(HarnessError, match="already running"):
        integrations.initialize_integrations(project)
    assert lock.exists()


def test_bad_checksum_prevents_extraction(tmp_path):
    archive = tmp_path / "archive"
    archive.write_bytes(b"untrusted")
    with pytest.raises(HarnessError, match="checksum mismatch"):
        integrations._extract_agent_os(archive, tmp_path / "extracted")
    assert not (tmp_path / "extracted").exists()


@pytest.mark.parametrize("kind", ("symlink", "traversal"))
def test_archive_rejects_unsafe_members(tmp_path, monkeypatch, kind):
    archive = tmp_path / "archive.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        member = tarfile.TarInfo("escape" if kind == "symlink" else "../escaped")
        if kind == "symlink":
            member.type = tarfile.SYMTYPE
            member.linkname = "../outside"
        bundle.addfile(member, io.BytesIO())
    monkeypatch.setitem(
        integrations.PINS["agent_os"], "sha256", hashlib.sha256(archive.read_bytes()).hexdigest()
    )
    with pytest.raises((HarnessError, tarfile.FilterError)):
        integrations._extract_agent_os(archive, tmp_path / "extracted")
    assert not (tmp_path / "escaped").exists()


def test_tool_error_does_not_expose_subprocess_output(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        assert kwargs["stdin"] == subprocess.DEVNULL
        assert kwargs["timeout"] == 300
        raise subprocess.CalledProcessError(1, "npm", stderr="private-token")

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(HarnessError, match="Official tool command failed: npm") as caught:
        integrations._run(["npm", "ci"], tmp_path, {})
    assert "private-token" not in str(caught.value)


def test_pins_and_lock_are_consistent_and_local(tmp_path):
    lock = json.loads(integrations.RESOURCES.joinpath("package-lock.json").read_text())
    assert (
        lock["packages"]["node_modules/@fission-ai/openspec"]["version"]
        == integrations.PINS["openspec"]
    )
    for name, package in lock["packages"].items():
        if name:
            assert package["integrity"].startswith("sha512-")
            assert package["resolved"].startswith("https://registry.npmjs.org/")
    env = integrations.tool_environment(tmp_path)
    assert env["OPENSPEC_TELEMETRY"] == "0"
    assert Path(env["XDG_CONFIG_HOME"]).is_relative_to(tmp_path)
    assert Path(env["XDG_DATA_HOME"]).is_relative_to(tmp_path)
