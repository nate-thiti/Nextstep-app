from __future__ import annotations

import json
import zipfile
from pathlib import Path

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from nextstep.application.dto import CreateWorkItem
from nextstep.desktop.settings_view import SettingsView
from nextstep.domain.errors import RestoreRequiresRestartError


def test_settings_exposes_portability_actions(qtbot, app_context) -> None:
    view = SettingsView(app_context)
    qtbot.addWidget(view)

    assert view.backup_button.text() == "Back up…"
    assert view.restore_button.text() == "Restore…"
    assert view.export_button.text() == "Export JSON…"


def test_settings_changes_default_work_list_view(qtbot, app_context) -> None:
    view = SettingsView(app_context)
    qtbot.addWidget(view)

    assert view.work_list_view.currentData() == "focus"
    view.work_list_view.setCurrentIndex(view.work_list_view.findData("compact"))

    assert app_context.settings.get_work_list_view() == "compact"


def test_backup_button_writes_an_archive(qtbot, app_context, tmp_path: Path, monkeypatch) -> None:
    app_context.work_items.create(CreateWorkItem(title="Task"))
    view = SettingsView(app_context)
    qtbot.addWidget(view)
    destination = tmp_path / "ui-backup.zip"

    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *args, **kwargs: (str(destination), "")),
    )
    monkeypatch.setattr(
        QMessageBox,
        "information",
        staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Ok),
    )

    view.backup_button.click()

    assert destination.exists()
    with zipfile.ZipFile(destination) as bundle:
        assert "manifest.json" in bundle.namelist()
        manifest = json.loads(bundle.read("manifest.json").decode("utf-8"))
    assert manifest["counts"]["work_items"] == 1


def test_export_button_writes_json(qtbot, app_context, tmp_path: Path, monkeypatch) -> None:
    app_context.work_items.create(CreateWorkItem(title="Task"))
    view = SettingsView(app_context)
    qtbot.addWidget(view)
    destination = tmp_path / "ui-export.json"

    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *args, **kwargs: (str(destination), "")),
    )
    monkeypatch.setattr(
        QMessageBox,
        "information",
        staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Ok),
    )

    view.export_button.click()

    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert [item["title"] for item in payload["work_items"]] == ["Task"]


def test_cancelled_dialog_does_nothing(qtbot, app_context, tmp_path: Path, monkeypatch) -> None:
    view = SettingsView(app_context)
    qtbot.addWidget(view)

    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *args, **kwargs: ("", "")),
    )

    view.backup_button.click()

    assert not list(tmp_path.glob("*.zip"))


def test_restore_failure_after_close_asks_to_restart_and_quits(
    qtbot, app_context, monkeypatch
) -> None:
    view = SettingsView(app_context)
    qtbot.addWidget(view)

    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        staticmethod(lambda *args, **kwargs: ("backup.zip", "")),
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Yes),
    )
    critical: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        staticmethod(lambda _parent, _title, text, *a, **k: critical.append(text)),
    )
    monkeypatch.setattr(
        app_context.portability,
        "restore",
        lambda _path: (_ for _ in ()).throw(RestoreRequiresRestartError("replace failed")),
    )
    quit_calls: list[bool] = []
    monkeypatch.setattr(QApplication, "quit", staticmethod(lambda: quit_calls.append(True)))

    view.restore_button.click()

    assert quit_calls == [True]
    assert critical and "replace failed" in critical[0]
    assert "Reopen" in critical[0]
