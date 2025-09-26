import json
import os
from typing import Dict, Any


class I18nManager:
    """Internationalization manager."""

    def __init__(self):
        self.current_language = "en"  # Default language
        self.translations = {}
        self.languages_dir = os.path.join(os.path.dirname(__file__), "languages")
        self.config_file = os.path.join(
            os.path.dirname(__file__), "..", ".powdroid_config.json"
        )
        self.available_languages = self._get_available_languages()

        # Load saved language or use default language
        saved_language = self._load_saved_language()
        if saved_language and saved_language in self.available_languages:
            self.current_language = saved_language

        self.load_language(self.current_language)

    def _get_available_languages(self) -> Dict[str, str]:
        """Returns the list of available languages."""
        return {"fr": "Français", "en": "English"}

    def _load_saved_language(self) -> str:
        """Loads the saved language from the configuration file."""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    return config.get("language", "en")
        except (json.JSONDecodeError, IOError) as e:
            print(f"[I18n] Error loading configuration: {e}")
        return "en"

    def _save_language_preference(self, language_code: str) -> bool:
        """Saves the language preference in the configuration file."""
        try:
            config = {}

            if os.path.exists(self.config_file):
                try:
                    with open(self.config_file, "r", encoding="utf-8") as f:
                        config = json.load(f)
                except (json.JSONDecodeError, IOError):
                    config = {}

            config["language"] = language_code

            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            print(f"[I18n] Language preference saved: {language_code}")
            return True

        except (IOError, OSError) as e:
            print(f"[I18n] Error saving language: {e}")
            return False

    def load_language(self, language_code: str) -> bool:
        """
        Loads translations for a given language.

        Args:
            language_code: Language code (e.g., 'fr', 'en')

        Returns:
            bool: True if loading succeeded, False otherwise
        """
        if language_code not in self.available_languages:
            print(f"[I18n] Unsupported language: {language_code}")
            return False

        language_file = os.path.join(self.languages_dir, f"{language_code}.json")

        if not os.path.exists(language_file):
            print(f"[I18n] Missing language file: {language_file}")
            return False

        try:
            with open(language_file, "r", encoding="utf-8") as f:
                self.translations = json.load(f)
            self.current_language = language_code
            print(f"[I18n] Language loaded: {self.available_languages[language_code]}")
            return True
        except (json.JSONDecodeError, IOError) as e:
            print(f"[I18n] Error loading {language_file}: {e}")
            return False

    def get_text(self, key: str, **kwargs) -> str:
        """
        Retrieves a translated text by its key.

        Args:
            key: Translation key (e.g., 'homepage.title')
            **kwargs: Variables to replace in the text

        Returns:
            str: Translated text or key if not found
        """
        keys = key.split(".")
        value = self.translations

        try:
            for k in keys:
                value = value[k]

            if kwargs and isinstance(value, str):
                try:
                    value = value.format(**kwargs)
                except KeyError as e:
                    print(f"[I18n] Missing variable in '{key}': {e}")

            return value
        except (KeyError, TypeError):
            print(f"[I18n] Missing translation key: {key}")
            return key

    def get_current_language(self) -> str:
        """Returns the current language code."""
        return self.current_language

    def get_available_languages(self) -> Dict[str, str]:
        """Returns the list of available languages."""
        return self.available_languages


_i18n_manager = I18nManager()


def get_text(key: str, **kwargs) -> str:
    """
    Shortcut function to retrieve a translated text.

    Args:
        key: Translation key
        **kwargs: Variables to replace

    Returns:
        str: Translated text
    """
    return _i18n_manager.get_text(key, **kwargs)


def get_current_language() -> str:
    """Returns the current language code."""
    return _i18n_manager.get_current_language()


def get_available_languages() -> Dict[str, str]:
    """Returns the list of available languages."""
    return _i18n_manager.get_available_languages()


def get_language(language_code: str) -> str:
    """Returns the language name for a given code."""
    return _i18n_manager.available_languages.get(language_code, "Unknown")


# Alias for compatibility
t = get_text  # Usage: t("homepage.title")
