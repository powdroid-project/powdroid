import sys
import signal
import core.utils.setup as setup_utils


def print_check_result(result, check_name=""):
    """Affiche le résultat d'une vérification avec le formatage CLI"""
    if result.success:
        print(f"[PowDroid] OK | {result.message}")
        if result.details:
            print(f"[PowDroid] └── {result.details}")
    else:
        print(f"[Debug] Error | {result.message}")
        if result.error:
            print(f"[Debug] └── {result.error}")


def check_android_sdk():
    """Wrapper CLI pour la vérification Android SDK"""
    result = setup_utils.check_android_sdk()
    print_check_result(result)
    if not result.success:
        raise SystemExit("[Debug] Exiting due to missing Android SDK platform tools.")


def check_python_version():
    """Wrapper CLI pour la vérification de Python"""
    result = setup_utils.check_python_version()
    print_check_result(result)
    if not result.success:
        raise SystemExit("[Debug] Exiting due to Python version issues.")


def check_pandas_module():
    """Wrapper CLI pour la vérification du module Pandas"""
    result = setup_utils.check_pandas_module()
    print_check_result(result)
    if not result.success:
        raise SystemExit("[Debug] Exiting due to missing Pandas module.")


def check_gui_modules():
    """Wrapper CLI pour la vérification des modules GUI"""
    result = setup_utils.check_gui_modules()
    print_check_result(result)


def check_go_runtime():
    """Wrapper CLI pour la vérification du runtime Go"""
    result = setup_utils.check_go_runtime()
    print_check_result(result)
    if not result.success:
        raise SystemExit("[Debug] Exiting due to missing Go runtime.")


def initialize_adb_server(verbose=False):
    """Wrapper CLI pour l'initialisation du serveur ADB"""
    result = setup_utils.initialize_adb_server(verbose=verbose)
    print_check_result(result)
    if not result.success:
        raise SystemExit("[Debug] Exiting due to ADB server initialization error.")


def handle_exit(sig, frame):
    """Gestionnaire pour l'interruption du signal"""
    sys.exit(0)


def main(verbose=False):
    """Point d'entrée principal pour l'interface CLI"""
    signal.signal(signal.SIGINT, handle_exit)
    print("[PowDroid] INFO | System configuration check...\n")
    errors = []

    checks = [
        check_android_sdk,
        check_python_version,
        check_pandas_module,
        check_gui_modules,
        check_go_runtime,
        lambda: initialize_adb_server(verbose=verbose),
    ]

    for check in checks:
        try:
            check()
        except SystemExit as e:
            errors.append(str(e))

    if errors:
        print(f"\n[PowDroid] INFO | Exiting due to {len(errors)} error(s).")
        sys.exit(1)
    else:
        print("\n[PowDroid] INFO | Check completed successfully.")


if __name__ == "__main__":
    verbose_flag = "--verbose" in sys.argv
    main(verbose=verbose_flag)
