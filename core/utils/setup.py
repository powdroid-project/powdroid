import shutil
import subprocess
import sys
import signal
from dataclasses import dataclass
from typing import Optional, List


@dataclass
class CheckResult:
    """Résultat d'une vérification de configuration système"""

    success: bool
    message: str
    details: Optional[str] = None
    error: Optional[str] = None


def command_in_path(command):
    """Vérifie si une commande est disponible dans le PATH"""
    return shutil.which(command) is not None


def check_android_sdk() -> CheckResult:
    """Vérifie la disponibilité d'ADB (Android SDK Platform Tools)"""
    if command_in_path("adb"):
        return CheckResult(
            success=True,
            message="Android SDK platform tools are installed and in the PATH.",
        )
    else:
        return CheckResult(
            success=False,
            message="Android SDK platform tools are not installed or not in the PATH.",
            error="Please ensure that Android SDK platform tools are installed and configured as described in the README.",
        )


def check_python_version() -> CheckResult:
    """Vérifie la version de Python"""
    python_cmd = None
    for cmd in ("python", "python3"):
        if command_in_path(cmd):
            python_cmd = cmd
            break

    if python_cmd:
        try:
            result = subprocess.run(
                [python_cmd, "--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            version = result.stdout.strip() or result.stderr.strip()

            if version.startswith("Python 3."):
                return CheckResult(
                    success=True,
                    message=f"{python_cmd.capitalize()} is installed.",
                    details=f"Version: {version}",
                )
            else:
                return CheckResult(
                    success=False,
                    message=f"{python_cmd.capitalize()} version is not supported.",
                    details=f"Version: {version}",
                    error="Python 3.x is required.",
                )
        except Exception as e:
            return CheckResult(
                success=False,
                message=f"An error occurred while checking {python_cmd}.",
                error=str(e),
            )
    else:
        return CheckResult(
            success=False,
            message="Python is not installed or not in the PATH.",
            error="Please ensure that Python is installed and configured as described in the README.",
        )


def check_pandas_module() -> CheckResult:
    """Vérifie la disponibilité du module Pandas"""
    try:
        import pandas
        import matplotlib
        import PyQt6

        return CheckResult(success=True, message="The Pandas module is installed.")
    except ImportError:
        return CheckResult(
            success=False,
            message="The Pandas module is not installed.",
            error="Run 'pip install pandas' to install it.",
        )


def check_gui_modules() -> CheckResult:
    """Vérifie la disponibilité des modules GUI"""
    missing_modules = []
    try:
        import matplotlib
    except ImportError:
        missing_modules.append("matplotlib")

    try:
        import PyQt5
    except ImportError:
        missing_modules.append("PyQt5")

    if not missing_modules:
        return CheckResult(
            success=True,
            message="GUI modules matplotlib and PyQt5 are installed.",
        )
    else:
        return CheckResult(
            success=False,
            message=f"GUI modules are not fully installed. Missing: {', '.join(missing_modules)}",
            error="If you wish to use the GUI, run: pip install pandas matplotlib PyQt5",
        )


def check_go_runtime() -> CheckResult:
    """Vérifie la disponibilité du runtime Go"""
    if command_in_path("go"):
        try:
            result = subprocess.run(
                ["go", "version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            return CheckResult(
                success=True,
                message="Go runtime is installed.",
                details=f"Version: {result.stdout.strip()}",
            )
        except Exception as e:
            return CheckResult(
                success=False,
                message="An error occurred while checking the Go runtime.",
                error=str(e),
            )
    else:
        return CheckResult(
            success=False,
            message="Go runtime is not installed or not in the PATH.",
            error="Please ensure that the Go runtime is installed and configured as described in the README.",
        )


def initialize_adb_server(verbose=False) -> CheckResult:
    """Initialise le serveur ADB"""
    if command_in_path("adb"):
        try:
            subprocess.run(
                "adb kill-server",
                shell=True,
                check=True,
                stdout=None if verbose else subprocess.DEVNULL,
                stderr=None if verbose else subprocess.DEVNULL,
            )
            subprocess.run(
                "adb start-server",
                shell=True,
                check=True,
                stdout=None if verbose else subprocess.DEVNULL,
                stderr=None if verbose else subprocess.DEVNULL,
            )
            return CheckResult(
                success=True, message="ADB server restarted successfully."
            )
        except Exception as e:
            return CheckResult(
                success=False,
                message="Failed to restart ADB server.",
                error=f"Error: {str(e)}",
            )
    else:
        return CheckResult(
            success=False,
            message="ADB command not found.",
            error="Ensure Android SDK platform tools are installed and in the PATH.",
        )


def run_all_checks(verbose=False) -> List[CheckResult]:
    """Exécute toutes les vérifications de configuration système"""
    checks = [
        check_android_sdk,
        check_python_version,
        check_pandas_module,
        check_gui_modules,
        check_go_runtime,
        lambda: initialize_adb_server(verbose=verbose),
    ]

    results = []
    for check in checks:
        try:
            result = check()
            results.append(result)
        except Exception as e:
            results.append(
                CheckResult(
                    success=False,
                    message=f"Unexpected error in {check.__name__}",
                    error=str(e),
                )
            )

    return results


def handle_exit(sig, frame):
    """Gestionnaire pour l'interruption du signal"""
    sys.exit(0)


def main(verbose=False):
    """Point d'entrée principal pour l'exécution en ligne de commande"""
    signal.signal(signal.SIGINT, handle_exit)
    print("[PowDroid] INFO | System configuration check...\n")

    results = run_all_checks(verbose=verbose)
    errors = []

    for result in results:
        if result.success:
            print(f"[PowDroid] OK | {result.message}")
            if result.details:
                print(f"[PowDroid] └── {result.details}")
        else:
            print(f"[Debug] Error | {result.message}")
            if result.error:
                print(f"[Debug] └── {result.error}")
            errors.append(result.message)

    if errors:
        print(f"\n[PowDroid] INFO | Exiting due to {len(errors)} error(s).")
        sys.exit(1)
    else:
        print("\n[PowDroid] INFO | Check completed successfully.")


if __name__ == "__main__":
    verbose_flag = "--verbose" in sys.argv
    main(verbose=verbose_flag)
