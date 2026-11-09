from __future__ import annotations

from PySide6.QtWidgets import QApplication

from nextstep.desktop.app_icon import application_icon


def test_packaged_application_icon_loads(qapp: QApplication) -> None:
    del qapp
    icon = application_icon()

    assert not icon.isNull()
    assert not icon.pixmap(32, 32).isNull()
