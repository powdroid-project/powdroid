"""Home page: configuration checks, device status and the start button."""

from html import escape

from PyQt6.QtCore import QSignalBlocker, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QPushButton, QVBoxLayout, QWidget,
)

from powdroid.core import adb, pending
from powdroid.gui.i18n import t
from powdroid.gui.theme import set_role
from powdroid.gui.widgets import ElidedLabel, card, label


# Title and hint keys (home.*) shown for a device that is not ready, by its adb state.
STATE_TEXTS = {
    "unauthorized": ("unauthorized", "unauthorized_hint"),
    "no permissions": ("no_permissions", "no_permissions_hint"),
    "offline": ("offline", "offline_hint"),
}


def device_text(device):
    """The name of a device in the device list."""
    if not device.ready:
        return f"{device.serial} ({device.state})"
    kind = t("home.emulator") if device.emulator else t("home.wifi") if device.wireless else ""
    return f"{device.label} ({kind})" if kind else device.label


class HomePage(QWidget):
    start_requested = pyqtSignal()
    collect_pending_requested = pyqtSignal(dict)  # a core/pending.py session
    discard_pending_requested = pyqtSignal(dict)
    open_report_requested = pyqtSignal(str)
    output_dir_changed = pyqtSignal(str)
    debug_toggled = pyqtSignal(bool)
    perfetto_toggled = pyqtSignal(bool)

    def __init__(self, output_dir, perfetto=True, parent=None):
        super().__init__(parent)
        self.device = None  # the selected device
        self.devices = []  # every device adb lists
        self.checks_ok = False
        self.busy = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 8, 24, 24)
        layout.setSpacing(14)

        # Sessions recorded but not collected (PowDroid was closed or crashed meanwhile)
        self.pending_box = QVBoxLayout()
        layout.addLayout(self.pending_box)

        # Device status, with a choice when several devices are connected
        self.device_choice = QComboBox()
        self.device_choice.currentIndexChanged.connect(self._device_chosen)
        self.device_name = label(role="heading")
        self.device_name.setTextFormat(Qt.TextFormat.PlainText)  # from the phone
        self.device_detail = label(role="muted", wrap=True)
        self.device_detail.setTextFormat(Qt.TextFormat.PlainText)
        wifi_button = QPushButton(t("home.wifi_button"))
        wifi_button.setToolTip(t("home.wifi_tooltip"))
        wifi_button.clicked.connect(self._connect_wifi)
        wifi_row = QHBoxLayout()
        wifi_row.addStretch()
        wifi_row.addWidget(wifi_button)
        device_card, device_layout = card(label(t("home.device_title"), "stat-label"), self.device_choice,
                                          self.device_name, self.device_detail)
        device_layout.addLayout(wifi_row)
        layout.addWidget(device_card)
        self.wanted_serial = None  # a device to select once adb lists it (just connected over Wi-Fi)

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

        # Perfetto
        self.perfetto_check = QCheckBox(t("home.perfetto"))
        self.perfetto_check.setToolTip(t("home.perfetto_tooltip"))
        self.perfetto_check.setChecked(perfetto)
        self.perfetto_check.toggled.connect(self.perfetto_toggled)
        layout.addWidget(self.perfetto_check)

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

        self.set_devices([])

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
            if result.warning:
                html += f"<br>⚠ {escape(result.warning)}"
            text = label(html, wrap=True)
            self.checks_grid.addWidget(mark, i, 0, Qt.AlignmentFlag.AlignTop)
            self.checks_grid.addWidget(text, i, 1)
        self.checks_ok = all(r.success for r in results)
        self.checks_status.setVisible(not self.checks_ok)
        self.checks_status.setText(t("checks.failed"))
        set_role(self.checks_status, "error")
        self._update_start()

    def set_pending(self, sessions):
        """Offer to collect or discard the sessions recorded but not collected."""
        while self.pending_box.count():
            widget = self.pending_box.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        for data in sessions:
            text = label(t("home.pending", session=pending.describe(data)), "warning", wrap=True)
            text.setTextFormat(Qt.TextFormat.PlainText)
            collect, discard = QPushButton(t("home.pending_collect")), QPushButton(t("home.pending_discard"))
            set_role(collect, "primary")
            collect.setToolTip(t("home.pending_collect_tooltip"))
            collect.clicked.connect(lambda _, d=data: self.collect_pending_requested.emit(d))
            discard.clicked.connect(lambda _, d=data: self.discard_pending_requested.emit(d))
            buttons = QHBoxLayout()
            buttons.addStretch()
            buttons.addWidget(discard)
            buttons.addWidget(collect)
            frame, frame_layout = card(text)
            frame_layout.addLayout(buttons)
            self.pending_box.addWidget(frame)

    def set_devices(self, devices):
        """Show the devices adb lists; the selected one stays selected while it is connected."""
        selected = self.device.serial if self.device else None
        if self.wanted_serial in [d.serial for d in devices]:
            selected, self.wanted_serial = self.wanted_serial, None
        self.devices = devices
        if selected not in [d.serial for d in devices]:
            selected = getattr(adb.preferred(devices), "serial", None)
        with QSignalBlocker(self.device_choice):
            self.device_choice.clear()
            for device in devices:
                self.device_choice.addItem(device_text(device), device.serial)
            self.device_choice.setCurrentIndex(self.device_choice.findData(selected))
        self.device_choice.setVisible(len(devices) > 1)
        self._show_device(next((d for d in devices if d.serial == selected), None))

    def _connect_wifi(self):
        from powdroid.gui.pages.wifi import WifiDialog

        dialog = WifiDialog(self.device, self)
        dialog.connected.connect(self._wifi_connected)
        dialog.exec()

    def _wifi_connected(self, serial):
        """Select the phone connected over Wi-Fi, now or once the device list shows it."""
        if serial in [d.serial for d in self.devices]:
            self.device_choice.setCurrentIndex(self.device_choice.findData(serial))
        else:
            self.wanted_serial = serial

    def _device_chosen(self, index):
        self._show_device(self.devices[index] if 0 <= index < len(self.devices) else None)

    def _show_device(self, device):
        self.device = device
        if device is None:
            self.device_name.setText(t("home.no_device"))
            self.device_detail.setText(t("home.no_device_hint"))
        elif not device.ready:
            title, hint = STATE_TEXTS.get(device.state, ("not_ready", "not_ready_hint"))
            self.device_name.setText(t(f"home.{title}", state=device.state))
            self.device_detail.setText(t(f"home.{hint}"))
        else:
            self.device_name.setText(device_text(device))
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
