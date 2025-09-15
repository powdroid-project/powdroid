"""
Module for the Record page GUI of PowDroid.
"""

import os
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QTextEdit,
    QWidget,
    QFrame,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QSize
from PyQt6.QtGui import QFont, QPixmap, QIcon, QFontDatabase
from typing import Optional
from gui.i18n import t
from gui.popup.about import AboutDialog


class RecordDialog(QDialog):
    """
    Record page for PowDroid.
    """

    # Signal émis quand l'enregistrement est terminé
    recording_finished = pyqtSignal()

    def __init__(
        self, parent: Optional[QWidget] = None, dark_theme="dark", language="en", auto_start=False
    ):
        super().__init__(parent)
        self.dark_theme = dark_theme
        self.language = language
        self.auto_start = auto_start
        self.setModal(True)
        self.setFixedSize(550, 900)

        # Variables pour le déplacement de la fenêtre
        self.dragging = False
        self.drag_position = None

        # Variables pour le timer d'enregistrement
        self.recording_timer = QTimer()
        self.recording_timer.timeout.connect(self.update_duration)
        self.recording_seconds = 0
        self.is_recording = False

        self.load_fonts()

        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.setup_ui()
        self.setup_styles()
        
        # Démarrer automatiquement l'enregistrement si demandé
        if self.auto_start:
            self.start_recording_timer()

    # Ajouter ces méthodes pour gérer le déplacement :
    def mousePressEvent(self, event):
        """Handle mouse press for window dragging."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.drag_position = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()

    def mouseMoveEvent(self, event):
        """Handle mouse move for window dragging."""
        if event.buttons() == Qt.MouseButton.LeftButton and self.dragging:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        """Handle mouse release to stop dragging."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False
            event.accept()

    def start_recording_timer(self):
        """Démarre le timer d'enregistrement."""
        if not self.is_recording:
            self.is_recording = True
            self.recording_timer.start(1000)  # Update every second
            print("[PowDroid] Timer d'enregistrement démarré")

    def stop_recording_timer(self):
        """Arrête le timer d'enregistrement."""
        if self.is_recording:
            self.is_recording = False
            self.recording_timer.stop()
            print(f"[PowDroid] Enregistrement terminé: {self.format_duration(self.recording_seconds)}")

    def update_duration(self):
        """Met à jour l'affichage de la durée d'enregistrement."""
        self.recording_seconds += 1
        if hasattr(self, 'duration_label'):
            self.duration_label.setText(self.format_duration(self.recording_seconds))

    def format_duration(self, seconds):
        """Formate la durée en HH:MM:SS."""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def stop_recording_and_close(self):
        """Arrête l'enregistrement et demande de rebrancher le téléphone."""
        self.stop_recording_timer()
        
        # Afficher la popup pour rebrancher le téléphone
        from gui.popup.information_plug_phone import InformationPopup
        popup = InformationPopup(
            parent=self,
            plugged=False,  # Demande de brancher le téléphone
            dark_theme=self.dark_theme,
            language=self.language
        )
        popup.device_connected.connect(self.on_device_reconnected)  # Utiliser device_connected
        popup.exec()

    def on_device_reconnected(self):
        """Appelé quand l'appareil est rebranché - termine l'enregistrement."""
        print("[PowDroid] Téléphone rebranché, enregistrement terminé")
        self.recording_finished.emit()
        # Ne pas fermer la fenêtre - l'utilisateur peut voir la durée finale

    def load_fonts(self):
        """Loads custom fonts from the fonts folder."""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        base_dir = os.path.join(current_dir, "..", "..")
        font_paths = [
            os.path.join(base_dir, "gui", "ressources", "fonts", "Inter.ttf"),
            os.path.join(base_dir, "gui", "ressources", "fonts", "Inter-Italic.ttf"),
        ]

        self.font_family = "Arial"

        for font_path in font_paths:
            font_path = os.path.normpath(font_path)

            if not os.path.exists(font_path):
                continue

            font_id = QFontDatabase.addApplicationFont(font_path)
            if font_id != -1:
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    self.font_family = families[0]
                    break

    def show_about_page(self):
        dialog = AboutDialog(self, dark_theme=self.dark_theme, language=self.language)
        dialog.exec()

    def setup_ui(self):
        """Configure the user interface for recording."""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.main_frame = QFrame()

        content_layout = QVBoxLayout()
        content_layout.setSpacing(10)
        content_layout.setContentsMargins(20, 20, 20, 20)

        # Header avec boutons theme et close (identique à homepage)
        header_buttons_layout = QHBoxLayout()
        header_buttons_layout.setSpacing(10)
        header_buttons_layout.setContentsMargins(0, 0, 0, 0)

        self.theme_button = QLabel(self)
        self.theme_button.setPixmap(
            QPixmap("gui/ressources/dark_light.png").scaled(
                40,
                40,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.theme_button.setFixedSize(40, 40)
        self.theme_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_button.setToolTip("Toggle Dark/Light Theme")

        def toggle_theme(event):
            self.toggle_theme()

        self.theme_button.mousePressEvent = toggle_theme

        close_button = QLabel(self)
        if self.dark_theme == "dark":
            close_button.setPixmap(
                QPixmap("gui/ressources/close_white.png").scaled(
                    40,
                    40,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            close_button.setPixmap(
                QPixmap("gui/ressources/close.png").scaled(
                    40,
                    40,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        close_button.setFixedSize(40, 40)
        close_button.setCursor(Qt.CursorShape.PointingHandCursor)

        def close_dialog(event):
            self.close()

        close_button.mousePressEvent = close_dialog

        header_buttons_layout.addStretch()
        header_buttons_layout.addWidget(self.theme_button)
        header_buttons_layout.addWidget(close_button)

        # Logo (identique à homepage)
        logo_label = QLabel()
        logo_label.setPixmap(
            QPixmap("gui/ressources/PowDroid_Vertical.png").scaled(
                497,
                90,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_layout = QVBoxLayout()
        logo_layout.addWidget(logo_label, alignment=Qt.AlignmentFlag.AlignTop)
        logo_layout.setContentsMargins(0, 0, 0, 0)

        content_layout.addLayout(header_buttons_layout)
        content_layout.addLayout(logo_layout)

        # Header with the title of the window inside a square box (Not USED)
        self.title_label = QLabel(t("record.title", language=self.language))
        title_font = QFont(self.font_family, 24, QFont.Weight.DemiBold)
        self.title_label.setFont(title_font)
        if self.dark_theme == "dark":
            self.title_label.setStyleSheet("color: #D2D2D2;")
        else:
            self.title_label.setStyleSheet("color: #000000;")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_frame = QFrame()
        if self.dark_theme == "dark":
            self.title_frame.setStyleSheet(
                "background-color: #282828; border: 1px solid #3C3C3C; border-radius: 8px;"
            )
        else:
            self.title_frame.setStyleSheet(
                "background-color: #EEEEEE; border: 1px solid #D9D9D9; border-radius: 8px;"
            )
        self.title_frame.setFixedSize(499, 49)
        title_layout = QHBoxLayout()
        title_layout.addWidget(self.title_label)
        title_layout.setContentsMargins(0, 0, 0, 0)
        self.title_frame.setLayout(title_layout)

        # Duration label
        self.duration_label = QLabel("00:00:00")
        self.duration_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if self.dark_theme == "dark":
            self.duration_label.setStyleSheet("color: #FFFFFF; margin: 20px 0;")
        else:
            self.duration_label.setStyleSheet("color: #000000; margin: 20px 0;")

        # Stop button
        stop_button = QPushButton("STOP RECORDING")
        stop_button.setIcon(QIcon("gui/ressources/stop.png"))
        stop_button.setIconSize(QSize(60, 60))
        if self.dark_theme == "dark":
            stop_button.setStyleSheet(
                "QPushButton { color: #D2D2D2; background-color: #5374C9; border: 1px solid #3C3C3C; border-radius: 5px; text-align: center; padding: 0px; } QPushButton:hover { background-color: #3C3C3C; }"
            )
        else:
            stop_button.setStyleSheet(
                "QPushButton { color: #000000; background-color: #5374C9; border: 1px solid #D9D9D9; border-radius: 5px; text-align: center; padding: 0px; } QPushButton:hover { background-color: #E0E0E0; }"
            )
        stop_button.setCursor(Qt.CursorShape.PointingHandCursor)
        github_font = QFont(self.font_family, 24, QFont.Weight.DemiBold)
        stop_button.setFont(github_font)
        stop_button.setFixedSize(499, 100)
        
        # Connecter le bouton stop à la méthode d'arrêt
        stop_button.clicked.connect(self.stop_recording_and_close)

        # Bouton d'aide (identique à homepage)
        question_label = QLabel("?")
        question_label.setFont(QFont(self.font_family, 32, QFont.Weight.Bold))
        question_label.setToolTip("About PowDroid")
        if self.dark_theme == "dark":
            question_label.setStyleSheet("color: #FFFFFF;")
        else:
            question_label.setStyleSheet("color: #313131;")
        question_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        question_label.setCursor(Qt.CursorShape.PointingHandCursor)
        question_label.mousePressEvent = lambda _: self.show_about_page()

        content_layout.addWidget(self.title_frame, alignment=Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(self.duration_label, alignment=Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(stop_button, alignment=Qt.AlignmentFlag.AlignCenter)

        content_layout.addWidget(
            question_label,
            alignment=Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight,
        )

        self.main_frame.setLayout(content_layout)
        main_layout.addWidget(self.main_frame)
        self.setLayout(main_layout)

    def toggle_theme(self):
        """Toggle between dark and light theme and update the interface."""
        self.dark_theme = "light" if self.dark_theme == "dark" else "dark"

        self.setup_styles()

        # Mettre à jour l'icône de fermeture
        if self.dark_theme == "dark":
            close_icon_path = "gui/ressources/close_white.png"
        else:
            close_icon_path = "gui/ressources/close.png"

        header_layout = self.main_frame.layout().itemAt(0).layout()
        close_button = header_layout.itemAt(2).widget()

        if os.path.exists(close_icon_path):
            close_button.setPixmap(
                QPixmap(close_icon_path).scaled(
                    40,
                    40,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

        # Mettre à jour le titre
        content_layout = self.main_frame.layout()
        for i in range(content_layout.count()):
            widget = content_layout.itemAt(i).widget()
            if (
                isinstance(widget, QLabel)
                and hasattr(widget, "text")
                and "Recording" in widget.text()
            ):
                if self.dark_theme == "dark":
                    widget.setStyleSheet("color: #D2D2D2; margin: 20px 0;")
                else:
                    widget.setStyleSheet("color: #000000; margin: 20px 0;")
                break

        # Mettre à jour le frame principal
        for i in range(content_layout.count()):
            widget = content_layout.itemAt(i).widget()
            if isinstance(widget, QFrame) and widget.size().height() == 400:
                if self.dark_theme == "dark":
                    widget.setStyleSheet(
                        "background-color: #282828; border: 1px solid #3C3C3C; border-radius: 8px;"
                    )
                else:
                    widget.setStyleSheet(
                        "background-color: #EEEEEE; border: 1px solid #D9D9D9; border-radius: 8px;"
                    )
                break

        # Mettre à jour le bouton d'aide
        for i in range(content_layout.count()):
            widget = content_layout.itemAt(i).widget()
            if isinstance(widget, QLabel) and widget.text() == "?":
                if self.dark_theme == "dark":
                    widget.setStyleSheet("color: #FFFFFF;")
                else:
                    widget.setStyleSheet("color: #313131;")
                break

        # Mettre à jour le label de durée
        if hasattr(self, "duration_label"):
            if self.dark_theme == "dark":
                self.duration_label.setStyleSheet("color: #FFFFFF; margin: 20px 0;")
            else:
                self.duration_label.setStyleSheet("color: #000000; margin: 20px 0;")

        # Mettre à jour le titre et son frame
        if hasattr(self, "title_label"):
            if self.dark_theme == "dark":
                self.title_label.setStyleSheet("color: #D2D2D2;")
            else:
                self.title_label.setStyleSheet("color: #000000;")

        if hasattr(self, "title_frame"):
            if self.dark_theme == "dark":
                self.title_frame.setStyleSheet(
                    "background-color: #282828; border: 1px solid #3C3C3C; border-radius: 8px;"
                )
            else:
                self.title_frame.setStyleSheet(
                    "background-color: #EEEEEE; border: 1px solid #D9D9D9; border-radius: 8px;"
                )

    def setup_styles(self):
        """Configure CSS styles for the record dialog."""
        if self.dark_theme == "dark":
            self.setStyleSheet(
                """
                /* Main dialog style (transparent) */
                RecordDialog {
                    background-color: transparent;
                }
                
                /* Main frame style with rounded corners */
                QFrame {
                    border-radius: 5px;
                    background-color: #1D1D1D;
                }
                
                /* Progress bar styles */
                QProgressBar {
                    border: 1px solid #3C3C3C;
                    border-radius: 5px;
                    background-color: #282828;
                    text-align: center;
                    color: #D2D2D2;
                }
                
                QProgressBar::chunk {
                    background-color: #5374C9;
                    border-radius: 5px;
                }
                
                /* Text edit styles */
                QTextEdit {
                    border: 1px solid #3C3C3C;
                    border-radius: 5px;
                    background-color: #1A1A1A;
                    color: #D2D2D2;
                    padding: 10px;
                }
                
                /* Button styles */
                QPushButton {
                    background-color: #5374C9;
                    border: 1px solid #3C3C3C;
                    border-radius: 5px;
                    color: #D2D2D2;
                    padding: 8px 16px;
                }
                
                QPushButton:hover {
                    background-color: #4A66B8;
                }
                
                QPushButton:disabled {
                    background-color: #3C3C3C;
                    color: #888888;
                }
                """
            )
        else:
            self.setStyleSheet(
                """
                /* Main dialog style (transparent) */
                RecordDialog {
                    background-color: transparent;
                }
                
                /* Main frame style with rounded corners */
                QFrame {
                    border-radius: 5px;
                    background-color: white;
                }
                
                /* Progress bar styles */
                QProgressBar {
                    border: 1px solid #D9D9D9;
                    border-radius: 5px;
                    background-color: #F5F5F5;
                    text-align: center;
                    color: #000000;
                }
                
                QProgressBar::chunk {
                    background-color: #5374C9;
                    border-radius: 5px;
                }
                
                /* Text edit styles */
                QTextEdit {
                    border: 1px solid #D9D9D9;
                    border-radius: 5px;
                    background-color: white;
                    color: #000000;
                    padding: 10px;
                }
                
                /* Button styles */
                QPushButton {
                    background-color: #5374C9;
                    border: 1px solid #D9D9D9;
                    border-radius: 5px;
                    color: white;
                    padding: 8px 16px;
                }
                
                QPushButton:hover {
                    background-color: #4A66B8;
                }
                
                QPushButton:disabled {
                    background-color: #E0E0E0;
                    color: #888888;
                }
                """
            )
