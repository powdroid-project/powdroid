"""
Module for the "CheckConfig" GUI of PowDroid.
"""

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QWidget,
    QPushButton,
)
from PyQt6.QtCore import Qt, QSize, QRect, QUrl, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap, QIcon, QDesktopServices, QFontDatabase, QMovie
from typing import Optional
from core.utils.setup import *
from gui.i18n import t
import os


class CheckWorker(QThread):
    """Worker thread for performing configuration checks."""

    finished = pyqtSignal(str, object)  # check_name, CheckResult
    error = pyqtSignal(str, str)  # check_name, error_message

    def __init__(self, check_name, check_function):
        super().__init__()
        self.check_name = check_name
        self.check_function = check_function

    def run(self):
        try:
            result = self.check_function()
            self.finished.emit(self.check_name, result)
        except Exception as e:
            self.error.emit(self.check_name, str(e))


class CheckConfigDialog(QDialog):
    """
    "CheckConfig" dialog.
    """

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

    def item_to_check(self, text: str, success: Optional[bool]) -> QWidget:
        """Create a widget with a custom icon (checkmark or cross) and a text next to it."""
        widget = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(20, 0, 0, 0)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        icon_label = QLabel()
        if success is None:
            movie = QMovie("gui/ressources/loading.gif")
            movie.setScaledSize(QSize(41, 41))
            icon_label.setMovie(movie)
            movie.start()
            movie.setSpeed(100)
        elif success:
            icon_label.setPixmap(
                QPixmap("gui/ressources/check.png").scaled(
                    41,
                    41,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            icon_label.setPixmap(
                QPixmap("gui/ressources/remove.png").scaled(
                    41,
                    41,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

        text_label = QLabel(text)
        text_label.setFont(QFont(self.font_family, 24, QFont.Weight.DemiBold))
        if self.dark_theme == "dark":
            text_label.setStyleSheet("color: #FFFFFF; ")
        else:
            text_label.setStyleSheet("color: #101010;")

        layout.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(text_label, alignment=Qt.AlignmentFlag.AlignLeft)
        widget.setLayout(layout)
        return widget

    def __init__(
        self, parent: Optional[QWidget] = None, dark_theme="dark", language="en"
    ):
        """
        Initialize the About dialog.

        Args:
            parent: Parent widget (optional)
        """
        super().__init__(parent)
        self.dark_theme = dark_theme
        self.language = language
        self.setModal(True)
        self.setFixedSize(550, 573)

        self.checks_config = [
            (t("check_config.android_sdk", language=self.language), check_android_sdk),
            (
                t("check_config.python_version", language=self.language),
                check_python_version,
            ),
            (
                t("check_config.pandas_library", language=self.language),
                check_pandas_module,
            ),
            (t("check_config.gui_module", language=self.language), check_gui_modules),
            (t("check_config.go_runtime", language=self.language), check_go_runtime),
            (
                t("check_config.adb_server", language=self.language),
                initialize_adb_server,
            ),
        ]
        self.status_widgets = []
        self.current_check = 0
        self.current_worker = None
        self.has_failures = False  # Track if any check failed

        self.load_fonts()

        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.setup_ui()
        self.setup_styles()

    def setup_ui(self):
        """Configure the user interface."""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.main_frame = QFrame()

        content_layout = QVBoxLayout()
        content_layout.setSpacing(10)
        content_layout.setContentsMargins(20, 20, 20, 20)

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

        title_label = QLabel(t("check_config.title", language=self.language))
        title_font = QFont(self.font_family, 24, QFont.Weight.DemiBold)
        title_label.setFont(title_font)
        if self.dark_theme == "dark":
            title_label.setStyleSheet("color: #D2D2D2;")
        else:
            title_label.setStyleSheet("color: #000000;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_frame = QFrame()
        if self.dark_theme == "dark":
            title_frame.setStyleSheet(
                "background-color: #282828; border: 1px solid #3C3C3C; border-radius: 8px;"
            )
        else:
            title_frame.setStyleSheet(
                "background-color: #EEEEEE; border: 1px solid #D9D9D9; border-radius: 8px;"
            )
        title_frame.setFixedSize(499, 49)
        title_layout = QHBoxLayout()
        title_layout.addWidget(title_label)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_frame.setLayout(title_layout)

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
        logo_layout.addWidget(logo_label)
        logo_layout.setContentsMargins(0, 0, 0, 0)

        content_layout.addWidget(
            close_button,
            alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight,
        )
        content_layout.addLayout(logo_layout)
        content_layout.addWidget(title_frame, alignment=Qt.AlignmentFlag.AlignCenter)

        for check_name, _ in self.checks_config:
            status_text = f"{check_name}: {t('check_config.status.in_progress', language=self.language)}"
            widget = self.item_to_check(status_text, None)
            self.status_widgets.append(widget)
            content_layout.addWidget(widget)

        self.main_frame.setLayout(content_layout)

        main_layout.addWidget(self.main_frame)

        self.setLayout(main_layout)

        QTimer.singleShot(100, self.start_checks)

    def start_checks(self):
        """Start the configuration checks asynchronously."""
        self.current_check = 0
        self.perform_next_check()

    def perform_next_check(self):
        """Perform the next configuration check."""
        if self.current_check >= len(self.checks_config):
            # All checks completed
            if not self.has_failures:
                # Only close if all checks passed
                QTimer.singleShot(
                    500, lambda: self.accept()
                )  # Wait a bit then close with accepted status
            # If there are failures, keep the dialog open
            return

        check_name, check_function = self.checks_config[self.current_check]

        self.current_worker = CheckWorker(check_name, check_function)
        self.current_worker.finished.connect(self.on_check_finished)
        self.current_worker.error.connect(self.on_check_error)
        self.current_worker.start()

    def on_check_finished(self, check_name, check_result):
        """Handle completion of a check."""
        success = check_result.success
        status_text = f"{check_name}: {t('check_config.status.ok', language=self.language) if success else t('check_config.status.failed', language=self.language)}"
        self.update_check_widget(status_text, success)

        if not success:
            # Mark that we have failures
            self.has_failures = True

        # Continue to next check regardless of success/failure
        self.current_check += 1
        QTimer.singleShot(50, self.perform_next_check)

    def on_check_error(self, check_name, error_message):
        """Handle error in a check."""
        print(f"Error in {check_name}: {error_message}")
        status_text = f"{check_name}: ERROR"
        self.update_check_widget(status_text, False)

        # Mark that we have failures
        self.has_failures = True

        # Continue to next check even if there was an error
        self.current_check += 1
        QTimer.singleShot(50, self.perform_next_check)

    def update_check_widget(self, status_text, result):
        """Update the widget for the current check."""
        new_widget = self.item_to_check(status_text, result)
        old_widget = self.status_widgets[self.current_check]
        layout = self.main_frame.layout()

        for i in range(layout.count()):
            if layout.itemAt(i).widget() == old_widget:
                layout.removeWidget(old_widget)
                layout.insertWidget(i, new_widget)
                old_widget.deleteLater()
                self.status_widgets[self.current_check] = new_widget
                break

    def setup_styles(self):
        """Configure CSS styles for the main dialog."""
        if self.dark_theme == "dark":
            self.setStyleSheet(
                """
                AboutDialog {
                    background-color: transparent;
                }
                
                QFrame {
                    border-radius: 5px;
                    background-color: #1D1D1D ;
                }
            """
            )
        else:
            self.setStyleSheet(
                """
                AboutDialog {
                    background-color: transparent;
                }
                
                QFrame {
                    border-radius: 5px;
                    background-color: white;
                }

                """
            )
