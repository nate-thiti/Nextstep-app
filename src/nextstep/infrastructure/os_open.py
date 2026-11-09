"""OS adapter for opening reference targets (MVP_SPEC section 8)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

from nextstep.domain.entities import WorkReference
from nextstep.domain.enums import ReferenceType


def reference_target_exists(reference: WorkReference) -> bool:
    """URLs are not checked; local paths are."""
    if reference.type is ReferenceType.URL:
        return True
    return Path(reference.target).exists()


def open_reference(reference: WorkReference) -> bool:
    """Open a reference with the OS default application.

    Returns ``False`` when the platform refuses to launch the target.
    """
    if reference.type is ReferenceType.URL:
        return QDesktopServices.openUrl(QUrl(reference.target))
    return QDesktopServices.openUrl(QUrl.fromLocalFile(reference.target))


def open_path(path: Path) -> bool:
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
