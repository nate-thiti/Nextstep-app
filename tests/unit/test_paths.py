from __future__ import annotations

from pathlib import Path

from nextstep.infrastructure.paths import DATA_DIR_ENV_VAR, DataPaths, default_data_root


def test_data_dir_override(monkeypatch, tmp_path: Path) -> None:
    custom_root = tmp_path / "custom-root"
    monkeypatch.setenv(DATA_DIR_ENV_VAR, str(custom_root))

    paths = DataPaths.resolve()

    assert paths.root == custom_root.resolve()
    assert paths.database_path == custom_root.resolve() / "data" / "nextstep.db"


def test_ensure_creates_expected_directories(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(DATA_DIR_ENV_VAR, str(tmp_path / "root"))

    paths = DataPaths.resolve().ensure()

    assert paths.data_dir.is_dir()
    assert paths.backups_dir.is_dir()
    assert paths.logs_dir.is_dir()
    assert paths.config_dir.is_dir()


def test_default_root_is_the_nextstep_app_folder(monkeypatch) -> None:
    monkeypatch.delenv(DATA_DIR_ENV_VAR, raising=False)

    assert default_data_root().name == "NextStep"
