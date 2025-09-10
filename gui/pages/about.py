"""
Fenêtre à propos.
"""

import os
import webbrowser
from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QScrollArea,
    QWidget,
    QSpacerItem,
    QSizePolicy,
)
from PyQt5.QtCore import Qt, QUrl, pyqtSignal
from PyQt5.QtGui import QFont, QPixmap, QIcon, QPalette, QDesktopServices
from gui.i18n import t


class AboutDialog(QDialog):

    def __init__(self, parent, ico_dir):
        super().__init__(parent)
        self.ico_dir = ico_dir
        self._setup_dialog()
        self._create_widgets()
        self._setup_layout()
        self._connect_signals()
        self._apply_styles()

    def _setup_dialog(self):
        """Configure les propriétés de base de la fenêtre."""
        self.setWindowTitle(t("about.title"))
        self.setFixedSize(550, 800)
        self.setModal(True)

        # Icône de la fenêtre
        icon_path = os.path.join(self.ico_dir, "powdroid_logo.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

    def _create_widgets(self):
        """Crée tous les widgets de l'interface."""
        # Widgets principaux
        self.scroll_area = QScrollArea()
        self.scroll_widget = QWidget()

        # Header
        self.header_frame = QFrame()
        self.header_frame.setObjectName("headerFrame")

        self.logo_label = self._create_logo_label("powdroid_logo.png", 80)
        self.title_label = self._create_title_label()
        self.version_label = self._create_version_label()
        self.description_label = self._create_description_label()

        # Content
        self.content_frame = QFrame()
        self.content_frame.setObjectName("contentFrame")

        self.features_section = self._create_features_section()
        self.credits_section = self._create_credits_section()
        self.uppa_logo = self._create_logo_label("uppa.png", 120)

        # Buttons
        self.close_btn = self._create_close_button()

    def _create_logo_label(self, filename, size):
        """Crée un label avec logo redimensionné."""
        label = QLabel()
        logo_path = os.path.join(self.ico_dir, filename)
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path)
            scaled_pixmap = pixmap.scaled(
                size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            label.setPixmap(scaled_pixmap)
        label.setAlignment(Qt.AlignCenter)
        return label

    def _create_title_label(self):
        """Crée le titre principal."""
        label = QLabel(t("app.name"))
        label.setAlignment(Qt.AlignCenter)
        font = QFont()
        font.setPointSize(24)
        font.setBold(True)
        label.setFont(font)
        label.setObjectName("titleLabel")
        return label

    def _create_version_label(self):
        """Crée le label de version."""
        label = QLabel(t("about.version").format(version=t("app.version")))
        label.setAlignment(Qt.AlignCenter)
        font = QFont()
        font.setPointSize(12)
        label.setFont(font)
        label.setObjectName("versionLabel")
        return label

    def _create_description_label(self):
        """Crée la description principale."""
        label = QLabel(t("about.description"))
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(True)
        font = QFont()
        font.setPointSize(11)
        label.setFont(font)
        label.setObjectName("descriptionLabel")
        return label

    def _create_features_section(self):
        """Crée la section des fonctionnalités."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Titre
        title = QLabel(t("about.features.title"))
        title.setFont(QFont("Arial", 14, QFont.Bold))
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        # Liste des fonctionnalités
        features = [
            t("about.features.battery_analysis"),
            t("about.features.csv_export"),
            t("about.features.html_reports"),
            t("about.features.real_time"),
            t("about.features.detailed_stats"),
        ]

        for feature in features:
            label = QLabel(f"• {feature}")
            label.setWordWrap(True)
            label.setObjectName("featureItem")
            layout.addWidget(label)

        return widget

    def _create_credits_section(self):
        """Crée la section des crédits."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Titre
        title = QLabel(t("about.credits.title"))
        title.setFont(QFont("Arial", 14, QFont.Bold))
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        # Informations de crédit
        credits = [
            t("about.credits.developed_by"),
            t("about.credits.university"),
            t("about.credits.license"),
        ]

        for credit in credits:
            label = QLabel(credit)
            label.setWordWrap(True)
            label.setObjectName("creditItem")
            layout.addWidget(label)

        return widget

    def _create_close_button(self):
        """Crée le bouton de fermeture."""
        btn = QPushButton(t("common.close"))
        btn.setObjectName("closeButton")
        btn.setMinimumWidth(100)
        return btn

    def _setup_layout(self):
        """Configure la mise en page de l'interface."""
        # Layout principal
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 10, 20, 10)

        # Configuration de la zone de défilement
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)

        scroll_layout = QVBoxLayout(self.scroll_widget)
        scroll_layout.setSpacing(10)

        # Header layout
        header_layout = QVBoxLayout(self.header_frame)
        header_layout.setContentsMargins(20, 20, 20, 20)
        header_layout.setSpacing(10)

        header_layout.addWidget(self.logo_label)
        header_layout.addWidget(self.title_label)
        header_layout.addWidget(self.version_label)
        header_layout.addWidget(self.description_label)

        # Content layout
        content_layout = QVBoxLayout(self.content_frame)
        content_layout.setContentsMargins(30, 30, 30, 30)
        content_layout.setSpacing(20)

        content_layout.addWidget(self.features_section)
        content_layout.addItem(
            QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Fixed)
        )
        content_layout.addWidget(self.credits_section)
        content_layout.addItem(
            QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Fixed)
        )
        content_layout.addWidget(self.uppa_logo)

        # Assemblage du scroll
        scroll_layout.addWidget(self.header_frame)
        scroll_layout.addWidget(self.content_frame)
        scroll_layout.addStretch()

        self.scroll_area.setWidget(self.scroll_widget)
        main_layout.addWidget(self.scroll_area)

        # Boutons d'action
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)

        main_layout.addLayout(buttons_layout)

        # Bouton fermer
        close_layout = QHBoxLayout()
        close_layout.addStretch()
        close_layout.addWidget(self.close_btn)
        close_layout.addStretch()

        main_layout.addLayout(close_layout)

    def _connect_signals(self):
        """Connecte les signaux aux slots."""
        self.close_btn.clicked.connect(self.accept)

    def _apply_styles(self):
        """Applique les styles CSS à l'interface."""
        self.setStyleSheet(
            """
            QDialog {
                background-color: #1e1e1e;
                color: #ffffff;
            }
            
            QLabel {
                color: #ffffff;
            }
            
            QLabel#titleLabel {
                color: #ffffff;
                margin: 10px 0;
            }
            
            QLabel#versionLabel {
                color: #b0b0b0;
                margin-bottom: 10px;
            }
            
            QLabel#descriptionLabel {
                color: #e0e0e0;
                margin-bottom: 20px;
            }
            
            QLabel#sectionTitle {
                color: #ffffff;
                margin-bottom: 10px;
                margin-top: 5px;
            }
            
            QLabel#featureItem, QLabel#creditItem {
                color: #d0d0d0;
                margin-left: 10px;
                margin-bottom: 5px;
            }
            
            QPushButton#actionButton {
                background-color: #0078d4;
                color: white;
                border: none;
                padding: 10px 16px;
                border-radius: 6px;
                font-weight: bold;
                min-height: 20px;
            }
            
            QPushButton#actionButton:hover {
                background-color: #106ebe;
            }
            
            QPushButton#actionButton:pressed {
                background-color: #005a9e;
            }
            
            QPushButton#closeButton {
                background-color: #333333;
                color: #ffffff;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-weight: bold;
            }
            
            QPushButton#closeButton:hover {
                background-color: #404040;
            }
            
            QPushButton#closeButton:pressed {
                background-color: #555555;
            }
            
            QFrame#contentFrame {
                background-color: #2a2a2a;
                border-radius: 8px;
                border: 1px solid #404040;
            }
            
            QFrame#headerFrame {
                background-color: transparent;
            }
            
            QScrollArea {
                background-color: #1e1e1e;
                border: none;
            }
            
            QScrollBar:vertical {
                background-color: #2a2a2a;
                width: 12px;
                border-radius: 6px;
            }
            
            QScrollBar::handle:vertical {
                background-color: #555555;
                border-radius: 6px;
                min-height: 20px;
            }
            
            QScrollBar::handle:vertical:hover {
                background-color: #666666;
            }
        """
        )


def show_about_window(parent, ico_dir):
    """Affiche la fenêtre À propos avec un design moderne."""
    dialog = AboutDialog(parent, ico_dir)
    dialog.exec_()
