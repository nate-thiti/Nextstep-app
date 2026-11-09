"""Load the packaged NextStep application icon."""

from __future__ import annotations

from importlib.resources import as_file, files

from PySide6.QtGui import QIcon


def application_icon() -> QIcon:
    resource = files("nextstep.assets").joinpath("app-icon.ico")
    with as_file(resource) as icon_path:
        return QIcon(str(icon_path))
