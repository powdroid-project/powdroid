"""PowDroid GUI: a single window with Home → Record → Report pages."""

import logging
import os
import sys

from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR, QSize, Qt
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QScrollArea, QStackedWidget,
    QToolButton, QVBoxLayout, QWidget,
)

from core import __version__, adb, config, debug, session
from gui import theme, workers
from gui.i18n import set_language, t
from gui.pages.home import HomePage
from gui.pages.record import RecordPage

logger = logging.getLogger("powdroid.gui")


def start_debug_log(settings):
    """Write the debug log in the output folder (raises OSError if it cannot be written)."""
    debug.enable(debug.default_path(settings["output_dir"]))
    logger.info("Qt %s, PyQt %s, platform %s; settings: %s",
                QT_VERSION_STR, PYQT_VERSION_STR, QApplication.platformName(), settings)


class MainWindow(QMainWindow):
    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.report = None  # created on first use: it loads matplotlib
        self.checks = None  # the configuration check results, once known
        self.setWindowTitle("PowDroid")
        self.setWindowIcon(QIcon(theme.resource("powdroid_logo.png")))
        self.setMinimumSize(520, 720)
        self.resize(980, 860)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(self._header())

        self.stack = QStackedWidget()
        self.home = HomePage(settings["output_dir"])
        self.record = RecordPage()
        scroll = QScrollArea()
        scroll.setWidget(self.home)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for page in (scroll, self.record):
            self.stack.addWidget(page)
        self.home_page = scroll
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self.home.start_requested.connect(self._prepare)
        self.home.open_report_requested.connect(self._open_report)
        self.home.output_dir_changed.connect(lambda p: self._save(output_dir=p))
        self.home.debug_toggled.connect(self._toggle_debug)
        self.home.set_debug_log(debug.log_path())
        self.record.finished.connect(self._show_report)
        self.record.cancelled.connect(self._go_home)

        self.watcher = workers.DeviceWatcher(self)
        self.watcher.device_changed.connect(self._device_changed)
        self.record.collecting.connect(self.watcher.set_paused)
        self.watcher.start()
        self._run(workers.run_checks, on_success=self._checks_done)

    def _header(self):
        bar = QHBoxLayout()
        bar.setContentsMargins(24, 16, 16, 8)
        logo = QLabel()
        logo.setPixmap(QPixmap(theme.resource("PowDroid_Vertical.png")).scaledToHeight(
            36, Qt.TransformationMode.SmoothTransformation))
        bar.addWidget(logo)
        bar.addStretch()
        self.theme_button = QToolButton()
        self.theme_button.setIconSize(QSize(22, 22))
        self.theme_button.setToolTip(t("app.theme_tooltip"))
        self.theme_button.clicked.connect(self._toggle_theme)
        about = QToolButton()
        about.setText("?")
        about.setToolTip(t("app.about_tooltip"))
        about.setFixedSize(32, 32)
        about.clicked.connect(self._about)
        bar.addWidget(self.theme_button)
        bar.addWidget(about)
        return bar

    # -- helpers ----------------------------------------------------------

    def _run(self, func, *args, on_success=None, on_failure=None):
        task = workers.Task(func, *args, parent=self)
        if on_success:
            task.succeeded.connect(on_success)
        if on_failure:
            task.failed.connect(on_failure)
        task.start()

    def _save(self, **changes):
        self.settings.update(changes)
        config.save(self.settings)

    def apply_theme(self):
        name = self.settings["theme"]
        QApplication.instance().setStyleSheet(theme.stylesheet(name))
        # The icon shows the theme you switch to.
        self.theme_button.setIcon(QIcon(theme.resource("light.png" if name == "dark" else "dark.png")))
        if self.report is not None:
            self.report.set_theme(name)

    def _toggle_theme(self):
        self._save(theme="light" if self.settings["theme"] == "dark" else "dark")
        self.apply_theme()

    def _checks_done(self, results):
        self.checks = results
        self._log_checks()
        self.home.set_checks(results)

    def _log_checks(self):
        for r in self.checks or []:
            logger.info("Check %s: %s, %s%s", r.name, "OK" if r.success else "FAILED", r.message,
                        f" ({r.hint})" if r.hint and not r.success else "")

    def _toggle_debug(self, on):
        self._save(debug=on)
        if not on:
            debug.disable()
        else:
            try:
                start_debug_log(self.settings)
            except OSError as e:
                self._save(debug=False)
                QMessageBox.warning(self, "PowDroid", t("home.debug_error", error=e))
            else:  # what happened before the log was started
                self._log_checks()
                logger.info("Current device: %s", self.home.device)
        self.home.set_debug_log(debug.log_path())

    def _about(self):
        QMessageBox.about(self, t("app.about_title"), t("app.about_text", version=__version__))

    # -- navigation -------------------------------------------------------

    def _device_changed(self, device):
        self.home.set_device(device)
        self.record.on_device_changed(device)

    def _prepare(self):
        device = self.home.device
        if device is None or not device.ready:
            return
        self.home.set_busy(True)
        logger.info("Preparing %s", device.serial)

        def prepared(_):
            self.home.set_busy(False)
            self.record.begin(device, self.settings["output_dir"])
            self.stack.setCurrentWidget(self.record)
            # The device may already be unplugged by the time preparation finished.
            self.record.on_device_changed(self.home.device)

        def failed(message):
            self.home.set_busy(False)
            QMessageBox.warning(self, "PowDroid", message)

        self._run(adb.prepare, device.serial, on_success=prepared, on_failure=failed)

    def _open_report(self, csv_path):
        """Load a CSV chosen on the home page (in the background: it can be large)."""
        def failed(message):
            QMessageBox.warning(self, t("report.title"), t("report.load_error", error=message))

        self._run(session.load, csv_path, on_success=self._show_report, on_failure=failed)

    def _show_report(self, result):
        if self.report is None:
            from gui.pages.report import ReportPage

            self.report = ReportPage()
            self.report.new_recording.connect(self._go_home)
            self.stack.addWidget(self.report)
        self.report.show_result(result, self.settings["theme"])
        self.stack.setCurrentWidget(self.report)

    def _go_home(self):
        self.stack.setCurrentWidget(self.home_page)

    def closeEvent(self, event):
        if self.record.is_busy():
            answer = QMessageBox.question(self, "PowDroid", t("app.busy_quit"))
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        logger.info("Quitting")
        self.watcher.stop()
        if any(task.isRunning() for task in self.findChildren(workers.Task)):
            # An adb command (e.g. the batterystats dump) cannot be interrupted cleanly: leave now.
            logger.warning("Quitting while a task is still running")
            debug.disable()
            os._exit(0)
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PowDroid")
    settings = config.load()
    if settings["debug"]:
        try:
            start_debug_log(settings)  # before anything else, to log startup problems too
        except OSError:
            pass  # the home page shows that no log is written
    theme.load_fonts(app)
    set_language(settings.get("language", "en"))
    window = MainWindow(settings)
    window.apply_theme()
    window.show()
    return app.exec()
