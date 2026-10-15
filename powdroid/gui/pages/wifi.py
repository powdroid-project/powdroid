"""Dialog connecting a phone over Wi-Fi: switch a USB phone to Wi-Fi, pair it, or connect to it."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy, QVBoxLayout,
)

from powdroid.core import adb
from powdroid.gui import workers
from powdroid.gui.i18n import t
from powdroid.gui.widgets import card, label


class WifiDialog(QDialog):
    connected = pyqtSignal(str)  # the serial of the phone now connected over Wi-Fi

    def __init__(self, device=None, parent=None):
        """device: the selected device, which can be switched to Wi-Fi if it is a ready USB phone."""
        super().__init__(parent)
        self.setWindowTitle(t("wifi.title"))
        self.setMinimumWidth(560)
        self.device = device
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        usb = device is not None and device.ready and not device.wireless and not device.emulator
        self.switch_button = QPushButton(t("wifi.switch"))
        self.switch_button.setEnabled(usb)
        self.switch_button.clicked.connect(self._switch)
        switch_text = label(t("wifi.switch_hint", device=device.label) if usb else t("wifi.switch_unavailable"),
                            "muted", wrap=True)
        switch_text.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(card(label(t("wifi.switch_title"), "heading"), switch_text, self.switch_button)[0])

        self.pair_address = QLineEdit(placeholderText=t("wifi.pair_address"))
        self.pair_code = QLineEdit(placeholderText=t("wifi.pair_code"))
        self.pair_button = QPushButton(t("wifi.pair"))
        self.pair_button.clicked.connect(self._pair)
        fields = QHBoxLayout()
        fields.addWidget(self.pair_address, 2)
        fields.addWidget(self.pair_code, 1)
        fields.addWidget(self.pair_button)
        frame, pair_layout = card(label(t("wifi.pair_title"), "heading"),
                                  label(t("wifi.pair_hint"), "muted", wrap=True))
        pair_layout.addLayout(fields)
        layout.addWidget(frame)

        self.connect_address = QLineEdit(placeholderText=t("wifi.connect_address"))
        self.connect_button = QPushButton(t("wifi.connect"))
        self.connect_button.clicked.connect(self._connect)
        fields = QHBoxLayout()
        fields.addWidget(self.connect_address, 1)
        fields.addWidget(self.connect_button)
        frame, connect_layout = card(label(t("wifi.connect_title"), "heading"),
                                     label(t("wifi.connect_hint"), "muted", wrap=True))
        connect_layout.addLayout(fields)
        layout.addWidget(frame)

        self.status = label(role="muted", wrap=True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)  # quotes adb
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        for text in self.findChildren(QLabel):  # never shorter than their wrapped text
            if text.wordWrap():
                policy = text.sizePolicy()
                policy.setVerticalPolicy(QSizePolicy.Policy.MinimumExpanding)
                text.setSizePolicy(policy)

    def showEvent(self, event):
        super().showEvent(event)
        self.adjustSize()  # tall enough for the wrapped texts at this width

    def _run(self, func, *args, working, done):
        """Run an adb action in the background; done(result) gives the status text."""
        for button in (self.switch_button, self.pair_button, self.connect_button):
            button.setProperty("was_enabled", button.isEnabled())
            button.setEnabled(False)
        self.status.setText(working)
        task = workers.Task(func, *args, parent=self)
        task.succeeded.connect(lambda result: self._finished(done(result)))
        task.failed.connect(self._finished)
        task.start()

    def _finished(self, text):
        for button in (self.switch_button, self.pair_button, self.connect_button):
            button.setEnabled(bool(button.property("was_enabled")))
        self.status.setText(text)

    def _connected(self, serial):
        self.connected.emit(serial)
        return t("wifi.connected", serial=serial)

    def _switch(self):
        self._run(adb.switch_to_wifi, self.device.serial, working=t("wifi.switching"), done=self._connected)

    def _pair(self):
        address, code = self.pair_address.text().strip(), self.pair_code.text().strip()
        if address and code:
            self._run(adb.pair, address, code, working=t("wifi.pairing"),
                      done=lambda out: t("wifi.paired", address=address))

    def _connect(self):
        address = self.connect_address.text().strip()
        if address:
            self._run(adb.connect, address, working=t("wifi.connecting"), done=self._connected)
