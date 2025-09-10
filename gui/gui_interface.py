#!/usr/bin/env python3
"""
Interface graphique principale utilisant PyQt5 pour PowDroid.
Version migr√©e depuis customtkinter vers PyQt pour plus de robustesse.
"""

import sys
import os
from pathlib import Path
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QStackedWidget,
    QFrame,
    QProgressBar,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt5.QtGui import QPixmap, QIcon, QFont

from gui.pages.homepage import HomePage
from gui.pages.session import SessionPage
from gui.pages.about import show_about_window
from gui.pages.setup import show_setup_window
from gui.i18n import t


class MainWindow(QMainWindow):
    """Fenêtre principale de l'application PowDroid."""

    def __init__(self):
        super().__init__()
        self.ico_dir = Path(__file__).resolve().parent / "ressources"
        self.init_ui()
        self.setup_pages()

    def init_ui(self):
        """Initialise l'interface utilisateur principale."""
        self.setWindowTitle(t("app.name"))
        self.setFixedSize(700, 900)
        # Icône de l'application
        try:
            icon_path = str(self.ico_dir / "powdroid_logo.ico")
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
        except Exception as e:
            print(f"[DEBUG] Erreur chargement icône: {e}")

        # Widget central avec stack pour naviguer entre les pages
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout()
        central_widget.setLayout(layout)

        # Stack widget pour les pages
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)

        # Boutons de navigation en bas
        self.setup_navigation(layout)

    def setup_navigation(self, layout):
        """Configure les boutons de navigation."""
        nav_frame = QFrame()
        nav_layout = QHBoxLayout()
        nav_frame.setLayout(nav_layout)

        # Bouton Setup
        self.setup_btn = QPushButton(t("setup.title"))
        self.setup_btn.clicked.connect(self.show_setup)
        nav_layout.addWidget(self.setup_btn)

        # Bouton About
        self.about_btn = QPushButton(t("about.title"))
        self.about_btn.clicked.connect(self.show_about)
        nav_layout.addWidget(self.about_btn)

        nav_layout.addStretch()  # Pousse les boutons vers la gauche

        layout.addWidget(nav_frame)

    def setup_pages(self):
        """Configure les pages de l'application."""
        # Page d'accueil
        self.home_page = HomePage(
            ico_dir=self.ico_dir, switch_to_session_callback=self.switch_to_session
        )
        self.stack.addWidget(self.home_page)

        # Page de session (créée à la demande)
        self.session_page = None

        # Afficher la page d'accueil par défaut
        self.stack.setCurrentWidget(self.home_page)

    def switch_to_session(self):
        """Navigue vers la page de session."""
        if self.session_page is None:
            self.session_page = SessionPage(switch_to_home_callback=self.switch_to_home)
            self.stack.addWidget(self.session_page)

        self.stack.setCurrentWidget(self.session_page)

    def switch_to_home(self):
        """Navigue vers la page d'accueil."""
        self.stack.setCurrentWidget(self.home_page)

    def show_setup(self):
        """Affiche la fenêtre de configuration."""
        show_setup_window(self, self.ico_dir)

    def show_about(self):
        """Affiche la fenêtre À propos."""
        show_about_window(self, self.ico_dir)


def main():
    """Point d'entrée principal de l'application PyQt."""
    app = QApplication(sys.argv)

    # Style de l'application
    app.setStyle("Fusion")  # Style moderne

    # Fenêtre principale
    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
