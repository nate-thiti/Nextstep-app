"""BUG-001: migrations must work from an installed package, not the source tree.

The wheel build itself is verified in CI before tests run. Building a wheel from
inside ``uv run pytest`` deadlocks on the uv cache lock, so this test recreates
the installed layout by copying only the package tree into a directory outside
the repository and importing it with ``PYTHONPATH``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = PROJECT_ROOT / "src" / "nextstep"

_RUNNER = """\
from pathlib import Path

from alembic import command

import nextstep
from nextstep.infrastructure.migrations import (
    alembic_config,
    current_revision,
    head_revision,
    upgrade_to_head,
)

expected = (Path.cwd().parent / "installed" / "nextstep").resolve()
assert Path(nextstep.__file__).resolve().is_relative_to(expected), nextstep.__file__

root = Path.cwd()
database_path = root / "data" / "nextstep.db"
backups_dir = root / "backups"

backup = upgrade_to_head(database_path, backups_dir)
assert backup is None
config = alembic_config(database_path)
head = head_revision(config)
assert head is not None
assert current_revision(database_path) == head

# Upgrade an older database through the installed package as well.
command.downgrade(config, "base")
assert current_revision(database_path) is None
backup = upgrade_to_head(database_path, backups_dir)
assert backup is not None and backup.exists()
assert current_revision(database_path) == head

print("ok")
"""


def test_migrations_run_from_an_installed_package_outside_the_repo(
    tmp_path: Path,
) -> None:
    installed = tmp_path / "installed"
    installed.mkdir()
    shutil.copytree(
        PACKAGE_ROOT,
        installed / "nextstep",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )

    assert (installed / "nextstep" / "migrations" / "env.py").is_file()
    assert (installed / "nextstep" / "migrations" / "versions" / "0001_initial.py").is_file()
    assert (installed / "nextstep" / "migrations" / "script.py.mako").is_file()
    assert (installed / "nextstep" / "assets" / "app-icon.png").is_file()
    assert (installed / "nextstep" / "assets" / "app-icon.ico").is_file()

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    runner = workspace / "run.py"
    runner.write_text(_RUNNER, encoding="utf-8")

    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(installed)
    environment.pop("PYTHONHOME", None)

    result = subprocess.run(
        [sys.executable, str(runner)],
        cwd=workspace,
        env=environment,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip().splitlines()[-1] == "ok"
    assert (workspace / "data" / "nextstep.db").exists()
