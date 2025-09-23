
import os
import subprocess
import sys
import argparse
import signal
import json


def handle_exit(signum, frame):
    print("[PowDroid] INFO | Execution interrupted. Exiting...")
    sys.exit(0)


def main():
    signal.signal(signal.SIGINT, handle_exit)

    try:
        with open(os.path.join("gui", "languages", "en.json"), encoding="utf-8") as f:
            lang_data = json.load(f)
            version = lang_data.get("version", "Version inconnue")
    except Exception:
        version = "Version inconnue"

    class CustomArgumentParser(argparse.ArgumentParser):
        def error(self, message):
            print(f"[Debug] ERROR | {message}. Use -h or --help for usage information.")
            sys.exit(2)

    parser = CustomArgumentParser(
        description=f"PowDroid CLI [Version {version}]"
    )
    parser.add_argument(
        "-o",
        "--output",
        help="output format (csv, html, or both separated by comma)",
        metavar="EXT",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="verbose mode for debugging"
    )
    parser.add_argument(
        "-t", "--traceback", action="store_true", help="traceback mode for analysis"
    )
    args = parser.parse_args()

    output_formats = []
    if args.output:
        output_formats = args.output.split(",")
        for ext in output_formats:
            if ext not in ["csv", "html"]:
                print(
                    f"[Debug] ERROR | Invalid output format: {ext}. Allowed formats are 'csv' and 'html'."
                )
                return

    if (args.verbose or args.traceback) and not output_formats:
        print(
            "[Debug] ERROR | The -o, --output argument is required when -v or -t is used."
        )
        return

    if len(output_formats) > 1:
        print(
            f"[PowDroid] INFO | Multiple output formats selected: {', '.join(output_formats)}"
        )

    if len(sys.argv) > 1:
        # Utiliser la nouvelle interface CLI de configuration
        try:
            from cli.setup_cli import main as setup_main

            setup_main(verbose=args.verbose)
        except subprocess.CalledProcessError as e:
            print(f"[Debug] ERROR | Setup check failed with error: {e}")
            return
        except Exception as e:
            print(f"[Debug] ERROR | Setup check failed: {e}")
            return

        from cli.cli_interface import main as cli_main

        cli_main(output_formats, verbose=args.verbose)
    else:
        # Utilisation de PyQt par défaut
        from gui.gui_interface import main as gui_main

        gui_main()


if __name__ == "__main__":
    main()
