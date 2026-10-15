"""The GUI driven end to end against tests/fake_adb.py, without a display (Qt offscreen platform)."""

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import set_fake_state, use_fake_adb

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PyQt6.QtWidgets import QApplication, QMessageBox

    import matplotlib  # noqa: F401
except ImportError:  # the CLI needs neither
    QApplication = None


@unittest.skipIf(QApplication is None, "PyQt6 and matplotlib are not installed")
class GuiTest(unittest.TestCase):
    def setUp(self):
        from powdroid.core import config

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.device = self.dir / "device"
        use_fake_adb(self, self.device)
        set_fake_state(self.device, "device")
        for patcher in (mock.patch.object(config, "PATH", self.dir / "settings.json"),
                        mock.patch.object(QMessageBox, "warning", side_effect=self.fail_on_message),
                        mock.patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.app = QApplication.instance() or QApplication([])

    def fail_on_message(self, parent, title, text, *args):
        self.fail(f"Unexpected message box: {text}")

    def wait_until(self, condition, seconds=20, what="the condition"):
        deadline = time.monotonic() + seconds
        while not condition():
            if time.monotonic() > deadline:
                self.fail(f"Timed out waiting for {what}")
            self.app.processEvents()
            time.sleep(0.02)

    def open_window(self, **settings):
        from powdroid.core import config
        from powdroid.gui.app import MainWindow

        window = MainWindow({**config.DEFAULTS, "output_dir": str(self.dir / "out"), **settings})
        window.apply_theme()
        window.show()
        self.addCleanup(window.close)
        return window

    def test_record_and_report(self):
        # An emulator listed first must neither be chosen nor be taken for the recorded phone.
        os.environ["FAKE_ADB_OTHERS"] = "emulator-5554:device"
        window = self.open_window(perfetto=True)
        self.wait_until(lambda: window.home.start_button.isEnabled(), what="the device and checks")
        self.assertEqual(window.home.device.serial, "FAKE123")
        self.assertTrue(window.home.device_choice.isVisibleTo(window))
        self.assertTrue(window.watcher.tracking)  # adb track-devices
        window.home.start_button.click()
        self.wait_until(lambda: window.stack.currentWidget() is window.record, what="the record page")
        self.assertIsNotNone(window.record.preparation.trace)

        set_fake_state(self.device, None)  # unplugged: recording starts
        self.wait_until(lambda: window.record.stop_button.isVisible(), what="recording")
        time.sleep(1.5)
        window.record.stop_button.click()
        set_fake_state(self.device, "device")  # plugged back in: collected
        self.wait_until(lambda: window.report is not None and window.stack.currentWidget() is window.report,
                        seconds=30, what="the report")
        result = window.report.result
        self.assertTrue(result.rows)
        self.assertTrue(result.csv_path.exists())
        self.assertNotEqual(window.report.stats["energy"].text(), "")
        for index in range(window.report.tabs.count()):  # every chart and the table draw
            window.report.tabs.setCurrentIndex(index)
            self.app.processEvents()

    def test_quitting_before_unplugging_gives_the_phone_back(self):
        window = self.open_window(perfetto=True)
        self.wait_until(lambda: window.home.start_button.isEnabled(), what="the device and checks")
        window.home.start_button.click()
        self.wait_until(lambda: window.stack.currentWidget() is window.record, what="the record page")
        self.assertTrue((self.device / "perfetto").exists())
        window.close()
        self.assertFalse((self.device / "perfetto").exists())  # the trace was stopped
        self.assertEqual((self.device / "options").read_text(), "")  # and the options turned off

    def test_record_over_wifi_with_markers(self):
        os.environ["FAKE_ADB_WIRELESS"] = "1"
        (self.device / "power").write_text("1")
        window = self.open_window(perfetto=True)
        self.wait_until(lambda: window.home.start_button.isEnabled(), what="the device and checks")
        self.assertEqual(window.home.device_name.text(), "Google Pixel 8 (fake) (Wi-Fi)")
        window.home.start_button.click()
        self.wait_until(lambda: window.stack.currentWidget() is window.record, what="the record page")
        self.assertEqual(window.record.title.text(), "Unplug the charger")
        time.sleep(1.2)  # still charging: still waiting
        self.app.processEvents()
        self.assertFalse(window.record.stop_button.isVisible())

        (self.device / "power").write_text("0")  # unplugged from the charger, still connected
        self.wait_until(lambda: window.record.stop_button.isVisible(), what="recording")
        time.sleep(0.6)
        window.record.add_marker()
        time.sleep(0.6)
        window.record.add_marker()
        self.assertEqual(window.record.marker_list.text().count("Marker"), 2)
        time.sleep(0.6)
        window.record.stop_button.click()  # collected at once: no replug
        self.wait_until(lambda: window.report is not None and window.stack.currentWidget() is window.report,
                        seconds=30, what="the report")
        result = window.report.result
        self.assertEqual(result.details["transport"], "wifi")
        self.assertEqual([p["label"] for p in result.phases], ["Start", "Marker 1", "Marker 2"])

    def test_wifi_dialog(self):
        from powdroid.gui.pages.wifi import WifiDialog

        window = self.open_window()
        self.wait_until(lambda: window.home.device is not None, what="the device")
        dialog = WifiDialog(window.home.device, window)
        serials = []
        dialog.connected.connect(serials.append)
        self.assertTrue(dialog.switch_button.isEnabled())
        dialog.connect_address.setText("192.168.1.20:5555")
        dialog.connect_button.click()
        self.wait_until(lambda: serials, what="the connection")
        self.assertEqual(serials, ["192.168.1.20:5555"])
        self.wait_until(lambda: dialog.connect_button.isEnabled(), what="the buttons")
        self.assertEqual(dialog.status.text(), "Connected to 192.168.1.20:5555: it is selected on the home page.")
        dialog.pair_address.setText("192.168.1.20:37000")
        dialog.pair_code.setText("000000")
        dialog.pair_button.click()
        self.wait_until(lambda: dialog.pair_button.isEnabled(), what="the pairing")
        self.assertIn("Cannot pair with 192.168.1.20:37000", dialog.status.text())
        self.assertFalse(WifiDialog(None, window).switch_button.isEnabled())

    def test_session_kept_when_quitting_while_recording(self):
        from powdroid.core import pending

        window = self.open_window(perfetto=True)
        self.wait_until(lambda: window.home.start_button.isEnabled(), what="the device and checks")
        window.home.start_button.click()
        self.wait_until(lambda: window.stack.currentWidget() is window.record, what="the record page")
        set_fake_state(self.device, None)
        self.wait_until(lambda: window.record.stop_button.isVisible(), what="recording")
        time.sleep(0.3)  # well after the unplug the battery history records
        window.record.add_marker()
        time.sleep(0.5)
        window.close()  # confirmed (QMessageBox.question answers Yes)
        (saved,) = pending.load_all()
        self.assertEqual((saved["stop"], len(saved["markers"])), (None, 1))

        set_fake_state(self.device, "device")
        window = self.open_window()
        banner = window.home.pending_box
        self.assertEqual(banner.count(), 1)
        self.wait_until(lambda: window.home.device is not None, what="the device")
        window._collect_pending(saved)
        self.wait_until(lambda: window.report is not None and window.stack.currentWidget() is window.report,
                        seconds=30, what="the report")
        self.assertEqual(pending.load_all(), [])
        self.assertEqual(window.report.result.details["current_source"], "perfetto")
        self.assertEqual(banner.count(), 0)

        # The marker can be renamed in the phases table: the JSON follows.
        table = window.report.phases_table
        table.item(1, 0).setText("Scrolling")
        self.wait_until(lambda: window.report.result.markers[0]["label"] == "Scrolling", what="the renaming")
        saved = json.loads(window.report.result.json_path.read_text())
        self.assertEqual([p["label"] for p in saved["phases"]], ["Start", "Scrolling"])

    def test_polling_without_track_devices(self):
        os.environ["FAKE_ADB_NO_TRACK"] = "1"
        window = self.open_window()
        self.wait_until(lambda: window.home.device is not None, what="the device")
        self.assertFalse(window.watcher.tracking)
        set_fake_state(self.device, "unauthorized")
        self.wait_until(lambda: not window.home.device.ready, what="the device state")
        self.assertEqual(window.home.device_name.text(), "Device not authorized")

    def test_open_a_saved_report(self):
        from powdroid.core import session
        from tests.fixtures import HISTORY, T0

        dump = self.dir / "dump.txt"
        dump.write_text(HISTORY)
        csv_path = session.process(dump, T0, T0 + 40_000, self.dir / "PowDroid_test.csv").csv_path
        window = self.open_window()
        window._open_report(str(csv_path))
        self.wait_until(lambda: window.report is not None and window.stack.currentWidget() is window.report,
                        what="the report")
        self.assertEqual(len(window.report.result.rows), len(session.load(csv_path).rows))


if __name__ == "__main__":
    unittest.main()
