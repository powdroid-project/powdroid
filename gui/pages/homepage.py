"""
Page d'accueil utilisant PyQt5 avec design moderne et sombre.
Architecture orientée objet améliorée.
"""

import os
from typing import Optional, Callable, Dict, Any
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QFrame,
    QGridLayout,
    QSpacerItem,
    QSizePolicy,
    QScrollArea,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QSize
from PyQt5.QtGui import QPixmap, QFont, QIcon
from core.utils import adb_runner as adb
from gui.i18n import t


class DeviceStatusWidget(QFrame):
    """Widget dédié à l'affichage du statut du périphérique."""

    # Signaux
    device_connected = pyqtSignal(bool)
    device_info_updated = pyqtSignal(dict)

    def __init__(self, ico_dir: Optional[str] = None):
        super().__init__()
        self.ico_dir = ico_dir
        self._current_status = None
        self._setup_widget()
        self._create_widgets()
        self._setup_layout()
        self._apply_styles()

    def _setup_widget(self):
        """Configure les propriétés de base du widget."""
        self.setObjectName("deviceFrame")
        self.setFrameStyle(QFrame.Box)

    def _create_widgets(self):
        """Crée tous les widgets du composant."""
        # Titre de la section
        self.title_label = QLabel(t("homepage.device_status"))
        self.title_label.setFont(QFont("Arial", 16, QFont.Bold))
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setObjectName("sectionTitle")

        # Image du device
        self.device_img_label = QLabel()
        self.device_img_label.setAlignment(Qt.AlignRight)
        self.device_img_label.setFixedSize(180, 180)

        # Label de statut principal
        self.status_label = QLabel(t("common.please_wait"))
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setFont(QFont("Arial", 14, QFont.Bold))

        # Détails du périphérique
        self.details_label = QLabel("")
        self.details_label.setAlignment(Qt.AlignCenter)
        self.details_label.setWordWrap(True)
        self.details_label.setObjectName("deviceDetails")

    def _setup_layout(self):
        """Configure la mise en page du widget."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 10, 20, 10)

        # Titre
        main_layout.addWidget(self.title_label)

        # Contenu horizontal
        content_layout = QHBoxLayout()
        content_layout.addWidget(self.device_img_label)

        # Informations côté droit
        info_layout = QVBoxLayout()
        info_layout.addItem(
            QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Expanding)
        )
        info_layout.addWidget(self.status_label)
        info_layout.addWidget(self.details_label)
        info_layout.addItem(
            QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Expanding)
        )

        content_layout.addLayout(info_layout)
        main_layout.addLayout(content_layout)

    def _apply_styles(self):
        """Applique les styles CSS au widget."""
        self.setStyleSheet(
            """
            QFrame#deviceFrame {
                background-color: #2a2a2a;
                border-radius: 8px;
                border: 1px solid #404040;
            }
            QLabel#sectionTitle {
                color: #ffffff;
                margin-bottom: 15px;
                background-color: transparent;
            }
            QLabel#deviceDetails {
                color: #d0d0d0;
                margin-top: 10px;
                background-color: transparent;
            }
        """
        )

    def update_status(
        self, connected: bool, device_info: Optional[Dict[str, Any]] = None
    ):
        """Met à jour le statut du périphérique."""
        if connected == self._current_status:
            return

        self._current_status = connected

        if connected:
            self._show_connected_state(device_info)
        else:
            self._show_disconnected_state()

        self.device_connected.emit(connected)
        if device_info:
            self.device_info_updated.emit(device_info)

    def _show_connected_state(self, device_info: Optional[Dict[str, Any]]):
        """Affiche l'état de périphérique connecté."""
        self.status_label.setText("✅ " + t("homepage.device_connected"))
        self.status_label.setStyleSheet(
            "color: #16a085; font-weight: bold; background-color: transparent;"
        )

        if device_info:
            model = device_info.get("model", "Inconnu")
            manufacturer = device_info.get("manufacturer", "Inconnu")
            android_version = device_info.get("android_version", "N/A")

            details_text = f"""
<b style='color: #ffffff;'>{manufacturer} {model}</b><br>
<span style='color: #c0c0c0;'>Android {android_version}</span>
            """.strip()
            self.details_label.setText(details_text)
        else:
            self.details_label.setText(
                "<span style='color: #c0c0c0;'>Informations détaillées indisponibles</span>"
            )

        self._show_device_image("phone_plugged.png")

    def _show_disconnected_state(self):
        """Affiche l'état de périphérique déconnecté."""
        self.status_label.setText("❌ " + t("homepage.device_disconnected"))
        self.status_label.setStyleSheet(
            "color: #e74c3c; font-weight: bold; background-color: transparent;"
        )

        self.details_label.setText(
            """
<span style='color: #c0c0c0;'>Connectez votre smartphone Android via USB<br>
et activez le débogage USB</span>
        """.strip()
        )

        self._show_device_image("plug_the_phone.png")

    def show_error_state(self, error_message: str = ""):
        """Affiche un état d'erreur."""
        self.status_label.setText("⚠️ Erreur de connexion ADB")
        self.status_label.setStyleSheet(
            "color: #f39c12; font-weight: bold; background-color: transparent;"
        )

        message = error_message or "Vérifiez l'installation ADB"
        self.details_label.setText(f"<span style='color: #c0c0c0;'>{message}</span>")

        self._show_fallback_image()

    def _show_device_image(self, image_name: str):
        """Affiche l'image correspondant au statut."""
        if not self.ico_dir:
            self._show_fallback_image()
            return

        image_path = os.path.join(str(self.ico_dir), image_name)
        if os.path.exists(image_path):
            pixmap = QPixmap(image_path)
            if not pixmap.isNull():
                scaled_pixmap = pixmap.scaled(
                    160, 160, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                self.device_img_label.setStyleSheet("background-color: #2a2a2a;")
                self.device_img_label.setPixmap(scaled_pixmap)
                return

        self._show_fallback_image()

    def _show_fallback_image(self):
        """Affiche une image de fallback."""
        self.device_img_label.clear()
        self.device_img_label.setText("📱")
        self.device_img_label.setStyleSheet("font-size: 80px; color: #666666;")


class ActionButtonsWidget(QFrame):
    """Widget pour les boutons d'action principaux."""

    # Signaux
    session_requested = pyqtSignal()
    reports_requested = pyqtSignal()
    settings_requested = pyqtSignal()

    def __init__(self, ico_dir: Optional[str] = None):
        super().__init__()
        self.ico_dir = ico_dir
        self._setup_widget()
        self._create_widgets()
        self._setup_layout()
        self._connect_signals()
        self._apply_styles()

    def _setup_widget(self):
        """Configure les propriétés de base du widget."""
        self.setObjectName("actionsFrame")
        self.setFrameStyle(QFrame.Box)

    def _create_widgets(self):
        """Crée tous les widgets du composant."""

        # Bouton principal
        self.session_btn = QPushButton(t("homepage.buttons.start_session"))
        self.session_btn.setObjectName("primaryButton")
        self.session_btn.setEnabled(False)

        # Ajouter icône si disponible
        if self.ico_dir:
            icon_path = os.path.join(str(self.ico_dir), "record.png")
            if os.path.exists(icon_path):
                self.session_btn.setIcon(QIcon(icon_path))
                self.session_btn.setIconSize(QSize(24, 24))

        # Boutons secondaires
        self.reports_btn = QPushButton(t("homepage.buttons.view_reports"))
        self.reports_btn.setObjectName("secondaryButton")
        if self.ico_dir:
            icon_path = os.path.join(str(self.ico_dir), "history.png")
            if os.path.exists(icon_path):
                self.reports_btn.setIcon(QIcon(icon_path))
                self.reports_btn.setIconSize(QSize(24, 24))

        self.settings_btn = QPushButton(t("homepage.buttons.settings"))
        self.settings_btn.setObjectName("secondaryButton")
        if self.ico_dir:
            icon_path = os.path.join(str(self.ico_dir), "settings.png")
            if os.path.exists(icon_path):
                self.settings_btn.setIcon(QIcon(icon_path))
                self.settings_btn.setIconSize(QSize(24, 24))

    def _setup_layout(self):
        """Configure la mise en page du widget."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 10, 20, 10)

        # Grille de boutons
        buttons_grid = QGridLayout()
        buttons_grid.setSpacing(5)

        buttons_grid.addWidget(self.session_btn, 0, 0, 1, 2)
        buttons_grid.addWidget(self.reports_btn, 1, 0)
        buttons_grid.addWidget(self.settings_btn, 1, 1)

        main_layout.addLayout(buttons_grid)

    def _connect_signals(self):
        """Connecte les signaux des boutons."""
        self.session_btn.clicked.connect(self.session_requested.emit)
        self.reports_btn.clicked.connect(self.reports_requested.emit)
        self.settings_btn.clicked.connect(self.settings_requested.emit)

    def _apply_styles(self):
        """Applique les styles CSS au widget."""
        self.setStyleSheet(
            """
            QFrame#actionsFrame {
                background-color: #2a2a2a;
                border-radius: 8px;
                border: 1px solid #404040;
            }
            QLabel#sectionTitle {
                color: #ffffff;
                margin-bottom: 5px;
                background-color: transparent;
            }
            QPushButton#primaryButton {
                background-color: #34495e;
                padding: 5px 10px;
                font-size: 13px;
                border: none;
                border-radius: 6px;
                color: white;
                font-weight: bold;
            }
            QPushButton#primaryButton:hover:enabled {
                background-color: #2c3e50;
            }
            QPushButton#primaryButton:pressed:enabled {
                background-color: #117864;
            }
            QPushButton#primaryButton:disabled {
                background-color: #404040;
                color: #888888;
            }
            QPushButton#secondaryButton {
                background-color: #34495e;
                padding: 10px 20px;
                font-size: 13px;
                border: none;
                border-radius: 6px;
                color: white;
                font-weight: bold;
            }
            QPushButton#secondaryButton:hover:enabled {
                background-color: #2c3e50;
            }
        """
        )

    def set_session_enabled(self, enabled: bool):
        """Active/désactive le bouton de session."""
        self.session_btn.setEnabled(enabled)


class InstructionsWidget(QFrame):
    """Widget pour afficher les instructions d'utilisation."""

    def __init__(self):
        super().__init__()
        self._setup_widget()
        self._create_widgets()
        self._setup_layout()
        self._apply_styles()

    def _setup_widget(self):
        """Configure les propriétés de base du widget."""
        self.setObjectName("instructionsFrame")
        self.setFrameStyle(QFrame.Box)

    def _create_widgets(self):
        """Crée tous les widgets du composant."""
        # Titre
        self.title_label = QLabel("📋 " + t("homepage.instructions.title"))
        self.title_label.setFont(QFont("Arial", 14, QFont.Bold))
        self.title_label.setObjectName("sectionTitle")

        # Labels des étapes
        self.step_labels = []
        steps = [
            t("homepage.instructions.step1"),
            t("homepage.instructions.step2"),
            t("homepage.instructions.step3"),
            t("homepage.instructions.step4"),
        ]

        for i, step in enumerate(steps, 1):
            label = QLabel(f"{step}")
            label.setWordWrap(True)
            label.setObjectName("instructionStep")
            self.step_labels.append(label)

    def _setup_layout(self):
        """Configure la mise en page du widget."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(25, 20, 25, 20)

        # Titre
        main_layout.addWidget(self.title_label)

        # Étapes
        for label in self.step_labels:
            main_layout.addWidget(label)

    def _apply_styles(self):
        """Applique les styles CSS au widget."""
        self.setStyleSheet(
            """
            QFrame#instructionsFrame {
                background-color: #2a2a2a;
                border-radius: 8px;
                border: 1px solid #404040;
            }
            QLabel#sectionTitle {
                color: #ffffff;
                margin-bottom: 15px;
                background-color: transparent;
            }
            QLabel#instructionStep {
                color: #d0d0d0;
                margin-bottom: 8px;
                padding-left: 15px;
                background-color: transparent;
            }
        """
        )


class HeaderWidget(QFrame):
    """Widget pour l'en-tête de la page."""

    def __init__(self, ico_dir: Optional[str] = None):
        super().__init__()
        self.ico_dir = ico_dir
        self._setup_widget()
        self._create_widgets()
        self._setup_layout()
        self._apply_styles()

    def _setup_widget(self):
        """Configure les propriétés de base du widget."""
        self.setObjectName("headerFrame")

    def _create_widgets(self):
        """Crée tous les widgets du composant."""
        # Logo
        self.logo_label = None
        if self.ico_dir:
            logo_path = os.path.join(str(self.ico_dir), "powdroid_banner.png")
            if os.path.exists(logo_path):
                self.logo_label = QLabel()
                pixmap = QPixmap(logo_path)
                if not pixmap.isNull():
                    scaled_pixmap = pixmap.scaled(
                        350, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation
                    )
                    self.logo_label.setPixmap(scaled_pixmap)
                    self.logo_label.setAlignment(Qt.AlignCenter)

        # Titre principal
        self.title_label = QLabel(t("homepage.welcome"))
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setFont(QFont("Arial", 26, QFont.Bold))
        self.title_label.setObjectName("mainTitle")

        # Sous-titre
        self.subtitle_label = QLabel(t("homepage.subtitle"))
        self.subtitle_label.setAlignment(Qt.AlignCenter)
        self.subtitle_label.setFont(QFont("Arial", 14))
        self.subtitle_label.setObjectName("subtitle")

    def _setup_layout(self):
        """Configure la mise en page du widget."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Logo (si disponible)
        if self.logo_label:
            logo_layout = QHBoxLayout()
            logo_layout.addItem(
                QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
            )
            logo_layout.addWidget(self.logo_label)
            logo_layout.addItem(
                QSpacerItem(10, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
            )
            main_layout.addLayout(logo_layout)

        # Titres
        main_layout.addWidget(self.title_label)
        main_layout.addWidget(self.subtitle_label)

    def _apply_styles(self):
        """Applique les styles CSS au widget."""
        self.setStyleSheet(
            """
            QFrame#headerFrame {
                background-color: transparent;
            }
            QLabel#mainTitle {
                color: #ffffff;
                margin: 5px 0;
                background-color: transparent;
            }
            QLabel#subtitle {
                color: #c0c0c0;
                margin-bottom: 5px;
                background-color: transparent;
            }
        """
        )


class HomePage(QWidget):
    """Page d'accueil moderne de l'application avec architecture orientée objet."""

    def __init__(
        self,
        ico_dir: Optional[str] = None,
        switch_to_session_callback: Optional[Callable] = None,
    ):
        super().__init__()
        self.ico_dir = ico_dir
        self.switch_to_session_callback = switch_to_session_callback

        # Timer pour vérifier le statut du device
        self.device_timer = QTimer()

        self._setup_ui()
        self._create_widgets()
        self._setup_layout()
        self._connect_signals()
        self._apply_theme()
        self._start_device_monitoring()

    def _setup_ui(self):
        """Configure les propriétés de base de l'interface."""
        self.setObjectName("homePage")

    def _create_widgets(self):
        """Crée tous les widgets de la page."""
        # Zone de défilement
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setObjectName("scrollArea")

        self.scroll_widget = QWidget()

        # Widgets principaux
        self.header_widget = HeaderWidget(self.ico_dir)
        self.device_widget = DeviceStatusWidget(self.ico_dir)
        self.actions_widget = ActionButtonsWidget(self.ico_dir)
        self.instructions_widget = InstructionsWidget()

    def _setup_layout(self):
        """Configure la mise en page de la page."""
        # Layout principal
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Layout de la zone de défilement
        scroll_layout = QVBoxLayout(self.scroll_widget)
        scroll_layout.setSpacing(5)

        # Ajout des widgets
        scroll_layout.addWidget(self.header_widget)
        scroll_layout.addWidget(self.device_widget)
        scroll_layout.addWidget(self.actions_widget)
        scroll_layout.addWidget(self.instructions_widget)

        # Espacement final
        scroll_layout.addItem(
            QSpacerItem(20, 30, QSizePolicy.Minimum, QSizePolicy.Fixed)
        )

        # Configuration finale
        self.scroll_area.setWidget(self.scroll_widget)
        main_layout.addWidget(self.scroll_area)

    def _connect_signals(self):
        """Connecte tous les signaux de la page."""
        # Timer
        self.device_timer.timeout.connect(self._check_device_status)

        # Signaux inter-widgets
        self.device_widget.device_connected.connect(
            self.actions_widget.set_session_enabled
        )

        # Signaux des actions
        self.actions_widget.session_requested.connect(self._start_new_session)
        self.actions_widget.reports_requested.connect(self._show_reports)
        self.actions_widget.settings_requested.connect(self._show_settings)

    def _apply_theme(self):
        """Applique le thème sombre global."""
        self.setStyleSheet(
            """
            QWidget {
                background-color: #1e1e1e;
                color: #ffffff;
            }
            QScrollArea#scrollArea {
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

    def _start_device_monitoring(self):
        """Démarre la surveillance du périphérique."""
        self._check_device_status()
        self.device_timer.start(2000)  # Vérifie toutes les 2 secondes

    def _check_device_status(self):
        """Vérifie le statut du périphérique connecté."""
        try:
            device_connected = adb.is_device_connected()
            device_info = None

            if device_connected:
                device_info = adb.get_device_info()

            self.device_widget.update_status(device_connected, device_info)

        except Exception as e:
            print(f"[ERROR] Erreur vérification périphérique: {e}")
            self.device_widget.show_error_state(str(e))

    def _start_new_session(self):
        """Démarre une nouvelle session d'enregistrement."""
        if self.switch_to_session_callback:
            self.switch_to_session_callback()

    def _show_reports(self):
        """Affiche les rapports (à implémenter)."""
        print("[DEBUG] Affichage des rapports demandé")

    def _show_settings(self):
        """Affiche les paramètres (à implémenter)."""
        print("[DEBUG] Affichage des paramètres demandé")

    def closeEvent(self, event):
        """Nettoyage lors de la fermeture."""
        if hasattr(self, "device_timer"):
            self.device_timer.stop()
        event.accept()
