"""PowDroid entry point: starts the GUI without arguments, the CLI otherwise."""

import argparse
import sys
from pathlib import Path

from powdroid.core import __version__

GUI_MISSING = 'The graphical interface needs PyQt6 and matplotlib: pip install "powdroid[gui]"'


def gui_main():
    """Start the graphical interface (the powdroid-gui command)."""
    try:
        from powdroid.gui.app import main
    except ImportError as e:
        print(f"[PowDroid] {GUI_MISSING} ({e}). Run 'powdroid --help' for the command-line interface.",
              file=sys.stderr)
        return 1
    return main()


def main():
    if len(sys.argv) == 1:
        return gui_main()

    parser = argparse.ArgumentParser(prog="powdroid",
                                     description=f"PowDroid {__version__} – energy profiler for Android")
    parser.add_argument("-o", "--output", default="csv", metavar="EXT",
                        help="output formats: csv, html or csv,html (default: csv)")
    parser.add_argument("-d", "--dir", help="output directory (default: the current directory; with --reprocess, "
                                             "the folder of the session file)")
    parser.add_argument("-s", "--serial", help="device serial, when several devices are connected")
    parser.add_argument("-v", "--verbose", action="store_true", help="print more details")
    parser.add_argument("-t", "--traceback", action="store_true", help="print the traceback on errors")
    parser.add_argument("--no-perfetto", dest="perfetto", action="store_false",
                        help="measure with the battery statistics only. By default, PowDroid records the battery "
                             "with Perfetto on Android 10+ (µAh coulomb counter and current samples twice a second, "
                             "plus the power rails of phones that measure them) and uses the battery statistics "
                             "when Perfetto is not available")
    parser.add_argument("--debug", nargs="?", const="", metavar="FILE",
                        help="write a detailed log (adb commands and answers, data read, errors) to "
                             "FILE, by default DIR/logs/PowDroid_debug_<date>.log, to attach to bug reports")
    parser.add_argument("--adb", metavar="PATH",
                        help="the adb program to use (default: the ADB environment variable, the PATH, then the "
                             "platform-tools of the Android SDK in ANDROID_HOME, ANDROID_SDK_ROOT or its usual folder)")
    parser.add_argument("--duration", type=float, metavar="SECONDS",
                        help="record for this long, without asking anything: the session starts when the phone is "
                             "unplugged (over Wi-Fi: when it runs on battery) and its data is read right after when "
                             "the phone is connected over Wi-Fi, or once it is plugged back in over USB")
    parser.add_argument("--connect", metavar="HOST:PORT",
                        help="first connect to a phone over Wi-Fi (adb connect), and use it")
    parser.add_argument("--collect-pending", action="store_true",
                        help="collect the sessions that were recorded but not collected (PowDroid was stopped or "
                             "crashed before reading the phone's data); -s to choose one phone")
    parser.add_argument("--reprocess", metavar="JSON",
                        help="process a recorded session again from its PowDroid_<date>.json file (no phone "
                             "needed), e.g. with a newer PowDroid: its CSV, JSON (and HTML) are written again")
    parser.add_argument("--version", action="version", version=f"PowDroid {__version__}")
    args = parser.parse_args()

    if args.duration is not None and args.duration <= 0:
        parser.error("--duration must be a positive number of seconds")
    formats = [f.strip() for f in args.output.split(",") if f.strip()]
    invalid = [f for f in formats if f not in ("csv", "html")]
    if invalid or not formats:
        parser.error(f"invalid output format: {', '.join(invalid) or args.output!r} (use csv, html or csv,html)")

    from powdroid.cli import cli
    from powdroid.core import adb, debug

    if args.adb:
        try:
            adb.set_executable(args.adb)
        except adb.AdbError as e:
            parser.error(str(e))
    out_dir = args.dir or (str(Path(args.reprocess).parent) if args.reprocess else ".")
    if args.debug is not None:
        try:
            debug.enable(args.debug or debug.default_path(out_dir))
        except OSError as e:
            parser.error(f"cannot write the debug log: {e}")
    try:
        if args.reprocess:
            return cli.reprocess(args.reprocess, formats, args.dir, args.traceback)
        if args.collect_pending:
            return cli.collect_pending(args.serial, args.verbose, args.traceback)
        return cli.main(formats, out_dir, args.serial, args.verbose, args.traceback, args.perfetto, args.duration,
                        args.connect)
    except KeyboardInterrupt:
        print("\n[PowDroid] Interrupted.")
        debug.logger.info("Interrupted by the user")
        return 130
    finally:
        if debug.enabled():
            print(f"[PowDroid] Debug log written to {debug.log_path()}: attach it to your bug report.")


if __name__ == "__main__":
    sys.exit(main())
