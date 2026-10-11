from concurrent.futures import ThreadPoolExecutor

import pytest

from harness.errors import HarnessError
from harness.resolution import writer


def test_stale_snapshot_does_not_touch_current_file(tmp_path):
    path = tmp_path.resolve() / "project.yaml"
    path.write_bytes(b"new user edits")
    with pytest.raises(HarnessError, match="changed after planning"):
        writer.write_configuration(path, b"proposed", expected=b"old state")
    assert path.read_bytes() == b"new user edits"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["project.yaml"]


@pytest.mark.parametrize("update", [False, True])
def test_symlink_target_is_never_followed(tmp_path, update):
    root = tmp_path.resolve()
    target = root / "target"
    target.write_bytes(b"original")
    path = root / "project.yaml"
    path.symlink_to(target)
    with pytest.raises(HarnessError):
        writer.write_configuration(path, b"proposed", b"original" if update else None)
    assert target.read_bytes() == b"original"
    assert path.is_symlink()


def test_existing_lock_blocks_write(tmp_path):
    path = tmp_path.resolve() / "project.yaml"
    lock = path.with_name(".project.yaml.harness-lock")
    lock.write_bytes(b"another writer")
    with pytest.raises(HarnessError):
        writer.write_configuration(path, b"proposed")
    assert lock.read_bytes() == b"another writer"
    assert not path.exists()


def test_update_rechecks_file_after_backup(monkeypatch, tmp_path):
    path = tmp_path.resolve() / "project.yaml"
    path.write_bytes(b"original")
    create = writer._create

    def concurrent_edit(directory, name, payload, mode=0o600):
        create(directory, name, payload, mode)
        if ".pending-" in name:
            path.write_bytes(b"user changed it")

    monkeypatch.setattr(writer, "_create", concurrent_edit)
    with pytest.raises(HarnessError, match="changed during"):
        writer.write_configuration(path, b"proposed", expected=b"original")
    assert path.read_bytes() == b"user changed it"
    assert not list(tmp_path.glob(".*pending*"))
    assert not list(tmp_path.glob(".*lock"))
    assert next(tmp_path.glob("*.backup-*")).read_bytes() == b"original"


def test_concurrent_creation_one_winner(tmp_path):
    path = tmp_path.resolve() / "project.yaml"

    def attempt(value):
        try:
            writer.write_configuration(path, value)
            return value
        except HarnessError:
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(attempt, [b"one", b"two", b"three", b"four"]))
    winners = [value for value in results if value]
    assert len(winners) == 1
    assert path.read_bytes() == winners[0]


def test_failed_replace_preserves_original_and_backup(monkeypatch, tmp_path):
    path = tmp_path.resolve() / "project.yaml"
    path.write_bytes(b"original")

    def fail(*args, **kwargs):
        raise OSError("private detail")

    monkeypatch.setattr(writer.os, "replace", fail)
    with pytest.raises(HarnessError):
        writer.write_configuration(path, b"proposal", expected=b"original")
    assert path.read_bytes() == b"original"
    assert next(tmp_path.glob("*.backup-*")).read_bytes() == b"original"
    assert not list(tmp_path.glob(".*pending*"))


def test_pending_name_collision_never_deletes_an_existing_file(monkeypatch, tmp_path):
    path = tmp_path.resolve() / "project.yaml"
    path.write_bytes(b"original")
    pending = path.with_name(".project.yaml.pending-fixed")
    pending.write_bytes(b"unrelated file")
    monkeypatch.setattr(writer.secrets, "token_hex", lambda _: "fixed")
    with pytest.raises(HarnessError):
        writer.write_configuration(path, b"proposed", expected=b"original")
    assert path.read_bytes() == b"original"
    assert pending.read_bytes() == b"unrelated file"


def test_parent_symlink_is_rejected(tmp_path):
    root = tmp_path.resolve()
    real = root / "real"
    real.mkdir()
    alias = root / "alias"
    alias.symlink_to(real, target_is_directory=True)
    with pytest.raises(HarnessError):
        writer.write_configuration(alias / "project.yaml", b"proposed")
    assert not list(real.iterdir())
