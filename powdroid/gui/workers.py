"""Background threads: every adb call runs here, never on the UI thread."""

import logging
import threading
import time
import traceback

from PyQt6.QtCore import QThread, pyqtSignal

from powdroid.core import PowDroidError, adb, checks

logger = logging.getLogger("powdroid.gui")


class DeviceWatcher(QThread):
    """Follows the devices adb lists and emits devices_changed([Device]) on every change.

    It uses `adb track-devices`, which reports a change at once, and polls `adb devices`
    once per second instead when it is not available. Ready devices have their
    manufacturer, model and Android version filled in.
    """

    devices_changed = pyqtSignal(list)
    TRACKING_FAILS_S = 5  # track-devices stopping sooner than this is taken as not available

    def __init__(self, parent=None):
        super().__init__(parent)
        self.paused = False
        self.properties = {}  # serial -> described Device, so getprop runs once per connection
        self.tracker = None
        self.tracking = False  # whether track-devices is used (else polling)
        self.last = None

    def set_paused(self, paused):
        """Stop polling while another long adb command (the batterystats dump) uses the device."""
        self.paused = paused

    def describe(self, devices):
        properties = {}  # of the ready devices only: a device connected again is described again
        for device in devices:
            if device.ready:
                known = properties[device.serial] = self.properties.get(device.serial) or adb.describe(device)
                device.manufacturer, device.model, device.android_version = (
                    known.manufacturer, known.model, known.android_version)
        self.properties = properties
        return devices

    def publish(self, devices):
        key = tuple((d.serial, d.state) for d in devices)
        if key != self.last:
            self.last = key
            self.devices_changed.emit(self.describe(devices))

    def run(self):
        threading.current_thread().name = "DeviceWatcher"  # for the debug log
        while not self.isInterruptionRequested():
            started = time.monotonic()
            self.track()
            if self.isInterruptionRequested():
                return
            if time.monotonic() - started < self.TRACKING_FAILS_S:
                logger.info("adb track-devices is not available: polling the devices every second")
                self.poll()
                return
            self.msleep(1000)  # e.g. the adb server was restarted: track again

    def track(self):
        """Publish the device lists of `adb track-devices` until it stops."""
        try:
            self.tracker = adb.DeviceTracker()
        except (adb.AdbError, OSError) as e:
            logger.info("Cannot run adb track-devices: %s", e)
            return
        if self.isInterruptionRequested():  # stop() came before the tracker existed
            self.tracker.close()
            return
        self.tracking = True
        try:
            for devices in self.tracker:
                self.publish(devices)
        except adb.AdbError:
            pass  # in the debug log
        finally:
            self.tracking = False
            self.tracker.close()

    def poll(self):
        while not self.isInterruptionRequested():
            if not self.paused:
                try:
                    self.publish(adb.list_devices(poll=True))
                except adb.AdbError:
                    pass  # in the debug log
            for _ in range(10):
                if self.isInterruptionRequested():
                    return
                self.msleep(100)

    def stop(self):
        self.requestInterruption()
        tracker = self.tracker
        if tracker is not None:
            tracker.close()  # ends its blocking read
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
        name = getattr(self.func, "__qualname__", repr(self.func))
        threading.current_thread().name = f"Task {name}"  # for the debug log
        logger.debug("Started")
        try:
            kwargs = {"report": self.progress.emit} if self.with_progress else {}
            result = self.func(*self.args, **kwargs)
        except (PowDroidError, OSError) as e:
            logger.error("Failed: %s", e, exc_info=True)
            self.failed.emit(str(e))
        except Exception as e:  # A bug: keep the traceback in the console.
            logger.critical("Crashed", exc_info=True)
            traceback.print_exc()
            self.failed.emit(f"{type(e).__name__}: {e}")
        else:
            logger.debug("Done")
            self.succeeded.emit(result)


def run_checks():
    return checks.run_all(gui=True)
