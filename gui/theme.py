"""Application-wide light/dark theme: one stylesheet, one palette."""

from pathlib import Path

from PyQt6.QtGui import QFontDatabase, QFont

RESOURCES = Path(__file__).resolve().parent / "ressources"

PALETTES = {
    "dark": {
        "bg": "#1D1D1D",
        "panel": "#282828",
        "panel_alt": "#303030",
        "border": "#3C3C3C",
        "text": "#E2E2E2",
        "muted": "#A0A0A0",
        "accent": "#5374C9",
        "accent_hover": "#4A66B8",
        "success": "#57C18B",
        "warning": "#E8B04B",
        "danger": "#FF6B6B",
        "grid": "#3C3C3C",
    },
    "light": {
        "bg": "#F5F5F7",
        "panel": "#FFFFFF",
        "panel_alt": "#F0F0F2",
        "border": "#D9D9D9",
        "text": "#1D1D1F",
        "muted": "#666666",
        "accent": "#5374C9",
        "accent_hover": "#4A66B8",
        "success": "#2E9E64",
        "warning": "#B7791F",
        "danger": "#C53030",
        "grid": "#E4E4E7",
    },
}

# Colours for the component on/off bands of the power chart.
COMPONENT_COLORS = ["#5374C9", "#57C18B", "#E8B04B", "#D9578E", "#4BB5C1", "#9B6BD3", "#E07A4B"]

STYLESHEET = """
QWidget {{ background: {bg}; color: {text}; font-size: 14px; }}
QLabel {{ background: transparent; }}
QFrame#card {{ background: {panel}; border: 1px solid {border}; border-radius: 8px; }}
QFrame#card QLabel, QFrame#card QCheckBox {{ background: transparent; }}
QLabel[role="title"] {{ font-size: 22px; font-weight: 600; }}
QLabel[role="heading"] {{ font-size: 16px; font-weight: 600; }}
QLabel[role="muted"] {{ color: {muted}; }}
QLabel[role="stat-label"] {{ color: {muted}; font-size: 12px; }}
QLabel[role="stat-value"] {{ font-size: 18px; font-weight: 600; }}
QLabel[role="timer"] {{ font-size: 48px; font-weight: 600; }}
QLabel[role="ok"] {{ color: {success}; }}
QLabel[role="error"] {{ color: {danger}; }}
QLabel[role="warning"] {{ color: {warning}; }}
QPushButton {{
    background: {panel}; color: {text}; border: 1px solid {border};
    border-radius: 6px; padding: 8px 14px;
}}
QPushButton:hover {{ background: {panel_alt}; }}
QPushButton:disabled {{ color: {muted}; }}
QPushButton[role="primary"] {{
    background: {accent}; color: white; border: none; font-weight: 600; padding: 12px 18px;
}}
QPushButton[role="primary"]:hover {{ background: {accent_hover}; }}
QPushButton[role="primary"]:disabled {{ background: {border}; color: {muted}; }}
QPushButton[role="danger"] {{
    background: {danger}; color: white; border: none; font-weight: 600; padding: 12px 18px;
}}
QToolButton {{ background: transparent; border: none; border-radius: 6px; padding: 4px; }}
QToolButton:hover {{ background: {panel_alt}; }}
QLineEdit {{
    background: {panel}; border: 1px solid {border}; border-radius: 6px; padding: 6px 8px;
}}
QLineEdit:focus {{ border-color: {accent}; }}
QTabWidget::pane {{ border: 1px solid {border}; border-radius: 8px; background: {panel}; top: -1px; }}
QTabBar::tab {{
    background: transparent; color: {muted}; padding: 8px 14px; border: none;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{ color: {text}; border-bottom-color: {accent}; }}
QTableView {{
    background: {panel}; alternate-background-color: {panel_alt}; gridline-color: {border};
    border: none; selection-background-color: {accent}; selection-color: white;
}}
QHeaderView::section {{
    background: {panel_alt}; color: {text}; border: none; border-right: 1px solid {border};
    border-bottom: 1px solid {border}; padding: 6px;
}}
QScrollArea {{ border: none; }}
QScrollBar:vertical, QScrollBar:horizontal {{ background: transparent; width: 10px; height: 10px; }}
QScrollBar::handle {{ background: {border}; border-radius: 5px; min-height: 24px; min-width: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QToolTip {{ background: {panel}; color: {text}; border: 1px solid {border}; }}
"""


def colors(name):
    return PALETTES.get(name, PALETTES["dark"])


def stylesheet(name):
    return STYLESHEET.format(**colors(name))


def load_fonts(app):
    """Register the bundled Inter font and make it the application default."""
    family = None
    for path in (RESOURCES / "fonts").glob("*.ttf"):
        font_id = QFontDatabase.addApplicationFont(str(path))
        families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
        family = family or (families[0] if families else None)
    if family:
        app.setFont(QFont(family, 11))


def resource(name):
    return str(RESOURCES / name)


def set_role(widget, role):
    """Set the QSS role of a widget and refresh its style."""
    widget.setProperty("role", role)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
