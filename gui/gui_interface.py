import sys
import os
import json

# Add parent directory to PYTHONPATH for imports
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gui.popup.about import AboutDialog

def load_config():
    """Load configuration from the .powdroid_config.json file"""
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.powdroid_config.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            return config.get('language', 'en'), config.get('theme', 'dark')  # 'en' default if no language
    except (FileNotFoundError, json.JSONDecodeError):
        return 'en', 'dark'  # Default language and theme if error


if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    
    current_language, current_theme = load_config()
    print(f"Language loaded from config: {current_language}")
    print(f"Theme loaded from config: {current_theme}")

    dialog = AboutDialog(dark_theme=current_theme, language=current_language)
    dialog.show()
    
    sys.exit(app.exec())