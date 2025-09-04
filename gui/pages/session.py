"""
Page de session d'enregistrement utilisant PyQt5.
Version robuste avec gestion proper des threads et signaux.
"""

import os
from datetime import datetime
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QProgressBar,
    QFrame,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt5.QtGui import QPixmap, QFont
from core.utils import adb_runner as adb
from gui.i18n import t


class ImageOverlay(QWidget):
    """Widget overlay pour afficher les images par-dessus l'interface."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")
        self._setup_ui()

    def _setup_ui(self):
        """Configuration de l'interface overlay."""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        # Container principal avec background semi-transparent
        self.container = QFrame()
        self.container.setStyleSheet(
            """
            QFrame {
                background-color: rgba(30, 30, 30, 0.9);
                border-radius: 15px;
                border: 2px solid #404040;
            }
        """
        )
        container_layout = QVBoxLayout()
        container_layout.setContentsMargins(40, 40, 40, 40)
        container_layout.setSpacing(20)
        self.container.setLayout(container_layout)

        # Image label
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet(
            """
            QLabel {
                background-color: transparent;
                border: none;
                padding: 20px;
            }
        """
        )
        container_layout.addWidget(self.image_label)

        # Message label
        self.message_label = QLabel()
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setWordWrap(True)
        self.message_label.setStyleSheet(
            """
            QLabel {
                color: #ffffff;
                font-size: 16px;
                font-weight: 600;
                padding: 15px;
                background-color: transparent;
                border: none;
            }
        """
        )
        container_layout.addWidget(self.message_label)

        # Centrer le container dans l'overlay
        layout.addWidget(self.container, 0, Qt.AlignCenter)

    def show_image_message(self, image_path, message, color):
        """Affiche l'image et le message dans l'overlay."""
        # Chargement de l'image
        full_path = os.path.join(
            os.path.dirname(__file__), "..", "ressources", image_path
        )
        if os.path.exists(full_path):
            pixmap = QPixmap(full_path)
            if not pixmap.isNull():
                scaled_pixmap = pixmap.scaled(
                    150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                self.image_label.setPixmap(scaled_pixmap)

        # Configuration du message avec la couleur
        self.message_label.setText(message)
        current_style = self.message_label.styleSheet()
        new_style = current_style.replace("color: #ffffff;", f"color: {color};")
        self.message_label.setStyleSheet(new_style)

        # Redimensionner l'overlay pour couvrir tout le parent
        if self.parent():
            self.resize(self.parent().size())

        self.show()
        self.raise_()

    def resizeEvent(self, event):
        """Redimensionne l'overlay quand la fenêtre parent change."""
        super().resizeEvent(event)
        # S'assurer que l'overlay couvre tout l'espace parent
        if self.parent():
            self.resize(self.parent().size())


class RecordingWorker(QThread):
    """Worker thread pour les opérations d'enregistrement."""

    # Signaux pour communication avec l'UI
    status_changed = pyqtSignal(str, str)  # message, color
    show_image = pyqtSignal(str, str, str)  # image_path, message, color
    hide_image = pyqtSignal()
    recording_started = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.operation = None

    def set_operation(self, operation):
        """Définit l'opération à effectuer: 'start' ou 'stop'."""
        self.operation = operation

    def run(self):
        """Exécute l'opération dans le thread worker."""
        try:
            if self.operation == "start":
                self._start_recording()
            elif self.operation == "stop":
                self._stop_recording()
        except Exception as e:
            self.error_occurred.emit(str(e))

    def _start_recording(self):
        """Processus de démarrage d'enregistrement."""

        # Préparation ADB
        self.status_changed.emit(t("session.status.preparing"), "#1976d2")
        adb.kill_all()
        adb.clear_batterystats(verbose=False)

        # Affichage message de débranchement
        self.show_image.emit(
            "plug_the_phone.png", t("session.messages.disconnect_device"), "#e67e22"
        )

        # Attente déconnexion
        adb.wait_for_device_disconnection(verbose=False)

        # Nettoyage UI et signal de démarrage
        self.hide_image.emit()
        self.recording_started.emit()

    def _stop_recording(self):
        """Processus d'arrêt d'enregistrement."""

        # Affichage message de reconnexion
        self.show_image.emit(
            "plug_the_phone.png", t("session.messages.reconnect_device"), "#1976d2"
        )

        # Attente reconnexion
        adb.wait_for_device_connection(verbose=False)

        # Nettoyage UI
        self.hide_image.emit()
        self.status_changed.emit(t("session.messages.device_reconnected"), "#1976d2")

        # Extraction des données
        self.status_changed.emit(t("session.messages.extracting_data"), "#1976d2")

        try:
            adb.dump_batterystats(verbose=False)
            self.status_changed.emit(
                t("session.messages.generating_reports"), "#1976d2"
            )
        except Exception as e:
            print(f"[DEBUG] Worker: Erreur dump: {e}")
            self.error_occurred.emit(f"Erreur dump: {str(e)}")
            return

        # Finalisation
        self.status_changed.emit(t("session.status.completed"), "#388e3c")


class SessionPage(QWidget):
    """Page de gestion des sessions d'enregistrement avec PyQt5."""

    def __init__(self, switch_to_home_callback=None):
        super().__init__()
        self.switch_to_home_callback = switch_to_home_callback

        # Définit le thème sombre cohérent avec la homepage
        self.setStyleSheet(
            """
            QWidget {
                background-color: #1e1e1e;
                color: #ffffff;
            }
        """
        )

        # État
        self._recording = False
        self.start_time = None
        self.end_time = None

        # Timer pour la durée
        self.duration_timer = QTimer()
        self.duration_timer.timeout.connect(self._update_duration)

        # Worker thread
        self.worker = RecordingWorker()
        self._connect_worker_signals()

        # Widgets temporaires
        self.temp_img_label = None
        self.temp_text_label = None

        # Overlay pour les images
        self.image_overlay = ImageOverlay(self)
        self.image_overlay.hide()

        self._init_ui()

    def _connect_worker_signals(self):
        """Connecte les signaux du worker aux slots de l'UI."""
        self.worker.status_changed.connect(self._update_status)
        self.worker.show_image.connect(self._show_temp_image)
        self.worker.hide_image.connect(self._hide_temp_image)
        self.worker.recording_started.connect(self._on_recording_started)
        self.worker.error_occurred.connect(self._handle_error)
        self.worker.finished.connect(self._on_worker_finished)

    def _init_ui(self):
        """Initialise l'interface utilisateur."""
        layout = QVBoxLayout()
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        self.setLayout(layout)

        # Titre de la page
        title_label = QLabel("🎙️ " + t("session.title"))
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet(
            """
            QLabel {
                color: #ffffff;
                font-size: 26px;
                font-weight: bold;
                margin-bottom: 20px;
                padding: 15px;
                background-color: transparent;
            }
        """
        )
        layout.addWidget(title_label)

        # Frame principal avec bordure moderne - thème sombre
        main_frame = QFrame()
        main_frame.setStyleSheet(
            """
            QFrame {
                background-color: #2a2a2a;
                border: 1px solid #404040;
                border-radius: 15px;
            }
        """
        )
        layout.addWidget(main_frame)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(40, 40, 40, 40)
        main_layout.setSpacing(25)
        main_frame.setLayout(main_layout)

        # Container pour le statut avec icône
        status_container = QFrame()
        status_container.setStyleSheet(
            """
            QFrame {
                background-color: #2a2a2a;
                border: 1px solid #404040;
                border-radius: 10px;
                padding: 20px;
            }
        """
        )
        status_layout = QVBoxLayout()
        status_container.setLayout(status_layout)

        # Label de statut avec style moderne
        self.status_label = QLabel("● " + t("session.status.ready"))
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet(
            """
            QLabel {
                color: #ffffff;
                font-size: 18px;
                font-weight: 600;
                padding: 15px;
                background-color: #333333;
                border-radius: 8px;
                border: 1px solid #555555;
                margin-bottom: 10px;
            }
        """
        )
        status_layout.addWidget(self.status_label)

        # Label de durée avec design amélioré
        self.duration_label = QLabel(t("session.duration_label") + " 00:00:00")
        self.duration_label.setAlignment(Qt.AlignCenter)
        self.duration_label.setStyleSheet(
            """
            QLabel {
                color: #d0d0d0;
                font-size: 16px;
                font-weight: 500;
                font-family: 'Courier New', monospace;
                padding: 12px;
                background-color: #333333;
                border-radius: 6px;
                border: 1px solid #555555;
            }
        """
        )
        status_layout.addWidget(self.duration_label)

        main_layout.addWidget(status_container)

        # Barre de progression moderne
        progress_container = QFrame()
        progress_container.setStyleSheet(
            """
            QFrame {
                background-color: #2a2a2a;
                border: 1px solid #404040;
                border-radius: 10px;
                padding: 20px;
            }
        """
        )
        progress_layout = QVBoxLayout()
        progress_container.setLayout(progress_layout)

        progress_title = QLabel("📊 " + t("session.progress"))
        progress_title.setStyleSheet(
            """
            QLabel {
                color: #ffffff;
                font-size: 14px;
                font-weight: 600;
                margin-bottom: 10px;
                background-color: transparent;
            }
        """
        )
        progress_layout.addWidget(progress_title)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet(
            """
            QProgressBar {
                border: 2px solid #555555;
                border-radius: 12px;
                text-align: center;
                height: 24px;
                background-color: #333333;
                font-weight: 600;
                color: #ffffff;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #16a085, stop:1 #1abc9c);
                border-radius: 10px;
                margin: 2px;
            }
        """
        )
        progress_layout.addWidget(self.progress_bar)

        main_layout.addWidget(progress_container)

        # Boutons
        self._create_buttons(main_layout)

    def _create_buttons(self, layout):
        """Crée les boutons de contrôle."""
        # Container pour les boutons avec style
        btn_container = QFrame()
        btn_container.setStyleSheet(
            """
            QFrame {
                background-color: #2a2a2a;
                border: 1px solid #404040;
                border-radius: 12px;
                padding: 20px;
                margin-top: 10px;
            }
        """
        )
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(15)
        btn_container.setLayout(btn_layout)

        # Bouton Enregistrer avec design moderne sombre
        self.record_btn = QPushButton("🔴 " + t("session.buttons.start"))
        self.record_btn.clicked.connect(self.start_recording)
        self.record_btn.setMinimumHeight(50)
        self.record_btn.setStyleSheet(
            """
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #e74c3c, stop:1 #c0392b);
                color: white;
                border: none;
                padding: 12px 24px;
                font-size: 16px;
                font-weight: bold;
                border-radius: 25px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #c0392b, stop:1 #a93226);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #a93226, stop:1 #922b21);
            }
            QPushButton:disabled {
                background-color: #555555;
                color: #888888;
            }
        """
        )
        btn_layout.addWidget(self.record_btn)

        # Bouton Arrêter avec design moderne sombre
        self.stop_btn = QPushButton("⏹ " + t("session.buttons.stop"))
        self.stop_btn.clicked.connect(self.stop_recording)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setMinimumHeight(50)
        self.stop_btn.setStyleSheet(
            """
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #95a5a6, stop:1 #7f8c8d);
                color: white;
                border: none;
                padding: 12px 24px;
                font-size: 16px;
                font-weight: bold;
                border-radius: 25px;
            }
            QPushButton:hover:enabled {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #7f8c8d, stop:1 #6c7b7d);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #6c7b7d, stop:1 #5d6d6e);
            }
            QPushButton:disabled {
                background-color: #555555;
                color: #888888;
            }
        """
        )
        btn_layout.addWidget(self.stop_btn)

        # Bouton Accueil avec design moderne sombre
        self.home_btn = QPushButton("🏠 " + t("session.buttons.home"))
        self.home_btn.clicked.connect(self.go_home)
        self.home_btn.setMinimumHeight(50)
        self.home_btn.setStyleSheet(
            """
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3498db, stop:1 #2980b9);
                color: white;
                border: none;
                padding: 12px 24px;
                font-size: 16px;
                font-weight: bold;
                border-radius: 25px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2980b9, stop:1 #1f5f8b);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1f5f8b, stop:1 #174a6b);
            }
        """
        )
        btn_layout.addWidget(self.home_btn)

        layout.addWidget(btn_container)

    def start_recording(self):
        """Démarre l'enregistrement."""
        print("[DEBUG] UI: Début start_recording")

        self._recording = True
        self.start_time = None  # Sera défini après déconnexion

        # Mise à jour UI
        self.status_label.setText("● " + t("session.status.recording"))
        self.status_label.setStyleSheet("color: #e53935;")
        self.progress_bar.setValue(10)
        self.record_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        # Lancement du worker
        if not self.worker.isRunning():
            self.worker.set_operation("start")
            self.worker.start()

    def stop_recording(self):
        """Arrête l'enregistrement."""
        print("[DEBUG] UI: Début stop_recording")

        self._recording = False
        self.end_time = datetime.now()

        # Arrêt du timer
        self.duration_timer.stop()

        # Lancement du worker
        if not self.worker.isRunning():
            self.worker.set_operation("stop")
            self.worker.start()

    def _update_status(self, text, color):
        """Met à jour le statut affiché."""
        self.status_label.setText("● " + text)

        # Mise à jour du style avec la couleur appropriée
        base_style = """
            QLabel {
                font-size: 18px;
                font-weight: 600;
                padding: 15px;
                background-color: #333333;
                border-radius: 8px;
                border: 1px solid #555555;
                margin-bottom: 10px;
            }
        """
        self.status_label.setStyleSheet(base_style + f"color: {color};")

        # Animation subtile pour le changement de statut
        if hasattr(self.status_label, "effect"):
            self.status_label.effect.deleteLater()

        # Effet d'ombre pour le statut actif
        if "recording" in text.lower() or "enregistrement" in text.lower():
            from PyQt5.QtWidgets import QGraphicsDropShadowEffect
            from PyQt5.QtCore import QPropertyAnimation, pyqtProperty

            effect = QGraphicsDropShadowEffect()
            effect.setBlurRadius(10)
            effect.setColor(Qt.red)
            effect.setOffset(0, 0)
            self.status_label.setGraphicsEffect(effect)
            self.status_label.effect = effect

    def _show_temp_image(self, image_path, message, color):
        """Affiche une image et un message temporaire via l'overlay."""
        self.image_overlay.show_image_message(image_path, message, color)

    def _hide_temp_image(self):
        """Cache l'image temporaire."""
        self.image_overlay.hide()

    def _on_recording_started(self):
        """Callback appelé quand l'enregistrement démarre."""
        self.start_time = datetime.now()
        self.status_label.setText("● " + t("session.status.recording"))
        self.status_label.setStyleSheet(
            """
            QLabel {
                color: #e74c3c;
                font-size: 18px;
                font-weight: 600;
                padding: 15px;
                background-color: #333333;
                border-radius: 8px;
                border: 2px solid #e74c3c;
                margin-bottom: 10px;
            }
        """
        )
        self.duration_timer.start(1000)  # Mise à jour chaque seconde

    def _on_worker_finished(self):
        """Callback appelé quand le worker termine."""
        if not self._recording:  # Si on était en train d'arrêter
            self.progress_bar.setValue(100)
            self.record_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)

            # Affichage durée finale
            if self.start_time and self.end_time:
                duration = self.end_time - self.start_time
                self.duration_label.setText(
                    f"{t('session.duration_label')} {self._format_duration(duration)}"
                )

    def _handle_error(self, error_msg):
        """Gère les erreurs."""
        self._hide_temp_image()
        self._recording = False
        self.duration_timer.stop()

        self.status_label.setText(f"{t('common.errors')} : {error_msg}")
        self.status_label.setStyleSheet("color: #e53935;")
        self.progress_bar.setValue(0)
        self.record_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def _update_duration(self):
        """Met à jour l'affichage de la durée."""
        if self._recording and self.start_time:
            now = datetime.now()
            duration = now - self.start_time
            self.duration_label.setText(
                f"{t('session.duration_label')} {self._format_duration(duration)}"
            )

    @staticmethod
    def _format_duration(duration):
        """Formate une durée en HH:MM:SS."""
        total_seconds = int(duration.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02}:{minutes:02}:{seconds:02}"

    def go_home(self):
        """Retourne à l'accueil."""
        if self.switch_to_home_callback:
            self.switch_to_home_callback()
