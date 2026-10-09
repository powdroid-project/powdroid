"""Environment checks run before recording."""

import importlib.util
import sys
from dataclasses import dataclass
from typing import Optional

from core import adb


@dataclass
class CheckResult:
    name: str
    success: bool
    message: str
    hint: Optional[str] = None


def check_python():
    version = ".".join(map(str, sys.version_info[:3]))
    if sys.version_info >= (3, 9):
        return CheckResult("Python", True, f"Python {version}")
    return CheckResult("Python", False, f"Python {version} is too old", "Python 3.9 or newer is required.")


def check_adb():
    if adb.is_available():
        return CheckResult("adb", True, "Android platform tools found in PATH")
    return CheckResult(
        "adb", False, "adb not found in PATH",
        "Install the Android SDK platform tools and add them to your PATH (see README).",
    )


def check_adb_server():
    try:
        adb.start_server()
        return CheckResult("adb server", True, "adb server running")
    except adb.AdbError as e:
        return CheckResult("adb server", False, "Could not start the adb server", str(e))


def check_gui_modules():
    missing = [m for m in ("PyQt6", "matplotlib") if importlib.util.find_spec(m) is None]
    if not missing:
        return CheckResult("GUI modules", True, "PyQt6 and matplotlib installed")
    return CheckResult(
        "GUI modules", False, f"Missing: {', '.join(missing)}", "Run: pip install -r requirements.txt"
    )


def run_all(gui=False):
    adb_check = check_adb()
    results = [check_python(), adb_check]
    if gui:
        results.append(check_gui_modules())
    if adb_check.success:
        results.append(check_adb_server())
    return results
