import os
import sys
import subprocess
import argparse
import signal

def handle_exit(sig, frame):
    print("\n[PowDroid] INFO | Execution interrupted. Exiting...")
    sys.exit(0)

def main():
    signal.signal(signal.SIGINT, handle_exit)

    class CustomArgumentParser(argparse.ArgumentParser):
        def error(self, message):
            print(f"[PowDroid] ERROR | {message}. Use -h or --help for usage information.")
            sys.exit(2)

    parser = CustomArgumentParser()
    parser.add_argument(
        "-o", "--output",
        help="output format (csv, html, or both separated by comma)",
        metavar="EXT"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="verbose mode for debugging")
    parser.add_argument("-t", "--traceback", action="store_true", help="traceback mode for analysis")
    args = parser.parse_args()

    ### if we don't want to use the default launch of the GUI, we can use the CLI interface

    # if not any(vars(args).values()):
    #     print("[PowDroid] ERROR | No valid arguments provided. Use -h or --help for usage information.")
    #     return

    output_formats = []
    if args.output:
        output_formats = args.output.split(",")
        for ext in output_formats:
            if ext not in ["csv", "html"]:
                print(f"[PowDroid] ERROR | Invalid output format: {ext}. Allowed formats are 'csv' and 'html'.")
                return

    if (args.verbose or args.traceback) and not output_formats:
        print("[PowDroid] ERROR | The -o, --output argument is required when -v or -t is used.")
        return

    if len(output_formats) > 1:
        print(f"[PowDroid] INFO | Multiple output formats selected: {', '.join(output_formats)}")

    setup_path = os.path.join(os.path.dirname(__file__), 'setup.py')
    if os.path.exists(setup_path):
        setup_command = [sys.executable, setup_path]
        if args.verbose:
            setup_command.append("--verbose")
        try:
            subprocess.run(setup_command, check=True)
        except subprocess.CalledProcessError as e:
            print(f"[PowDroid] ERROR | Setup script failed with error: {e}")
            return
    else:
        print("[PowDroid] ERROR | setup.py not found.")
        return

    if len(sys.argv) > 1:
        try:
            from cli.cli_interface import main as cli_main
            cli_main(output_formats, verbose=args.verbose, traceback=args.traceback)
        except ImportError as e:
            print(f"[PowDroid] ERROR | Failed to import CLI interface. Please ensure all dependencies are installed.")
        except Exception as e:
            if args.traceback:
                print(f"[PowDroid] ERROR | An error occurred in the CLI: {e}")
            else:
                print("[PowDroid] ERROR | An unexpected error occurred in the CLI. Use --traceback for details.")
    else:
        try:
            from gui.gui_interface import main as gui_main
            gui_main()
        except ImportError as e:
            print(f"[PowDroid] ERROR | Failed to import GUI interface. Please ensure all dependencies are installed.")
        except Exception as e:
            if args.traceback:
                print(f"[PowDroid] ERROR | An error occurred in the GUI: {e}")
            else:
                print("[PowDroid] ERROR | An unexpected error occurred in the GUI. Use --traceback for details.")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[PowDroid] ERROR | An unexpected error occurred: {e}")
