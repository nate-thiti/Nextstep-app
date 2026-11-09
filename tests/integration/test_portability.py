from __future__ import annotations

import json
import os
import sqlite3
import zipfile
from pathlib import Path

import pytest

from nextstep.application.dto import AddReference, CreateWorkItem, SaveCheckpoint
from nextstep.domain.enums import ReferenceType
from nextstep.domain.errors import ArchiveError, RestoreRequiresRestartError
from nextstep.infrastructure.archive import (
    ARCHIVE_FORMAT_VERSION,
    DATABASE_NAME,
    MANIFEST_NAME,
    ZipArchive,
)
from nextstep.infrastructure.db import Database


def _seed(app_context) -> None:
    item = app_context.work_items.create(
        CreateWorkItem(title="Fix login", goal="Ship auth", group_name="Auth")
    )
    checkpoint = app_context.checkpoints.save(
        SaveCheckpoint(
            work_item_id=item.id,
            stopped_at="integration test fails",
            next_actions="check cookie after refresh",
            completed_work="middleware fixed",
            blockers="token expired",
            context_summary="Longer context",
        )
    )
    app_context.references.add(
        AddReference(
            work_item_id=item.id,
            checkpoint_id=checkpoint.id,
            type=ReferenceType.URL,
            label="Issue",
            target="https://example.com/issues/42",
        )
    )


def test_backup_creates_archive_with_manifest_and_snapshot(app_context, tmp_path: Path) -> None:
    _seed(app_context)
    destination = tmp_path / "backup.zip"

    result = app_context.portability.backup(destination)

    assert result.path == destination
    assert result.work_item_count == 1
    assert result.checkpoint_count == 1
    assert result.reference_count == 1
    assert destination.exists()

    with zipfile.ZipFile(destination) as bundle:
        names = set(bundle.namelist())
        manifest = json.loads(bundle.read(MANIFEST_NAME).decode("utf-8"))
    assert names == {DATABASE_NAME, MANIFEST_NAME}
    assert manifest["format_version"] == ARCHIVE_FORMAT_VERSION
    assert manifest["app_version"] == "0.1.0"
    assert manifest["schema_version"] == "0002_audit_logs"
    assert manifest["counts"] == {
        "work_items": 1,
        "checkpoints": 1,
        "references": 1,
    }

    snapshot = tmp_path / "snapshot.db"
    ZipArchive(app_context.paths.database_path).extract_database(destination, snapshot)
    connection = sqlite3.connect(snapshot)
    try:
        assert connection.execute("SELECT title FROM work_items").fetchone() == ("Fix login",)
        assert connection.execute("SELECT COUNT(*) FROM checkpoints").fetchone() == (1,)
    finally:
        connection.close()


def test_backup_adds_zip_suffix(app_context, tmp_path: Path) -> None:
    result = app_context.portability.backup(tmp_path / "backup")

    assert result.path.name == "backup.zip"
    assert result.path.exists()


def test_restore_brings_back_previous_data(app_context, tmp_path: Path) -> None:
    _seed(app_context)
    archive = app_context.portability.backup(tmp_path / "backup.zip")
    work_item = app_context.work_items.list_items()[0]
    app_context.work_items.delete(work_item.id)
    assert app_context.work_items.list_items() == []

    result = app_context.portability.restore(archive.path)

    assert result.path == archive.path
    assert result.safety_backup.exists()
    assert app_context.restore_confirmation_pending()

    database = Database.open(app_context.paths.database_path)
    try:
        with database.uow() as uow:
            restored = uow.work_items.list_items()
            assert [item.title for item in restored] == ["Fix login"]
            assert uow.checkpoints.count() == 1
            assert uow.references.count() == 1
    finally:
        database.dispose()


def test_restore_creates_safety_backup_of_current_data(app_context, tmp_path: Path) -> None:
    _seed(app_context)
    archive = app_context.portability.backup(tmp_path / "backup.zip")

    result = app_context.portability.restore(archive.path)

    assert result.safety_backup.name.startswith("pre-restore-")
    manifest = ZipArchive(app_context.paths.database_path).read_manifest(result.safety_backup)
    assert manifest["counts"]["work_items"] == 1


def test_backup_failure_leaves_no_archive(app_context, tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a directory", encoding="utf-8")

    with pytest.raises(ArchiveError):
        app_context.portability.backup(blocker / "backup.zip")

    assert not (blocker / "backup.zip").exists()


def test_restore_rejects_a_file_that_is_not_a_zip(app_context, tmp_path: Path) -> None:
    broken = tmp_path / "broken.zip"
    broken.write_text("not a zip", encoding="utf-8")

    with pytest.raises(ArchiveError):
        app_context.portability.restore(broken)


def test_restore_rejects_missing_manifest(app_context, tmp_path: Path) -> None:
    broken = tmp_path / "broken.zip"
    with zipfile.ZipFile(broken, "w") as bundle:
        bundle.writestr(DATABASE_NAME, b"whatever")

    with pytest.raises(ArchiveError):
        app_context.portability.restore(broken)


def test_restore_rejects_a_newer_schema(app_context, tmp_path: Path) -> None:
    _seed(app_context)
    source = app_context.portability.backup(tmp_path / "backup.zip")
    snapshot = tmp_path / "snapshot.db"
    archiver = ZipArchive(app_context.paths.database_path)
    archiver.extract_database(source.path, snapshot)

    newer = tmp_path / "newer.zip"
    archiver.write_archive(
        newer,
        snapshot,
        {
            "format_version": ARCHIVE_FORMAT_VERSION,
            "app_version": "99.0.0",
            "schema_version": "9999_future",
            "created_at": "2026-01-01T00:00:00+00:00",
        },
    )

    with pytest.raises(ArchiveError):
        app_context.portability.restore(newer)

    assert [item.title for item in app_context.work_items.list_items()] == ["Fix login"]


def test_restore_rejects_a_damaged_database(app_context, tmp_path: Path) -> None:
    archive = tmp_path / "damaged.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(
            MANIFEST_NAME,
            json.dumps(
                {
                    "format_version": ARCHIVE_FORMAT_VERSION,
                    "app_version": "0.1.0",
                    "schema_version": "0001_initial",
                    "created_at": "2026-01-01T00:00:00+00:00",
                }
            ),
        )
        bundle.writestr(DATABASE_NAME, b"this is not a sqlite database")

    with pytest.raises(ArchiveError):
        app_context.portability.restore(archive)


def test_export_json_contains_all_entities(app_context, tmp_path: Path) -> None:
    item = app_context.work_items.create(
        CreateWorkItem(
            title="แก้ระบบล็อกอิน",
            goal="บรรทัดแรก\nบรรทัดที่สอง",
            group_name="งานหลัก",
        )
    )
    checkpoint = app_context.checkpoints.save(
        SaveCheckpoint(
            work_item_id=item.id,
            stopped_at="integration test ยังไม่ผ่าน",
            next_actions="ตรวจ cookie หลัง refresh",
            blockers="token หมดอายุ",
        )
    )
    app_context.references.add(
        AddReference(
            work_item_id=item.id,
            checkpoint_id=checkpoint.id,
            type=ReferenceType.GIT_REPOSITORY,
            label="Repo",
            target=str(tmp_path),
            metadata={"branch": "main", "commit": "abc123"},
        )
    )

    result = app_context.portability.export_json(tmp_path / "export.json")

    assert result.path == tmp_path / "export.json"
    assert result.work_item_count == 1
    assert result.checkpoint_count == 1
    assert result.reference_count == 1

    payload = json.loads(result.path.read_text(encoding="utf-8"))
    assert set(payload) == {
        "export_version",
        "exported_at",
        "app_version",
        "work_items",
        "checkpoints",
        "references",
    }
    assert payload["export_version"] == 1
    assert payload["app_version"] == "0.1.0"
    assert payload["work_items"][0]["title"] == "แก้ระบบล็อกอิน"
    assert payload["work_items"][0]["goal"] == "บรรทัดแรก\nบรรทัดที่สอง"
    assert payload["checkpoints"][0]["next_actions"] == "ตรวจ cookie หลัง refresh"
    assert payload["checkpoints"][0]["status_after_save"] == "active"
    assert payload["references"][0]["metadata"] == {
        "branch": "main",
        "commit": "abc123",
    }
    assert payload["references"][0]["checkpoint_id"] == str(checkpoint.id)


def test_export_adds_json_suffix(app_context, tmp_path: Path) -> None:
    result = app_context.portability.export_json(tmp_path / "export")

    assert result.path.name == "export.json"
    assert result.path.exists()


def test_export_failure_is_reported_as_archive_error(app_context, tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a directory", encoding="utf-8")

    with pytest.raises(ArchiveError):
        app_context.portability.export_json(blocker / "export.json")


def _rewrite_revision(database_path: Path, revision: str) -> None:
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("UPDATE alembic_version SET version_num = ?", (revision,))
        connection.commit()
    finally:
        connection.close()


def test_restore_rejects_manifest_database_revision_mismatch(app_context, tmp_path: Path) -> None:
    _seed(app_context)
    source = app_context.portability.backup(tmp_path / "backup.zip")
    archiver = ZipArchive(app_context.paths.database_path)
    snapshot = tmp_path / "snapshot.db"
    archiver.extract_database(source.path, snapshot)

    # The database claims a revision that is not the one in the manifest.
    _rewrite_revision(snapshot, "9999_future")
    tampered = tmp_path / "tampered.zip"
    manifest = archiver.read_manifest(source.path)
    manifest["schema_version"] = "0001_initial"
    archiver.write_archive(tampered, snapshot, manifest)

    with pytest.raises(ArchiveError, match="does not match"):
        app_context.portability.restore(tampered)

    # Validation failed before the live database was touched.
    assert [item.title for item in app_context.work_items.list_items()] == ["Fix login"]
    assert not app_context.restore_confirmation_pending()


def test_restore_rejects_unknown_revision_even_when_manifest_matches(
    app_context, tmp_path: Path
) -> None:
    _seed(app_context)
    source = app_context.portability.backup(tmp_path / "backup.zip")
    archiver = ZipArchive(app_context.paths.database_path)
    snapshot = tmp_path / "snapshot.db"
    archiver.extract_database(source.path, snapshot)

    _rewrite_revision(snapshot, "9999_future")
    tampered = tmp_path / "tampered.zip"
    manifest = archiver.read_manifest(source.path)
    manifest["schema_version"] = "9999_future"
    archiver.write_archive(tampered, snapshot, manifest)

    with pytest.raises(ArchiveError):
        app_context.portability.restore(tampered)

    assert [item.title for item in app_context.work_items.list_items()] == ["Fix login"]


def test_restore_failure_after_close_requires_restart(
    app_context, tmp_path: Path, monkeypatch
) -> None:
    _seed(app_context)
    archive = app_context.portability.backup(tmp_path / "backup.zip")
    database_path = app_context.paths.database_path
    real_replace = os.replace

    def failing_replace(source: str | Path, destination: str | Path) -> None:
        if Path(destination) == database_path:
            raise PermissionError("locked by antivirus")
        real_replace(source, destination)

    monkeypatch.setattr("nextstep.application.portability.os.replace", failing_replace)

    with pytest.raises(RestoreRequiresRestartError) as error:
        app_context.portability.restore(archive.path)

    assert "Safety backup" in error.value.message

    backups = list(app_context.paths.backups_dir.glob("pre-restore-*.zip"))
    assert len(backups) == 1
    assert backups[0].exists()

    # The previous database is still on disk and readable.
    database = Database.open(database_path)
    try:
        with database.uow() as uow:
            assert [item.title for item in uow.work_items.list_items()] == ["Fix login"]
    finally:
        database.dispose()

    # No marker and no stray temporary database remain.
    assert not app_context.restore_confirmation_pending()
    assert not list(database_path.parent.glob(".nextstep-restore-*"))


def test_restore_confirms_each_reference_separately(app_context, tmp_path: Path) -> None:
    _seed(app_context)
    item = app_context.work_items.list_items()[0]
    first = app_context.references.list_for_work_item(item.id)[0]
    second = app_context.references.add(
        AddReference(
            work_item_id=item.id,
            type=ReferenceType.FOLDER,
            label="Project folder",
            target=str(tmp_path),
        )
    )

    archive = app_context.portability.backup(tmp_path / "backup.zip")
    app_context.portability.restore(archive.path)

    marker = app_context.paths.config_dir / "restored-references.flag"
    payload = json.loads(marker.read_text(encoding="utf-8"))
    assert payload["format_version"] == 1
    assert set(payload["reference_ids"]) == {str(first.id), str(second.id)}

    assert app_context.restore_confirmation_pending()
    assert app_context.reference_requires_confirmation(first.id)
    assert app_context.reference_requires_confirmation(second.id)

    app_context.clear_reference_confirmation(first.id)

    assert not app_context.reference_requires_confirmation(first.id)
    assert app_context.reference_requires_confirmation(second.id)
    assert app_context.restore_confirmation_pending()

    app_context.clear_reference_confirmation(second.id)

    assert not app_context.reference_requires_confirmation(second.id)
    assert not app_context.restore_confirmation_pending()
    assert not marker.exists()


def test_restore_marker_failure_keeps_live_database_open(
    app_context, tmp_path: Path, monkeypatch
) -> None:
    _seed(app_context)
    archive = app_context.portability.backup(tmp_path / "backup.zip")
    original = app_context.work_items.list_items()[0]

    def fail_marker(_reference_ids: list[str]) -> None:
        raise ArchiveError("marker is not writable")

    monkeypatch.setattr(app_context.portability, "_write_restore_marker", fail_marker)

    with pytest.raises(ArchiveError, match="marker is not writable"):
        app_context.portability.restore(archive.path)

    # Restore aborted before close_database(); the existing context still works.
    assert app_context.work_items.get(original.id).title == "Fix login"
    app_context.work_items.create(CreateWorkItem(title="Still writable"))
    assert {item.title for item in app_context.work_items.list_items()} == {
        "Fix login",
        "Still writable",
    }
