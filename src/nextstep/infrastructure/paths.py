"""Windows data locations (MVP_SPEC section 12).

Never build these paths from a user name; use the Known Folder API through
platformdirs. ``NEXTSTEP_DATA_DIR`` exists only for development and tests.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import platformdirs

DATA_DIR_ENV_VAR = "NEXTSTEP_DATA_DIR"
APP_NAME = "NextStep"


def default_data_root() -> Path:
    """Resolve ``%LOCALAPPDATA%\\NextStep`` (or the dev override)."""
    override = os.environ.get(DATA_DIR_ENV_VAR)
    if override:
        return Path(override).expanduser().resolve()
    return Path(platformdirs.user_data_path(APP_NAME, appauthor=False, roaming=False)).resolve()


@dataclass(frozen=True)
class DataPaths:
    root: Path

    @classmethod
    def resolve(cls, root: Path | None = None) -> DataPaths:
        return cls(root if root is not None else default_data_root())

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "nextstep.db"

    @property
    def backups_dir(self) -> Path:
        return self.root / "backups"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    @property
    def config_dir(self) -> Path:
        return self.root / "config"

    def ensure(self) -> DataPaths:
        for directory in (
            self.data_dir,
            self.backups_dir,
            self.logs_dir,
            self.config_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        return self
