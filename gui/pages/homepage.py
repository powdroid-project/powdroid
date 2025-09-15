"""
Module for the "Main" GUI of PowDroid.
"""

import os
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QWidget,
    QPushButton,
    QToolButton,
    QScrollArea,
    QSizePolicy,
)
from PyQt6.QtCore import (
    Qt,
    QSize,
    QRect,
    QUrl,
    pyqtSlot,
    QTimer,
)
from PyQt6.QtGui import QFont, QPixmap, QIcon, QDesktopServices, QFontDatabase
from typing import Optional
from gui.i18n import t
from gui.popup import *
from gui.popup.information_plug_phone import InformationPopup
from core.utils import adb_runner
import os

from gui.popup.about import AboutDialog
from gui.pages.record_page import RecordDialog
from gui.popup.information_plug_phone import InformationPopup


class CollapsibleBox(QWidget):
    def __init__(self, title="", parent=None, content_size=None):
        super(CollapsibleBox, self).__init__(parent)
        
        self.content_size = content_size  # Store the desired content size

        self.toggle_button = QToolButton(text=title, checkable=True, checked=False)
        self.toggle_button.setStyleSheet("QToolButton { border: none; }")
        self.toggle_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.toggle_button.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_button.setMinimumSize(QSize(499, 30))
        self.toggle_button.clicked.connect(self.on_clicked)
        

        self.content_area = QScrollArea(maximumHeight=0, minimumHeight=0)
        self.content_area.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.content_area.setFrameShape(QFrame.Shape.NoFrame)

        lay = QVBoxLayout(self)
        lay.setSpacing(0)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.toggle_button)
        lay.addWidget(self.content_area)

    @pyqtSlot()
    def on_clicked(self):
        checked = self.toggle_button.isChecked()
        self.toggle_button.setArrowType(
            Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow
        )
        # Toggle the content area visibility directly without animation
        if checked:
            # Show content with specific size if provided
            if self.content_size:
                self.content_area.setFixedSize(self.content_size[0], self.content_size[1])
                self.content_area.setMaximumHeight(self.content_size[1])
            else:
                self.content_area.setMaximumHeight(16777215)  # Large value to allow expansion
        else:
            # Hide content
            self.content_area.setMaximumHeight(0)
            self.content_area.setMinimumHeight(0)
            # Reset fixed size to allow proper hiding
            self.content_area.setFixedSize(0, 0)

    def setContentLayout(self, layout):
        lay = self.content_area.layout()
        del lay
        self.content_area.setLayout(layout)


class MainDialog(QDialog):
    """
    "Main" frame.
    """

    def __init__(
        self, parent: Optional[QWidget] = None, dark_theme="dark", language="en"
    ):
        """
        Initialize the Main frame.

        Args:
            parent: Parent widget (optional)
        """
        super().__init__(parent)
        self.dark_theme = dark_theme
        self.language = language
        self.setModal(True)
        self.setFixedSize(550, 900)

        self.previous_device_status = None
        
        # Variables pour le déplacement de la fenêtre
        self.dragging = False
        self.drag_position = None

        self.load_fonts()

        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.setup_ui()
        self.setup_styles()

    # Ajouter ces méthodes pour gérer le déplacement :
    def mousePressEvent(self, event):
        """Handle mouse press for window dragging."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
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
        """Configure the user interface."""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.main_frame = QFrame()

        content_layout = QVBoxLayout()
        content_layout.setSpacing(10)
        content_layout.setContentsMargins(20, 20, 20, 20)

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

        title_frame = QFrame()
        if self.dark_theme == "dark":
            title_frame.setStyleSheet(
                "background-color: #282828; border: 1px solid #3C3C3C; border-radius: 8px;"
            )
        else:
            title_frame.setStyleSheet(
                "background-color: #EEEEEE; border: 1px solid #D9D9D9; border-radius: 8px;"
            )
        title_frame.setFixedSize(499, 207)

        title_layout = QHBoxLayout()
        title_layout.setContentsMargins(15, 15, 15, 15)
        title_layout.setSpacing(15)

        self.phone_image = QLabel()
        self.phone_image.setFixedSize(184, 184)
        self.phone_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.phone_image.setStyleSheet("border: none;")

        self.status_label = QLabel()
        status_font = QFont(self.font_family, 16, QFont.Weight.Medium)
        self.status_label.setFont(status_font)
        self.status_label.setWordWrap(True)
        self.status_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        if self.dark_theme == "dark":
            self.status_label.setStyleSheet("color: #D2D2D2; border: none;")
        else:
            self.status_label.setStyleSheet("color: #000000; border: none;")

        self.phone_model_label = QLabel()
        model_font = QFont(self.font_family, 15, QFont.Weight.DemiBold)
        self.phone_model_label.setFont(model_font)
        self.phone_model_label.setWordWrap(True)
        self.phone_model_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        if self.dark_theme == "dark":
            self.phone_model_label.setStyleSheet("color: #D2D2D2; border: none;")
        else:
            self.phone_model_label.setStyleSheet("color: #000000; border: none;")
        self.phone_version_label = QLabel()
        version_font = QFont(self.font_family, 15, QFont.Weight.Normal)
        self.phone_version_label.setFont(version_font)
        self.phone_version_label.setWordWrap(True)
        self.phone_version_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        if self.dark_theme == "dark":
            self.phone_version_label.setStyleSheet("color: #D2D2D2; border: none;")
        else:
            self.phone_version_label.setStyleSheet("color: #000000; border: none;")

        title_layout.addWidget(self.phone_image)
        text_layout = QVBoxLayout()
        text_layout.setSpacing(5)
        text_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text_layout.addWidget(self.status_label)

        self.phone_model_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text_layout.addWidget(self.phone_model_label)

        self.phone_version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text_layout.addWidget(self.phone_version_label)

        title_layout.addLayout(text_layout, 1)

        title_frame.setLayout(title_layout)

        record_button = QPushButton(t("homepage.record_button"))
        record_button.setIcon(QIcon("gui/ressources/record.png"))
        record_button.setIconSize(QSize(60, 60))
        if self.dark_theme == "dark":
            record_button.setStyleSheet(
                "QPushButton { color: #D2D2D2; background-color: #5374C9; border: 1px solid #3C3C3C; border-radius: 5px; text-align: center; padding: 0px; } QPushButton:hover { background-color: #3C3C3C; }"
            )
        else:
            record_button.setStyleSheet(
                "QPushButton { color: #000000; background-color: #5374C9; border: 1px solid #D9D9D9; border-radius: 5px; text-align: center; padding: 0px; } QPushButton:hover { background-color: #E0E0E0; }"
            )
        record_button.setCursor(Qt.CursorShape.PointingHandCursor)
        github_font = QFont(self.font_family, 24, QFont.Weight.DemiBold)
        record_button.setFont(github_font)
        record_button.setFixedSize(499, 100)
        record_button.clicked.connect(self.show_record_page)

        instructions_group = CollapsibleBox("Instructions", content_size=(499, 216))
        instructions_group.toggle_button.setFont(QFont(self.font_family, 24, QFont.Weight.DemiBold))

        instructions_content_layout = QVBoxLayout()
        instructions_label = QLabel(t("homepage.instructions.content"))
        instructions_label.setFont(QFont(self.font_family, 16, QFont.Weight.Normal))
        instructions_label.setWordWrap(True)

        instructions_content_layout.addWidget(instructions_label)
        instructions_group.setContentLayout(instructions_content_layout)

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

        content_layout.addWidget(title_frame)
        content_layout.addWidget(record_button)
        content_layout.addWidget(instructions_group)
        content_layout.addWidget(
            question_label,
            alignment=Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight,
        )

        self.update_phone_status(adb_runner.is_device_connected())

        self.device_check_timer = QTimer()
        self.device_check_timer.timeout.connect(self.check_device_status)
        self.device_check_timer.start(2000)

        self.main_frame.setLayout(content_layout)
        main_layout.addWidget(self.main_frame)
        self.setLayout(main_layout)

    def toggle_theme(self):
        """Toggle between dark and light theme and update the interface."""
        self.dark_theme = "light" if self.dark_theme == "dark" else "dark"

        self.setup_styles()

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

        title_frame = None
        content_layout = self.main_frame.layout()
        for i in range(content_layout.count()):
            widget = content_layout.itemAt(i).widget()
            if isinstance(widget, QFrame) and widget.size() == QSize(499, 207):
                title_frame = widget
                break

        if title_frame:
            if self.dark_theme == "dark":
                title_frame.setStyleSheet(
                    "background-color: #282828; border: 1px solid #3C3C3C; border-radius: 8px;"
                )
            else:
                title_frame.setStyleSheet(
                    "background-color: #EEEEEE; border: 1px solid #D9D9D9; border-radius: 8px;"
                )

        if hasattr(self, "status_label"):
            if self.dark_theme == "dark":
                self.status_label.setStyleSheet("color: #D2D2D2; border: none;")
            else:
                self.status_label.setStyleSheet("color: #000000; border: none;")

        if hasattr(self, "phone_model_label"):
            if self.dark_theme == "dark":
                self.phone_model_label.setStyleSheet("color: #D2D2D2; border: none;")
            else:
                self.phone_model_label.setStyleSheet("color: #000000; border: none;")

        if hasattr(self, "phone_version_label"):
            if self.dark_theme == "dark":
                self.phone_version_label.setStyleSheet("color: #D2D2D2; border: none;")
            else:
                self.phone_version_label.setStyleSheet("color: #000000; border: none;")

        content_layout = self.main_frame.layout()
        for i in range(content_layout.count()):
            widget = content_layout.itemAt(i).widget()
            if isinstance(widget, QLabel) and widget.text() == "?":
                if self.dark_theme == "dark":
                    widget.setStyleSheet("color: #FFFFFF;")
                else:
                    widget.setStyleSheet("color: #313131;")
                break

        if (
            hasattr(self, "previous_device_status")
            and self.previous_device_status is not None
        ):
            self.update_phone_status(self.previous_device_status)

    def check_device_status(self):
        """Check periodically for device connection status and update UI if necessary."""
        current_status = adb_runner.is_device_connected()

        if current_status != self.previous_device_status:
            self.update_phone_status(current_status)
            self.previous_device_status = current_status

    def update_phone_status(self, phone_detected: bool):
        """Update the display based on phone detection.

        Args:
            phone_detected: True if a phone is detected, False otherwise
        """
        if phone_detected:
            if self.dark_theme == "dark":
                phone_icon_path = "gui/ressources/phone_plugged.png"
            else:
                phone_icon_path = "gui/ressources/phone_plugged.png"

            status_text = t("homepage.phone_status.connected")

            device_info = adb_runner.get_device_info()
            if device_info:
                manufacturer = device_info.get("manufacturer", "Unknown")
                model = device_info.get("model", "Unknown")
                android_version = device_info.get("android_version", "Unknown")

                self.phone_model_label.setText(f"{manufacturer} {model}")
                self.phone_version_label.setText(f"Android {android_version}")
            else:
                self.phone_model_label.setText("")
                self.phone_version_label.setText("")

        else:
            if self.dark_theme == "dark":
                phone_icon_path = "gui/ressources/plug_the_phone.png"
            else:
                phone_icon_path = "gui/ressources/plug_the_phone.png"

            status_text = t("homepage.phone_status.disconnected")

            self.phone_model_label.setText("")
            self.phone_version_label.setText("")

        if os.path.exists(phone_icon_path):
            pixmap = QPixmap(phone_icon_path).scaled(
                184,
                184,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.phone_image.setPixmap(pixmap)
        else:
            self.phone_image.setText("📱" if phone_detected else "❌")
            self.phone_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_font = QFont(self.font_family, 48)
            self.phone_image.setFont(icon_font)

        self.status_label.setText(status_text)

    def show_record_page(self):
        """Show the recording page."""
        # D'abord afficher la popup pour débrancher l'appareil
        popup = InformationPopup(
            parent=self,
            plugged=True,
            dark_theme=self.dark_theme,
            language=self.language
        )
        popup.device_disconnected.connect(self.start_recording)
        popup.exec()

    def start_recording(self):
        """Démarre l'enregistrement après déconnexion de l'appareil."""
        # Maintenant ouvrir la page d'enregistrement avec le timer démarré
        record_dialog = RecordDialog(
            self, 
            dark_theme=self.dark_theme, 
            language=self.language,
            auto_start=True  # Démarre automatiquement le timer
        )
        record_dialog.recording_finished.connect(self.on_recording_finished)
        record_dialog.exec()

    def on_recording_finished(self):
        """Handle when recording is finished."""
        # Actions à effectuer après l'enregistrement
        pass

    def setup_styles(self):
        """Configure CSS styles for the main dialog."""
        if self.dark_theme == "dark":
            self.setStyleSheet(
                """
                /* Main dialog style (transparent) */
                AboutDialog {
                    background-color: transparent;
                }
                
                /* Main frame style with rounded corners */
                QFrame {
                    border-radius: 5px;
                    background-color: #1D1D1D ;
                }
                
                /* CollapsibleBox styles */
                QToolButton {
                    border: none;
                    color: white;
                    text-align: left;
                    padding: 5px;
                }
                
                QScrollArea {
                    border: none;
                    background-color: transparent;
                }
            """
            )
        else:
            self.setStyleSheet(
                """
                /* Main dialog style (transparent) */
                AboutDialog {
                    background-color: transparent;
                }
                
                /* Main frame style with rounded corners */
                QFrame {
                    border-radius: 5px;
                    background-color: white;
                }
                
                /* CollapsibleBox styles */
                QToolButton {
                    border: none;
                    color: black;
                    text-align: left;
                    padding: 5px;
                }
                
                QScrollArea {
                    border: none;
                    background-color: transparent;
                }
                """
            )
