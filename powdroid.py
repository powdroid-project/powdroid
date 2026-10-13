"""PowDroid entry point: starts the GUI without arguments, the CLI otherwise."""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import __version__  # noqa: E402


def main():
    if len(sys.argv) == 1:
        from gui.app import main as gui_main

        return gui_main()

    parser = argparse.ArgumentParser(description=f"PowDroid {__version__} – energy profiler for Android")
    parser.add_argument("-o", "--output", default="csv", metavar="EXT",
                        help="output formats: csv, html or csv,html (default: csv)")
    parser.add_argument("-d", "--dir", default=".", help="output directory (default: current directory)")
    parser.add_argument("-s", "--serial", help="device serial, when several devices are connected")
    parser.add_argument("-v", "--verbose", action="store_true", help="print more details")
    parser.add_argument("-t", "--traceback", action="store_true", help="print the traceback on errors")
    parser.add_argument("--debug", nargs="?", const="", metavar="FILE",
                        help="write a detailed log (adb commands and answers, data read, errors) to "
                             "FILE, by default DIR/logs/PowDroid_debug_<date>.log, to attach to bug reports")
    parser.add_argument("--version", action="version", version=f"PowDroid {__version__}")
    args = parser.parse_args()

    formats = [f.strip() for f in args.output.split(",") if f.strip()]
    invalid = [f for f in formats if f not in ("csv", "html")]
    if invalid or not formats:
        parser.error(f"invalid output format: {', '.join(invalid) or args.output!r} (use csv, html or csv,html)")

    from cli.cli import main as cli_main
    from core import debug

    if args.debug is not None:
        try:
            debug.enable(args.debug or debug.default_path(args.dir))
        except OSError as e:
            parser.error(f"cannot write the debug log: {e}")
    try:
        return cli_main(formats, args.dir, args.serial, args.verbose, args.traceback)
    except KeyboardInterrupt:
        print("\n[PowDroid] Interrupted.")
        debug.logger.info("Interrupted by the user")
        return 130
    finally:
        if debug.enabled():
            print(f"[PowDroid] Debug log written to {debug.log_path()}: attach it to your bug report.")


if __name__ == "__main__":
    sys.exit(main())
