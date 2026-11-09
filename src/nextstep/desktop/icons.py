"""Small theme-friendly icons drawn with Qt primitives."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap


def work_indicator_icon(*, pinned: bool, reminder: bool) -> QIcon:
    """Return a compact pin/clock icon without relying on emoji fonts."""
    if not pinned and not reminder:
        return QIcon()

    width = 34 if pinned and reminder else 18
    pixmap = QPixmap(QSize(width, 18))
    pixmap.fill(QColor("transparent"))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor("#1d6b55"), 1.7))

    x = 0.0
    if pinned:
        painter.drawEllipse(QRectF(x + 5, 2.5, 7, 7))
        painter.drawLine(QPointF(x + 8.5, 9.5), QPointF(x + 8.5, 15))
        painter.drawLine(QPointF(x + 5.5, 9), QPointF(x + 11.5, 9))
        x += 16
    if reminder:
        painter.drawEllipse(QRectF(x + 2.5, 2.5, 13, 13))
        painter.drawLine(QPointF(x + 9, 5.5), QPointF(x + 9, 9.5))
        painter.drawLine(QPointF(x + 9, 9.5), QPointF(x + 12, 11))

    painter.end()
    return QIcon(pixmap)
