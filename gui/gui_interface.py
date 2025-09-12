import sys
import os
import json


# Add parent directory to PYTHONPATH for imports
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gui.popup.information_plug_phone import InformationPopup
from gui.popup.about import AboutDialog
from gui.popup.check_config import CheckConfigDialog


def load_config():
    """Load configuration from the .powdroid_config.json file"""
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        ".powdroid_config.json",
    )
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            return config.get("language", "en"), config.get(
                "theme", "dark"
            )  # 'en' default if no language
    except (FileNotFoundError, json.JSONDecodeError):
        return "en", "dark"  # Default language and theme if error


def main():
    """Main function for the GUI interface"""
    from PyQt6.QtWidgets import QApplication, QDialog
    from PyQt6.QtCore import QTimer
    import time

    app = QApplication(sys.argv)

    current_language, current_theme = load_config()
    print(f"Language loaded from config: {current_language}")
    print(f"Theme loaded from config: {current_theme}")

    # First show the configuration check dialog
    checkConfig = CheckConfigDialog(dark_theme=current_theme, language=current_language)

    if checkConfig.exec() == QDialog.DialogCode.Accepted:

        # Variables globales pour garder les références
        popup1 = None
        popup2 = None
        timer1 = None
        timer2 = None

        def show_second_popup():
            nonlocal popup2, timer2
            # Show second popup (plugged)
            popup2 = InformationPopup(
                dark_theme=current_theme, language=current_language, plugged=True
            )
            popup2.show()

            # Timer to close second popup
            timer2 = QTimer()
            timer2.timeout.connect(popup2.close)
            timer2.timeout.connect(show_about_dialog)
            timer2.setSingleShot(True)
            timer2.start(3000)

        def show_about_dialog():
            aboutDialog = AboutDialog(
                dark_theme=current_theme, language=current_language
            )
            aboutDialog.exec()
            app.quit()  # Quitter l'application après le dialog About

        # Show first popup (unplugged)
        popup1 = InformationPopup(
            dark_theme=current_theme, language=current_language, plugged=False
        )
        popup1.show()

        # Timer to close first popup and show second
        timer1 = QTimer()
        timer1.timeout.connect(popup1.close)
        timer1.timeout.connect(show_second_popup)
        timer1.setSingleShot(True)
        timer1.start(3000)

        # Start the event loop
        app.exec()
    else:
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
