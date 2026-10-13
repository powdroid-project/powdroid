"""Optional debug log, to investigate problems that only happen on other computers or phones.

Modules log to children of the "powdroid" logger, which writes nothing until enable() is
called (CLI --debug, or the GUI's debug log option). The log then records the environment,
every adb command with its answer, what the battery statistics dump contains, the steps of
the session and every error with its traceback.
"""

import atexit
import faulthandler
import locale
import logging
import os
import platform
import shutil
import sys
import threading
from datetime import datetime
from pathlib import Path

from core import __version__

logger = logging.getLogger("powdroid")
logger.addHandler(logging.NullHandler())  # nothing at all, not even warnings on stderr, until enabled

FORMAT = "%(asctime)s.%(msecs)03d %(levelname)-8s [%(threadName)s] %(name)s: %(message)s"
# Environment variables that change how adb behaves.
ADB_VARIABLES = ("ANDROID_HOME", "ANDROID_SDK_ROOT", "ANDROID_SERIAL", "ANDROID_ADB_SERVER_PORT",
                 "ADB_SERVER_SOCKET", "ADB_VENDOR_KEYS", "ADB_LIBUSB", "ADB_MDNS_OPENSCREEN")
MAX_TEXT = 20_000  # characters of one command output or file excerpt written to the log

_handler = None
_previous_hooks = None


def default_path(directory):
    """A new log file in the logs folder of the output directory."""
    return Path(directory).expanduser() / "logs" / f"PowDroid_debug_{datetime.now():%Y%m%d-%H%M%S}.log"


def enabled():
    return _handler is not None


def log_path():
    """The log file being written, or None."""
    return Path(_handler.baseFilename) if _handler else None


def enable(path):
    """Write the debug log to path (appending if it exists) and return its absolute path.

    Raises OSError if the file cannot be written.
    """
    global _handler
    disable()
    path = Path(path).expanduser().absolute()
    path.parent.mkdir(parents=True, exist_ok=True)
    _handler = logging.FileHandler(path, encoding="utf-8")
    _handler.setFormatter(logging.Formatter(FORMAT, "%Y-%m-%d %H:%M:%S"))
    logger.addHandler(_handler)
    logger.setLevel(logging.DEBUG)
    faulthandler.enable(_handler.stream)  # hard crashes (e.g. in Qt) leave a trace too
    _hook_exceptions()
    _log_environment()
    return path


@atexit.register  # runs before logging's own shutdown, which would close the file under faulthandler
def disable():
    global _handler
    if _handler is None:
        return
    logger.info("Debug log stopped.")
    faulthandler.disable()
    _unhook_exceptions()
    logger.removeHandler(_handler)
    logger.setLevel(logging.NOTSET)
    _handler.close()
    _handler = None


def _hook_exceptions():
    """Log uncaught exceptions, then let the previous hooks handle them.

    With a custom sys.excepthook, PyQt no longer aborts on an exception raised in a slot:
    in debug mode the GUI keeps running after logging it.
    """
    global _previous_hooks
    previous_hook, previous_thread_hook = _previous_hooks = (sys.excepthook, threading.excepthook)

    def excepthook(*exc_info):
        logger.critical("Uncaught exception", exc_info=exc_info)
        previous_hook(*exc_info)

    def thread_excepthook(args):
        if not issubclass(args.exc_type, SystemExit):
            logger.critical("Uncaught exception in thread %s", getattr(args.thread, "name", "?"),
                            exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
        previous_thread_hook(args)

    sys.excepthook, threading.excepthook = excepthook, thread_excepthook


def _unhook_exceptions():
    global _previous_hooks
    sys.excepthook, threading.excepthook = _previous_hooks
    _previous_hooks = None


def _find_all(program):
    """Every copy of a program in the PATH, in order: the first one is used."""
    found = []
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        path = directory and shutil.which(program, path=directory)
        if path and path not in found:
            found.append(path)
    return found


def _log_environment():
    from core import adb  # imported here: adb logs through this module

    system = platform.platform()
    if sys.platform.startswith("linux"):
        try:
            system += f" ({platform.freedesktop_os_release()['PRETTY_NAME']})"
        except (AttributeError, OSError, KeyError):  # AttributeError: Python < 3.10
            pass
    try:
        language = locale.getlocale()
    except ValueError as e:
        language = e
    now = datetime.now().astimezone()
    lines = [
        f"PowDroid {__version__} debug log, started {now.isoformat(timespec='seconds')} ({now:%Z})",
        f"Command line: {sys.argv}",
        f"Python {sys.version} at {sys.executable}",
        f"System: {system}",
        f"Locale: {language}, encodings: preferred {locale.getpreferredencoding(False)}, "
        f"file system {sys.getfilesystemencoding()}, console {getattr(sys.stdout, 'encoding', None)}",
        f"Working directory: {os.getcwd()}",
        f"adb found in PATH: {_find_all('adb') or 'none'}",
    ]
    lines += [f"{name}={os.environ[name]}" for name in ("PATH", *ADB_VARIABLES) if name in os.environ]
    logger.info("\n".join(lines))
    try:
        adb.version()
    except adb.AdbError:
        pass  # already logged


def indent(title, text):
    """Format a command output or a file excerpt for the log, one '| ' line per line."""
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    if len(text) > MAX_TEXT:
        text = f"{text[:MAX_TEXT]}\n[{len(text) - MAX_TEXT} more characters not logged]"
    return f"  {title}:\n" + "\n".join(f"    | {line}" for line in text.splitlines())


def ms(value):
    """An epoch time in ms (device or computer time), as a local time followed by the raw value."""
    if value is None:
        return "None"
    try:
        return f"{datetime.fromtimestamp(value / 1000):%Y-%m-%d %H:%M:%S.%f}"[:-3] + f" ({value})"
    except (OverflowError, OSError, ValueError):
        return str(value)
