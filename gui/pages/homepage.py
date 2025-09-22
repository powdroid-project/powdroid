"""
Module for the "Main" GUI of PowDroid.
"""

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
    pyqtSlot,
    QTimer,
)
from PyQt6.QtGui import QFont, QPixmap, QIcon, QFontDatabase
from typing import Optional
from gui.i18n import t
from gui.popup import *
from gui.popup.information_plug_phone import InformationPopup
from core.utils import adb_runner
import os

from gui.popup.about import AboutDialog
from gui.pages.record_page import RecordDialog
from gui.popup.information_plug_phone import InformationPopup


class CollapsibleBox(QFrame):
    def __init__(self, title="", parent=None, content_size=None):
        super(CollapsibleBox, self).__init__(parent)

        self.content_size = content_size

        self.setObjectName("collapsible_box")
        self.setFixedWidth(499)
        self.setFixedHeight(350)

        self.toggle_button = QToolButton(text=title, checkable=True, checked=False)
        self.toggle_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.toggle_button.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_button.setFixedSize(489, 40)
        self.toggle_button.clicked.connect(self.on_clicked)

        self.content_area = QScrollArea()
        self.content_area.setObjectName("collapsible_content_area")
        self.content_area.setFrameShape(QFrame.Shape.NoFrame)
        self.content_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.content_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.content_area.setWidgetResizable(True)

        self.toggle_button.setParent(self)
        self.toggle_button.move(5, 5)

        self.content_area.setParent(self)
        self.content_area.move(5, 50)
        self.content_area.resize(489, 0)

        self.content_widget = QWidget()
        self.content_widget.setObjectName("collapsible_content_widget")
        self.content_area.setWidget(self.content_widget)

    @pyqtSlot()
    def on_clicked(self):
        checked = self.toggle_button.isChecked()
        self.toggle_button.setArrowType(
            Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow
        )

        if checked:
            self.content_area.setVisible(True)
            self.content_area.resize(489, 280)
            self.content_area.setMinimumHeight(280)
            self.content_area.setMaximumHeight(280)
        else:
            self.content_area.resize(489, 0)
            self.content_area.setMinimumHeight(0)
            self.content_area.setMaximumHeight(0)
            self.content_area.setVisible(False)

    def setContentLayout(self, layout):
        if self.content_widget.layout():
            old_layout = self.content_widget.layout()
            while old_layout.count():
                child = old_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
            old_layout.deleteLater()

        self.content_widget.setLayout(layout)


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

        self.dragging = False
        self.drag_position = None

        self.load_fonts()

        # Initialisation du chemin absolu vers le dossier des ressources
        current_dir = os.path.dirname(os.path.abspath(__file__))
        base_dir = os.path.join(current_dir, "..", "..")
        self.ressources_dir = os.path.normpath(
            os.path.join(base_dir, "gui", "ressources")
        )

        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.setup_ui()
        self.setup_styles()

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

    def load_fonts(self):
        """Load custom fonts from the fonts folder."""
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
        header_buttons_layout.setSpacing(5)
        header_buttons_layout.setContentsMargins(0, 0, 0, 0)

        self.theme_button = QLabel(self)
        self.update_theme_button_icon()
        self.theme_button.setFixedSize(40, 40)
        self.theme_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_button.setToolTip("Toggle Dark/Light Theme")

        def toggle_theme(event):
            self.toggle_theme()

        self.theme_button.mousePressEvent = toggle_theme

        close_button = QLabel(self)
        if self.dark_theme == "dark":
            close_button.setPixmap(
                QPixmap(os.path.join(self.ressources_dir, "close_white.png")).scaled(
                    40,
                    40,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            close_button.setPixmap(
                QPixmap(os.path.join(self.ressources_dir, "close.png")).scaled(
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
            QPixmap(os.path.join(self.ressources_dir, "PowDroid_Vertical.png")).scaled(
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

        self.record_button = QPushButton(t("homepage.record_button"))
        self.record_button.setIcon(
            QIcon(os.path.join(self.ressources_dir, "record.png"))
        )
        self.record_button.setIconSize(QSize(60, 60))
        self.update_record_button_style()
        self.record_button.setCursor(Qt.CursorShape.PointingHandCursor)
        github_font = QFont(self.font_family, 24, QFont.Weight.DemiBold)
        self.record_button.setFont(github_font)
        self.record_button.setFixedSize(499, 100)
        self.record_button.clicked.connect(self.show_record_page)

        instructions_group = CollapsibleBox("Instructions", content_size=(499, 216))
        instructions_group.toggle_button.setFont(
            QFont(self.font_family, 24, QFont.Weight.DemiBold)
        )

        instructions_content_layout = QVBoxLayout()
        instructions_label = QLabel(t("homepage.instructions.content"))
        instructions_label.setFont(QFont(self.font_family, 20, QFont.Weight.Normal))
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
        content_layout.addWidget(self.record_button)
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

    def update_theme_button_icon(self):
        """Update the theme button icon based on the current theme."""
        if self.dark_theme == "dark":
            # In dark theme, show light theme icon (suggesting switch to light)
            icon_path = os.path.join(
                self.ressources_dir, "light.png"
            )  # You can replace with a specific light theme icon
        else:
            # In light theme, show dark theme icon (suggesting switch to dark)
            icon_path = os.path.join(
                self.ressources_dir, "dark.png"
            )  # You can replace with a specific dark theme icon

        if os.path.exists(icon_path):
            self.theme_button.setPixmap(
                QPixmap(icon_path).scaled(
                    40,
                    40,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

    def toggle_theme(self):
        """Toggle between dark and light theme and update the interface."""
        self.dark_theme = "light" if self.dark_theme == "dark" else "dark"

        self.setup_styles()
        self.update_theme_button_icon()  # Update theme button icon

        if self.dark_theme == "dark":
            close_icon_path = os.path.join(self.ressources_dir, "close_white.png")
        else:
            close_icon_path = os.path.join(self.ressources_dir, "close.png")

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

    def update_record_button_style(self):
        """Update the record button style based on theme and enabled state."""
        if not hasattr(self, "record_button"):
            return

        if self.record_button.isEnabled():
            # Button enabled style
            if self.dark_theme == "dark":
                self.record_button.setStyleSheet(
                    "QPushButton { color: #D2D2D2; background-color: #5374C9; border: 1px solid #3C3C3C; border-radius: 5px; text-align: center; padding: 0px; } QPushButton:hover { background-color: #4A66B8; }"
                )
            else:
                self.record_button.setStyleSheet(
                    "QPushButton { color: #FFFFFF; background-color: #5374C9; border: 1px solid #D9D9D9; border-radius: 5px; text-align: center; padding: 0px; } QPushButton:hover { background-color: #4A66B8; }"
                )
            self.record_button.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            # Button disabled style
            if self.dark_theme == "dark":
                self.record_button.setStyleSheet(
                    "QPushButton { color: #888888; background-color: #3C3C3C; border: 1px solid #3C3C3C; border-radius: 5px; text-align: center; padding: 0px; }"
                )
            else:
                self.record_button.setStyleSheet(
                    "QPushButton { color: #888888; background-color: #E0E0E0; border: 1px solid #D9D9D9; border-radius: 5px; text-align: center; padding: 0px; }"
                )
            self.record_button.setCursor(Qt.CursorShape.ForbiddenCursor)

    def check_device_status(self):
        """Periodically check device connection status and update UI if necessary."""
        try:
            current_status = adb_runner.is_device_connected()
        except Exception as e:
            print(f"[PowDroid] Error while checking device status: {e}")
            current_status = False

        if current_status != self.previous_device_status:
            self.update_phone_status(current_status)
            self.previous_device_status = current_status

    def update_phone_status(self, phone_detected: bool):
        """Update the display based on phone detection.

        Args:
            phone_detected: True if a phone is detected, False otherwise
        """
        if phone_detected:
            phone_icon_path = os.path.join(self.ressources_dir, "phone_plugged.png")
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
            phone_icon_path = os.path.join(self.ressources_dir, "plug_the_phone.png")
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

        # Enable or disable the record button based on device connection
        if hasattr(self, "record_button"):
            self.record_button.setEnabled(phone_detected)
            self.update_record_button_style()

    def show_record_page(self):
        """Show the recording page."""
        # Check if device is connected before proceeding
        if not adb_runner.is_device_connected():
            print("[PowDroid] Cannot start recording: No device connected")
            return

        adb_runner.kill_all()

        # Clear battery stats while device is still connected
        adb_runner.clear_batterystats(verbose=True)

        self.popup = InformationPopup(
            parent=self,
            plugged=True,
            dark_theme=self.dark_theme,
            language=self.language,
        )
        self.popup.device_disconnected.connect(self.on_device_disconnected)
        self.popup.exec()

    def on_device_disconnected(self):
        """Handle device disconnection - close popup and start recording."""
        # Close the information popup
        if hasattr(self, "popup") and self.popup:
            self.popup.accept()  # Close the popup

        # Start recording after a short delay to ensure popup is closed
        from PyQt6.QtCore import QTimer

        QTimer.singleShot(100, self.start_recording)

    def start_recording(self):
        """Start recording after device disconnection."""
        # Hide the homepage while recording
        self.hide()

        record_dialog = RecordDialog(
            self,
            dark_theme=self.dark_theme,
            language=self.language,
            auto_start=True,
        )
        record_dialog.recording_finished.connect(self.on_recording_finished)
        record_dialog.exec()

    def on_recording_finished(self):
        """Handle when recording is finished."""
        # Check if this homepage window is still the active one and should be shown
        # If battery report is handling homepage restoration, don't interfere
        try:
            if (
                hasattr(self, "should_restore_on_recording_finished")
                and not self.should_restore_on_recording_finished
            ):
                return

            # Show the homepage again after recording is finished
            self.show()
            # Ensure homepage stays on top
            self.raise_()
            self.activateWindow()
        except RuntimeError:
            # Homepage object may have been destroyed, ignore
            pass

    def bring_to_front(self):
        """Bring the homepage to the front of all windows."""
        self.show()
        self.raise_()
        self.activateWindow()

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
                
                /* CollapsibleBox specific styles */
                QFrame#collapsible_box {
                    background-color: transparent;
                    border: none;
                }
                
                /* CollapsibleBox styles */
                QToolButton {
                    border: none;
                    color: white;
                    text-align: left;
                    padding: 5px;
                    background-color: transparent;
                }
                
                QToolButton:hover {
                    background-color: #3D3D3D;
                }
                
                QScrollArea#collapsible_content_area {
                    border: none;
                    background-color: #1D1D1D;
                }
                
                QWidget#collapsible_content_widget {
                    background-color: #1D1D1D;
                }
                
                QLabel {
                    color: white;
                    background-color: #1D1D1D;
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
                
                /* CollapsibleBox specific styles */
                QFrame#collapsible_box {
                    background-color: transparent;
                    border: none;
                }
                
                /* CollapsibleBox styles */
                QToolButton {
                    border: none;
                    color: black;
                    text-align: left;
                    padding: 5px;
                    background-color: transparent;
                }
                
                QToolButton:hover {
                    background-color: #E0E0E0;
                }
                
                QScrollArea#collapsible_content_area {
                    border: none;
                    background-color: white;
                }
                
                QWidget#collapsible_content_widget {
                    background-color: white;
                }
                
                QLabel {
                    color: black;
                    background-color: white;
                }
                """
            )
