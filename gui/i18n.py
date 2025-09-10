#!/usr/bin/env python3
"""
Système d'internationalisation pour PowDroid - Version PyQt5
Gère le chargement et la sélection des langues.
"""

import json
import os
from typing import Dict, Any


class I18nManager:
    """Gestionnaire de l'internationalisation."""

    def __init__(self):
        self.current_language = "en"  # Langue par défaut
        self.translations = {}
        self.languages_dir = os.path.join(os.path.dirname(__file__), "languages")
        self.config_file = os.path.join(
            os.path.dirname(__file__), "..", ".powdroid_config.json"
        )
        self.available_languages = self._get_available_languages()

        # Charger la langue sauvegardée ou utiliser la langue par défaut
        saved_language = self._load_saved_language()
        if saved_language and saved_language in self.available_languages:
            self.current_language = saved_language

        self.load_language(self.current_language)

    def _get_available_languages(self) -> Dict[str, str]:
        """Retourne la liste des langues disponibles."""
        return {"fr": "Français", "en": "English"}

    def _load_saved_language(self) -> str:
        """Charge la langue sauvegardée depuis le fichier de configuration."""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    return config.get("language", "en")
        except (json.JSONDecodeError, IOError) as e:
            print(f"[I18n] Erreur lors du chargement de la configuration: {e}")
        return "en"

    def _save_language_preference(self, language_code: str) -> bool:
        """Sauvegarde la préférence de langue dans le fichier de configuration."""
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

            print(f"[I18n] Préférence de langue sauvegardée: {language_code}")
            return True

        except (IOError, OSError) as e:
            print(f"[I18n] Erreur lors de la sauvegarde de la langue: {e}")
            return False

    def load_language(self, language_code: str) -> bool:
        """
        Charge les traductions pour une langue donnée.

        Args:
            language_code: Code de la langue (ex: 'fr', 'en')

        Returns:
            bool: True si le chargement a réussi, False sinon
        """
        if language_code not in self.available_languages:
            print(f"[I18n] Langue non supportée: {language_code}")
            return False

        language_file = os.path.join(self.languages_dir, f"{language_code}.json")

        if not os.path.exists(language_file):
            print(f"[I18n] Fichier de langue manquant: {language_file}")
            return False

        try:
            with open(language_file, "r", encoding="utf-8") as f:
                self.translations = json.load(f)
            self.current_language = language_code
            print(f"[I18n] Langue chargée: {self.available_languages[language_code]}")
            return True
        except (json.JSONDecodeError, IOError) as e:
            print(f"[I18n] Erreur lors du chargement de {language_file}: {e}")
            return False

    def get_text(self, key: str, **kwargs) -> str:
        """
        Récupère un texte traduit par sa clé.

        Args:
            key: Clé de traduction (ex: 'homepage.title')
            **kwargs: Variables à remplacer dans le texte

        Returns:
            str: Texte traduit ou clé si non trouvée
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
                    print(f"[I18n] Variable manquante dans '{key}': {e}")

            return value
        except (KeyError, TypeError):
            print(f"[I18n] Clé de traduction manquante: {key}")
            return key

    def get_current_language(self) -> str:
        """Retourne le code de la langue actuelle."""
        return self.current_language

    def get_available_languages(self) -> Dict[str, str]:
        """Retourne la liste des langues disponibles."""
        return self.available_languages

    def switch_language(self, language_code: str) -> bool:
        """
        Change la langue active et sauvegarde la préférence.

        Args:
            language_code: Code de la nouvelle langue

        Returns:
            bool: True si le changement a réussi
        """
        if self.load_language(language_code):
            self._save_language_preference(language_code)
            return True
        return False


_i18n_manager = I18nManager()


def get_text(key: str, **kwargs) -> str:
    """
    Fonction raccourci pour récupérer un texte traduit.

    Args:
        key: Clé de traduction
        **kwargs: Variables à remplacer

    Returns:
        str: Texte traduit
    """
    return _i18n_manager.get_text(key, **kwargs)


def switch_language(language_code: str) -> bool:
    """
    Fonction raccourci pour changer la langue.

    Args:
        language_code: Code de la langue

    Returns:
        bool: True si le changement a réussi
    """
    return _i18n_manager.switch_language(language_code)


def get_current_language() -> str:
    """Retourne le code de la langue actuelle."""
    return _i18n_manager.get_current_language()


def get_available_languages() -> Dict[str, str]:
    """Retourne la liste des langues disponibles."""
    return _i18n_manager.get_available_languages()


# Alias pour compatibilité
t = get_text  # Usage: t("homepage.title")
