"""Home page: configuration checks, device status and the start button."""

from html import escape

from PyQt6.QtCore import QSignalBlocker, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox, QFileDialog, QGridLayout, QHBoxLayout, QPushButton, QVBoxLayout, QWidget,
)

from gui.i18n import t
from gui.theme import set_role
from gui.widgets import ElidedLabel, card, label


class HomePage(QWidget):
    start_requested = pyqtSignal()
    open_report_requested = pyqtSignal(str)
    output_dir_changed = pyqtSignal(str)
    debug_toggled = pyqtSignal(bool)

    def __init__(self, output_dir, parent=None):
        super().__init__(parent)
        self.device = None
        self.checks_ok = False
        self.busy = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 8, 24, 24)
        layout.setSpacing(14)

        # Device status
        self.device_name = label(role="heading")
        self.device_detail = label(role="muted", wrap=True)
        device_card, _ = card(label(t("home.device_title"), "stat-label"), self.device_name, self.device_detail)
        layout.addWidget(device_card)

        # Configuration checks
        self.checks_grid = QGridLayout()
        self.checks_grid.setHorizontalSpacing(10)
        self.checks_grid.setColumnStretch(1, 1)
        self.checks_status = label(t("checks.running"), "muted", wrap=True)
        checks_card, checks_layout = card(label(t("checks.title"), "stat-label"))
        checks_layout.addLayout(self.checks_grid)
        checks_layout.addWidget(self.checks_status)
        layout.addWidget(checks_card)

        # Instructions
        instructions = label(t("home.instructions"), wrap=True)
        instructions.setTextFormat(Qt.TextFormat.RichText)
        instructions_card, _ = card(label(t("home.instructions_title"), "heading"), instructions)
        layout.addWidget(instructions_card)

        layout.addStretch()

        # Output folder
        self.output_label = ElidedLabel(role="muted")
        change = QPushButton(t("home.change"))
        change.clicked.connect(self._choose_output_dir)
        row = QHBoxLayout()
        row.addWidget(self.output_label, 1)
        row.addWidget(change)
        layout.addLayout(row)
        self.set_output_dir(output_dir)

        # Debug log
        self.debug_check = QCheckBox(t("home.debug"))
        self.debug_check.setToolTip(t("home.debug_tooltip"))
        self.debug_check.toggled.connect(self.debug_toggled)
        self.debug_label = ElidedLabel(role="muted")
        self.debug_open = QPushButton(t("home.debug_open"))
        self.debug_open.clicked.connect(self._open_debug_folder)
        row = QHBoxLayout()
        row.addWidget(self.debug_check)
        row.addWidget(self.debug_label, 1)
        row.addWidget(self.debug_open)
        layout.addLayout(row)
        self.set_debug_log(None)

        self.start_button = QPushButton(t("home.start"))
        set_role(self.start_button, "primary")
        self.start_button.clicked.connect(self.start_requested)
        layout.addWidget(self.start_button)

        open_button = QPushButton(t("home.open_report"))
        open_button.clicked.connect(self._open_report)
        layout.addWidget(open_button)

        self.set_device(None)

    def set_output_dir(self, path):
        self.output_dir = path
        self.output_label.setFullText(f"{t('home.output_dir')} {path}")

    def _choose_output_dir(self):
        path = QFileDialog.getExistingDirectory(self, t("home.output_dir"), self.output_dir)
        if path:
            self.set_output_dir(path)
            self.output_dir_changed.emit(path)

    def set_debug_log(self, path):
        """Show the debug log being written (None: no log)."""
        self.debug_path = path
        with QSignalBlocker(self.debug_check):
            self.debug_check.setChecked(path is not None)
        self.debug_label.setFullText(str(path or ""))
        self.debug_open.setVisible(path is not None)

    def _open_debug_folder(self):
        if self.debug_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.debug_path.parent)))

    def _open_report(self):
        path, _ = QFileDialog.getOpenFileName(self, t("home.open_report"), self.output_dir, "CSV (*.csv)")
        if path:
            self.open_report_requested.emit(path)

    def set_checks(self, results):
        for i, result in enumerate(results):
            mark = label("✓" if result.success else "✗", "ok" if result.success else "error")
            html = f"<b>{escape(result.name)}</b> — {escape(result.message)}"
            if result.hint and not result.success:
                html += f"<br>{escape(result.hint)}"
            text = label(html, wrap=True)
            self.checks_grid.addWidget(mark, i, 0, Qt.AlignmentFlag.AlignTop)
            self.checks_grid.addWidget(text, i, 1)
        self.checks_ok = all(r.success for r in results)
        self.checks_status.setVisible(not self.checks_ok)
        self.checks_status.setText(t("checks.failed"))
        set_role(self.checks_status, "error")
        self._update_start()

    def set_device(self, device):
        self.device = device
        if device is None:
            self.device_name.setText(t("home.no_device"))
            self.device_detail.setText(t("home.no_device_hint"))
        elif not device.ready:
            self.device_name.setText(t("home.unauthorized"))
            self.device_detail.setText(t("home.unauthorized_hint"))
        else:
            self.device_name.setText(device.label)
            self.device_detail.setText(
                t("home.android", version=device.android_version or "?", serial=device.serial))
        self._update_start()

    def set_busy(self, busy):
        self.busy = busy
        self.start_button.setText(t("home.preparing") if busy else t("home.start"))
        self._update_start()

    def _update_start(self):
        ready = self.device is not None and self.device.ready
        self.start_button.setEnabled(self.checks_ok and ready and not self.busy)
