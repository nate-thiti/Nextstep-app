"""Desktop entry point."""

from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from nextstep.desktop.app_icon import application_icon
from nextstep.desktop.context import build_context
from nextstep.desktop.main_window import MainWindow
from nextstep.desktop.theme import apply_theme
from nextstep.infrastructure.logging_setup import configure_logging
from nextstep.infrastructure.paths import DataPaths

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    app = QApplication(sys.argv if argv is None else argv)
    app.setApplicationName("NextStep")
    app.setApplicationDisplayName("NextStep")
    app.setOrganizationName("NextStep")
    app.setWindowIcon(application_icon())

    paths = DataPaths.resolve().ensure()
    log_path = configure_logging(paths.logs_dir)

    try:
        ctx = build_context(paths)
    except Exception:
        logger.exception("startup failed")
        QMessageBox.critical(
            None,
            "NextStep could not start",
            "NextStep could not open its database.\n\n"
            f"Data folder: {paths.root}\n"
            f"Log file: {log_path}",
        )
        return 1

    apply_theme(app, ctx.settings.get_theme())
    window = MainWindow(ctx)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
