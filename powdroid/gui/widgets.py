"""Small widgets shared by the pages."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout

from powdroid.gui.theme import set_role


def label(text="", role=None, wrap=False, align=None):
    widget = QLabel(text)
    if role:
        set_role(widget, role)
    widget.setWordWrap(wrap)
    if align is not None:
        widget.setAlignment(align)
    return widget


def card(*widgets):
    """A rounded panel stacking the given widgets; returns (frame, layout)."""
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(6)
    for w in widgets:
        layout.addWidget(w)
    return frame, layout


class ElidedLabel(QLabel):
    """A one-line label that elides its text in the middle to fit its width (full text as tooltip)."""

    def __init__(self, text="", role=None):
        super().__init__()
        if role:
            set_role(self, role)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setFullText(text)

    def setFullText(self, text):
        self.full_text = text
        self.setToolTip(text)
        self._elide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()

    def _elide(self):
        self.setText(self.fontMetrics().elidedText(
            self.full_text, Qt.TextElideMode.ElideMiddle, max(self.width(), 50)))
