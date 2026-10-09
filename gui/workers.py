"""Background threads: every adb call runs here, never on the UI thread."""

import traceback

from PyQt6.QtCore import QThread, pyqtSignal

from core import PowDroidError, adb, checks


class DeviceWatcher(QThread):
    """Polls adb once per second and emits device_changed(Device | None) on every change."""

    device_changed = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.paused = False

    def set_paused(self, paused):
        """Stop polling while another long adb command (bugreport) uses the device."""
        self.paused = paused

    def run(self):
        last = ()
        while not self.isInterruptionRequested():
            if not self.paused:
                try:
                    devices = adb.list_devices()
                    key = tuple((d.serial, d.state) for d in devices)
                    if key != last:
                        last = key
                        self.device_changed.emit(adb.find_device(devices=devices))
                except adb.AdbError:
                    pass
            for _ in range(10):
                if self.isInterruptionRequested():
                    return
                self.msleep(100)

    def stop(self):
        self.requestInterruption()
        self.wait()


class Task(QThread):
    """Runs func(*args) in the background and reports its result or error message.

    With with_progress=True, func also receives report=<callable> emitting `progress`.
    """

    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, func, *args, with_progress=False, parent=None):
        super().__init__(parent)
        self.func = func
        self.args = args
        self.with_progress = with_progress
        self.finished.connect(self.deleteLater)

    def run(self):
        try:
            kwargs = {"report": self.progress.emit} if self.with_progress else {}
            result = self.func(*self.args, **kwargs)
        except (PowDroidError, OSError) as e:
            self.failed.emit(str(e))
        except Exception as e:  # A bug: keep the traceback in the console.
            traceback.print_exc()
            self.failed.emit(f"{type(e).__name__}: {e}")
        else:
            self.succeeded.emit(result)


def run_checks():
    return checks.run_all(gui=True)
