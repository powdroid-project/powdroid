"""Environment checks run before recording."""

import importlib.util
import sys
from dataclasses import dataclass
from typing import Optional

from powdroid.core import adb

MIN_PYTHON = (3, 11)


@dataclass
class CheckResult:
    name: str
    success: bool
    message: str
    hint: Optional[str] = None
    warning: Optional[str] = None  # a problem that does not prevent recording


def check_python():
    version = ".".join(map(str, sys.version_info[:3]))
    if sys.version_info >= MIN_PYTHON:
        return CheckResult("Python", True, f"Python {version}")
    return CheckResult("Python", False, f"Python {version} is too old",
                       f"Python {'.'.join(map(str, MIN_PYTHON))} or newer is required.")


def check_adb():
    try:
        return CheckResult("adb", True, f"Android platform tools: {adb.command()[-1]}")
    except adb.AdbError as e:
        hint = str(e).removeprefix("adb not found: ")
        return CheckResult("adb", False, "adb not found", hint[:1].upper() + hint[1:])


def check_adb_server():
    try:
        adb.start_server()
        version = adb.platform_tools_version()
    except adb.AdbError as e:
        return CheckResult("adb server", False, "Could not start the adb server", str(e))
    shown = ".".join(map(str, version)) if version else "unknown version"
    result = CheckResult("adb server", True, f"adb server running (platform-tools {shown})")
    if version and version < adb.MIN_PLATFORM_TOOLS:
        result.warning = (f"These platform-tools are old: update them to version "
                          f"{'.'.join(map(str, adb.MIN_PLATFORM_TOOLS))} or newer if PowDroid fails.")
    return result


def check_gui_modules():
    missing = [m for m in ("PyQt6", "matplotlib") if importlib.util.find_spec(m) is None]
    if not missing:
        return CheckResult("GUI modules", True, "PyQt6 and matplotlib installed")
    return CheckResult(
        "GUI modules", False, f"Missing: {', '.join(missing)}",
        'Run: pip install "powdroid[gui]" (or pip install -r requirements.txt in a source checkout)',
    )


def run_all(gui=False):
    adb_check = check_adb()
    results = [check_python(), adb_check]
    if gui:
        results.append(check_gui_modules())
    if adb_check.success:
        results.append(check_adb_server())
    return results
