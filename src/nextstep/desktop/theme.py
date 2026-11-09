"""Light and dark stylesheets for the desktop UI."""

from __future__ import annotations

from string import Template

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

LIGHT: dict[str, str] = {
    "bg": "#f4f5f7",
    "panel": "#ffffff",
    "panel_alt": "#f8f9fb",
    "text": "#1f2328",
    "muted": "#6b7280",
    "border": "#dcdfe4",
    "accent": "#1d6b55",
    "accent_hover": "#155444",
    "accent_text": "#ffffff",
    "accent_soft": "#e3f2ec",
    "accent_border": "#b5dacd",
    "hover": "#eef1f5",
    "selection": "#dcefe8",
    "danger": "#dc2626",
    "danger_soft": "#fef2f2",
    "warning": "#b45309",
    "warning_bg": "#fffbeb",
    "warning_border": "#fde68a",
    "badge_active_bg": "#dcefe8",
    "badge_active_fg": "#155444",
    "badge_paused_bg": "#fef3c7",
    "badge_paused_fg": "#92400e",
    "badge_completed_bg": "#dcfce7",
    "badge_completed_fg": "#166534",
    "badge_archived_bg": "#e5e7eb",
    "badge_archived_fg": "#4b5563",
}

DARK: dict[str, str] = {
    "bg": "#16181c",
    "panel": "#1f2227",
    "panel_alt": "#24282e",
    "text": "#e6e8eb",
    "muted": "#9aa1ab",
    "border": "#343841",
    "accent": "#67c7a9",
    "accent_hover": "#84d4bb",
    "accent_text": "#0c1d18",
    "accent_soft": "#173b31",
    "accent_border": "#285d4e",
    "hover": "#2a2f36",
    "selection": "#244a3e",
    "danger": "#f87171",
    "danger_soft": "#3a1f22",
    "warning": "#fbbf24",
    "warning_bg": "#3a2f14",
    "warning_border": "#6b5316",
    "badge_active_bg": "#173b31",
    "badge_active_fg": "#8fdbc3",
    "badge_paused_bg": "#3f2f10",
    "badge_paused_fg": "#fcd34d",
    "badge_completed_bg": "#14351f",
    "badge_completed_fg": "#86efac",
    "badge_archived_bg": "#2a2e35",
    "badge_archived_fg": "#cbd5e1",
}

_TEMPLATE = Template(
    """
QWidget {
    background: $bg;
    color: $text;
    font-family: "Segoe UI Variable", "Segoe UI";
    font-size: 13px;
}
QLabel {
    background: transparent;
}
QCheckBox {
    background: transparent;
    spacing: 8px;
    padding: 4px 2px;
}
QCheckBox:disabled {
    color: $muted;
}
QCheckBox[role="toggleTitle"] {
    color: $text;
    font-weight: 600;
    padding: 2px 0;
}
QCheckBox[class="permissionOption"] {
    padding: 5px 2px;
}
QMainWindow, QDialog, QMessageBox {
    background: $bg;
}
QToolTip {
    background: $panel;
    color: $text;
    border: 1px solid $border;
    padding: 4px 6px;
}

#Sidebar {
    background: $panel;
    border-right: 1px solid $border;
}
#SidebarTitle {
    font-size: 18px;
    font-weight: 700;
    color: $text;
    padding: 4px 4px 0 4px;
}
#SidebarSection {
    color: $muted;
    font-size: 11px;
    font-weight: 700;
    padding: 12px 6px 4px 6px;
}
#Sidebar QListWidget {
    background: transparent;
    border: none;
    border-radius: 0;
}
#Sidebar QListWidget::item {
    padding: 7px 10px;
    border-radius: 6px;
    margin: 1px 6px;
}
#Sidebar QListWidget::item:selected {
    background: $selection;
    color: $text;
}
#Sidebar QListWidget::item:hover {
    background: $hover;
}

QPushButton {
    background: $panel;
    border: 1px solid $border;
    border-radius: 6px;
    padding: 6px 12px;
}
QPushButton:hover {
    background: $hover;
}
QPushButton:pressed {
    background: $selection;
}
QPushButton:disabled {
    color: $muted;
    background: $panel_alt;
}
QPushButton[class="primary"] {
    background: $accent;
    color: $accent_text;
    border: 1px solid $accent;
    font-weight: 600;
}
QPushButton[class="primary"]:hover {
    background: $accent_hover;
    border-color: $accent_hover;
}
QPushButton[class="danger"] {
    color: $danger;
}
QPushButton[class="link"] {
    background: transparent;
    border: none;
    color: $accent;
    padding: 2px 4px;
    text-align: left;
}
QPushButton[class="link"]:hover {
    color: $accent_hover;
}
QPushButton[class="chip"] {
    background: $panel_alt;
    border: 1px solid $border;
    border-radius: 12px;
    padding: 4px 10px;
    font-size: 12px;
}
QPushButton[class="chip"]:checked {
    background: $accent_soft;
    color: $accent;
    border-color: $accent_border;
    font-weight: 600;
}

QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QDateEdit, QTimeEdit {
    background: $panel;
    border: 1px solid $border;
    border-radius: 6px;
    padding: 6px 8px;
    selection-background-color: $selection;
    selection-color: $text;
}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus,
QDateEdit:focus, QTimeEdit:focus {
    border: 1px solid $accent;
}
QLineEdit[invalid="true"], QPlainTextEdit[invalid="true"], QComboBox[invalid="true"] {
    border: 1px solid $danger;
}
#CommandSearch {
    min-height: 32px;
    font-size: 15px;
    padding: 8px 12px;
    border-radius: 9px;
}
#CommandResults {
    border-radius: 10px;
}
#CommandResults::item {
    padding: 0;
    margin: 2px 4px;
    border-radius: 7px;
}
QLabel[role="paletteTitle"] {
    color: $text;
    font-weight: 600;
}
QLabel[role="paletteCategory"] {
    color: $accent;
    font-size: 9px;
    font-weight: 700;
}
QLabel[role="shortcut"] {
    background: $panel_alt;
    color: $muted;
    border: 1px solid $border;
    border-radius: 5px;
    padding: 2px 6px;
    font-size: 11px;
}
QComboBox {
    border-radius: 10px;
    combobox-popup: 0;
    padding: 6px 34px 6px 10px;
}
QComboBox:hover {
    border-color: $accent_border;
    background: $accent_soft;
}
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    background: $panel_alt;
    border: none;
    border-left: 1px solid $border;
    border-top-right-radius: 9px;
    border-bottom-right-radius: 9px;
    width: 28px;
}
QComboBox QAbstractItemView {
    background: $panel;
    border: none;
    border-radius: 10px;
    padding: 5px;
    outline: none;
    selection-background-color: $selection;
    selection-color: $text;
}
QComboBox QAbstractItemView::item {
    min-height: 28px;
    border-radius: 6px;
    margin: 1px;
    padding: 4px 8px;
}
QComboBox QAbstractItemView::item:hover {
    background: $hover;
    color: $text;
}
QComboBoxPrivateContainer {
    background: transparent;
    border: none;
}
QDateEdit, QTimeEdit {
    min-height: 28px;
    padding: 6px 10px;
}
QDateEdit::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 30px;
    border: none;
    border-left: 1px solid $border;
    background: $panel_alt;
}
QCalendarWidget {
    background: $panel;
    border: 1px solid $border;
    border-radius: 10px;
}
QCalendarWidget QWidget#qt_calendar_navigationbar {
    background: $panel_alt;
    border-bottom: 1px solid $border;
}
QCalendarWidget QToolButton {
    background: transparent;
    border: none;
    color: $text;
    font-weight: 600;
    padding: 6px;
}
QCalendarWidget QToolButton:hover {
    background: $hover;
}
QCalendarWidget QSpinBox {
    background: $panel;
    color: $text;
    border: 1px solid $border;
    border-radius: 6px;
    padding: 4px 8px;
}
QCalendarWidget QTableView {
    background: $panel;
    alternate-background-color: $panel;
    border: none;
    outline: none;
    selection-background-color: $accent;
    selection-color: $accent_text;
}

QTableWidget, QListWidget, QTreeWidget {
    background: $panel;
    border: 1px solid $border;
    border-radius: 8px;
    alternate-background-color: $panel_alt;
    gridline-color: $border;
    outline: none;
}
QTableWidget::item, QListWidget::item {
    padding: 6px;
}
QTableWidget::item:selected, QListWidget::item:selected {
    background: $selection;
    color: $text;
}
QHeaderView::section {
    background: $panel_alt;
    color: $muted;
    border: none;
    border-bottom: 1px solid $border;
    padding: 8px;
    font-weight: 600;
}
QTableCornerButton::section {
    background: $panel_alt;
    border: none;
}

QScrollArea, QScrollArea > QWidget > QWidget {
    background: transparent;
    border: none;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: $border;
    border-radius: 5px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background: $muted;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
    height: 0;
}
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 2px;
}
QScrollBar::handle:horizontal {
    background: $border;
    border-radius: 5px;
    min-width: 24px;
}

QGroupBox {
    border: 1px solid $border;
    border-radius: 8px;
    margin-top: 12px;
    padding: 12px 10px 8px 10px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: $muted;
}

QLabel[role="h1"] {
    font-size: 22px;
    font-weight: 700;
}
QLabel[role="h2"] {
    font-size: 15px;
    font-weight: 600;
}
QLabel[role="muted"] {
    color: $muted;
}
QLabel[role="error"] {
    color: $danger;
    font-size: 12px;
}
QLabel[role="section"] {
    color: $muted;
    font-size: 11px;
    font-weight: 700;
}
QLabel[status="active"] {
    background: $badge_active_bg;
    color: $badge_active_fg;
    border-radius: 10px;
    padding: 2px 10px;
    font-weight: 600;
    font-size: 11px;
}
QLabel[status="paused"] {
    background: $badge_paused_bg;
    color: $badge_paused_fg;
    border-radius: 10px;
    padding: 2px 10px;
    font-weight: 600;
    font-size: 11px;
}
QLabel[status="completed"] {
    background: $badge_completed_bg;
    color: $badge_completed_fg;
    border-radius: 10px;
    padding: 2px 10px;
    font-weight: 600;
    font-size: 11px;
}
QLabel[status="archived"] {
    background: $badge_archived_bg;
    color: $badge_archived_fg;
    border-radius: 10px;
    padding: 2px 10px;
    font-weight: 600;
    font-size: 11px;
}

QFrame[role="card"] {
    background: $panel;
    border: 1px solid $border;
    border-radius: 10px;
}
QFrame[role="empty"] {
    background: $accent_soft;
    border: 1px solid $accent_border;
    border-radius: 10px;
}
QFrame[role="goal"] {
    background: $panel;
    border: 1px solid $border;
    border-radius: 10px;
}
QFrame[role="permissions"] {
    background: $panel_alt;
    border: 1px solid $border;
    border-radius: 8px;
}
QLabel[role="eyebrow"] {
    color: $accent;
    font-size: 10px;
    font-weight: 700;
}
QLabel[role="goalText"] {
    color: $text;
    font-size: 16px;
    font-weight: 600;
}
QFrame[role="next"] {
    background: $accent_soft;
    border: 1px solid $accent_border;
    border-radius: 10px;
}
QFrame[role="warning"] {
    background: $warning_bg;
    border: 1px solid $warning_border;
    border-radius: 10px;
}
QFrame[role="separator"] {
    background: $border;
    max-height: 1px;
    border: none;
}

QStatusBar {
    color: $muted;
    background: $panel;
    border-top: 1px solid $border;
}
QMenu {
    background: $panel;
    border: 1px solid $border;
    padding: 4px;
}
QMenu::item {
    padding: 6px 20px;
    border-radius: 4px;
}
QMenu::item:selected {
    background: $selection;
    color: $text;
}
"""
)


def stylesheet(theme: str) -> str:
    palette = DARK if theme == "dark" else LIGHT
    return _TEMPLATE.substitute(palette)


def resolve_theme(app: QApplication, theme: str) -> str:
    if theme in ("light", "dark"):
        return theme
    scheme = app.styleHints().colorScheme()
    return "dark" if scheme == Qt.ColorScheme.Dark else "light"


def apply_theme(app: QApplication, theme: str) -> str:
    resolved = resolve_theme(app, theme)
    app.setStyle("Fusion")
    app.setStyleSheet(stylesheet(resolved))
    return resolved
