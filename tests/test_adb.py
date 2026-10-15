"""Finding adb, and reading what it says about devices."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from powdroid.core import adb, checks


class FindAdbTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        patcher = mock.patch.object(adb, "_command", None)  # not found yet
        patcher.start()
        self.addCleanup(patcher.stop)

    def program(self, folder):
        path = self.dir / folder / adb.ADB_NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("")
        path.chmod(0o755)
        return path

    def environment(self, **variables):
        names = ("PATH", "ADB", "ANDROID_HOME", "ANDROID_SDK_ROOT", "LOCALAPPDATA")
        cleared = {name: "" for name in names}
        patchers = [mock.patch.dict(os.environ, {**cleared, **variables}),
                    mock.patch.object(Path, "home", return_value=self.dir / "home")]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_path_first_then_sdk_folders(self):
        on_path = self.program("bin")
        sdk = self.program("sdk/platform-tools")
        studio = self.program("home/Library/Android/sdk/platform-tools")
        self.environment(PATH=os.pathsep.join([str(self.dir / "empty"), str(on_path.parent)]),
                         ANDROID_HOME=str(self.dir / "sdk"))
        self.assertEqual(adb.candidates(), [on_path, sdk, studio])
        self.assertEqual(adb.command(), [str(on_path)])

    def test_relative_path_entries_are_ignored(self):
        self.program("here")
        self.environment(PATH=os.pathsep.join([".", "here"]))
        with mock.patch("os.getcwd", return_value=str(self.dir)):
            self.assertEqual(adb.candidates(), [])
        self.assertFalse(adb.is_available())
        with self.assertRaisesRegex(adb.AdbError, "adb not found: install the Android SDK platform tools"):
            adb.command()
        result = checks.check_adb()
        self.assertFalse(result.success)
        self.assertTrue(result.hint.startswith("Install the Android SDK platform tools"))

    def test_adb_variable(self):
        chosen = self.program("chosen")
        self.program("bin")
        self.environment(PATH=str(self.dir / "bin"), ADB=str(chosen))
        self.assertEqual(adb.command(), [str(chosen)])

    def test_set_executable(self):
        with self.assertRaisesRegex(adb.AdbError, "is not an adb program"):
            adb.set_executable(self.dir / "missing")
        adb.set_executable(self.program("x"))
        self.assertEqual(adb.command(), [str(self.dir / "x" / adb.ADB_NAME)])


class DevicesTest(unittest.TestCase):
    def test_parse_devices(self):
        devices = adb.parse_devices(
            "List of devices attached\n"
            "0123456789\tdevice\n"
            "emulator-5554\tdevice\n"
            "192.168.1.20:5555\toffline\n"
            "adb-0A1B2C-xyz._adb-tls-connect._tcp\tunauthorized\n"
            "9876\tno permissions (user in plugdev group; are your udev rules wrong?); see [http://x]\n"
            "\n")
        self.assertEqual([(d.serial, d.state, d.ready, d.emulator, d.wireless) for d in devices], [
            ("0123456789", "device", True, False, False),
            ("emulator-5554", "device", True, True, False),
            ("192.168.1.20:5555", "offline", False, False, True),
            ("adb-0A1B2C-xyz._adb-tls-connect._tcp", "unauthorized", False, False, True),
            ("9876", "no permissions", False, False, False)])
        self.assertEqual(adb.preferred(devices).serial, "0123456789")
        self.assertEqual(adb.preferred(devices[1:]).serial, "emulator-5554")
        self.assertEqual(adb.preferred(devices[2:]).serial, "192.168.1.20:5555")
        self.assertIsNone(adb.preferred([]))
        for state in ("unauthorized", "no permissions", "offline"):
            self.assertIn(state, adb.STATE_HINTS)

    def test_platform_tools_version(self):
        text = "Android Debug Bridge version 1.0.41\nVersion 35.0.2-12147458\nInstalled as /x/adb\n"
        self.assertEqual(adb.platform_tools_version(text), (35, 0, 2))
        self.assertIsNone(adb.platform_tools_version("Android Debug Bridge version 1.0.32\n"))
        for version, warned in (((28, 0, 2), True), ((35, 0, 2), False), (None, False)):
            with mock.patch.object(adb, "start_server"), \
                    mock.patch.object(adb, "platform_tools_version", return_value=version):
                result = checks.check_adb_server()
            self.assertTrue(result.success)
            self.assertEqual(bool(result.warning), warned)


if __name__ == "__main__":
    unittest.main()
