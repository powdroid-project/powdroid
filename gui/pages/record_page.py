"""
Module for the Record page GUI of PowDroid.
"""

from datetime import datetime
import os
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
    QFrame,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QSize, QThread
from PyQt6.QtGui import QFont, QPixmap, QIcon, QFontDatabase, QMovie
from typing import Optional
from gui.i18n import t
from gui.popup.about import AboutDialog
from gui.pages.battery_report import BatteryReportDialog
from core.utils import adb_runner, csv_handler


class DataProcessingWorker(QThread):
    """Worker thread for processing recording data."""

    finished = pyqtSignal()
    error = pyqtSignal(str)
    csv_generated = pyqtSignal(str)  # Signal to emit CSV file path

    def __init__(self, start_time, stop_time):
        super().__init__()
        self.start_time = start_time
        self.stop_time = stop_time

    def run(self):
        """Process the recording data in a separate thread."""
        try:

            # Dump battery stats
            adb_runner.dump_batterystats(True)

            # Convert battery stats to CSV
            file_name = adb_runner.conversion_batterystats()

            # Generate individual CSV files from the main CSV
            csv_handler.generate_files(file_name)

            # Process CSV file
            def to_timestamp_ms(dt):
                return int(dt.timestamp() * 1000) if isinstance(dt, datetime) else dt

            start_ts = to_timestamp_ms(self.start_time)
            stop_ts = to_timestamp_ms(self.stop_time)

            csv_file_path = csv_handler.process_csv_file(start_ts, stop_ts)

            print("[PowDroid] Data processing completed")
            if csv_file_path:
                self.csv_generated.emit(csv_file_path)
            self.finished.emit()

        except Exception as e:
            print(f"[PowDroid] Error during data processing: {str(e)}")
            self.error.emit(str(e))


class RecordDialog(QDialog):
    """
    Record page for PowDroid.
    """

    recording_finished = pyqtSignal()

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        dark_theme="dark",
        language="en",
        auto_start=False,
    ):
        super().__init__(parent)
        self.dark_theme = dark_theme
        self.language = language
        self.auto_start = auto_start
        self.setModal(True)
        self.setFixedSize(550, 900)

        # Initialisation du chemin absolu vers le dossier des ressources
        current_dir = os.path.dirname(os.path.abspath(__file__))
        base_dir = os.path.join(current_dir, "..", "..")
        self.ressources_dir = os.path.normpath(
            os.path.join(base_dir, "gui", "ressources")
        )

        self.dragging = False
        self.drag_position = None

        self.recording_timer = QTimer()
        self.recording_timer.timeout.connect(self.update_duration)
        self.recording_seconds = 0
        self.is_recording = False
        self.t_start_time = None
        self.t_stop_time = None

        self.load_fonts()

        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.setup_ui()
        self.setup_styles()

        if self.auto_start:
            self.start_recording_timer()

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
        """Start the recording timer."""
        if not self.is_recording:
            self.is_recording = True
            self.t_start_time = datetime.now()
            self.recording_timer.start(1000)

    def stop_recording_timer(self):
        """Stop the recording timer."""
        if self.is_recording:
            self.is_recording = False
            self.t_stop_time = datetime.now()
            self.recording_timer.stop()

    def update_duration(self):
        """Update the recording duration display."""
        self.recording_seconds += 1
        if hasattr(self, "duration_label"):
            self.duration_label.setText(self.format_duration(self.recording_seconds))

    def format_duration(self, seconds):
        """Format duration in HH:MM:SS."""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def stop_recording_and_close(self):
        """Stop recording and ask to reconnect the phone."""
        self.stop_recording_timer()

        self._device_reconnected = False

        from gui.popup.information_plug_phone import InformationPopup

        self.popup = InformationPopup(
            parent=self,
            plugged=False,
            dark_theme=self.dark_theme,
            language=self.language,
        )
        self.popup.setModal(True)
        self.popup.device_connected.connect(self.on_device_reconnected)

        result = self.popup.exec()

        if not self._device_reconnected:
            self._process_recording_data()

    def on_device_reconnected(self):
        """Called when device is reconnected - close popup and process data."""
        self._device_reconnected = True

        from PyQt6.QtCore import QTimer

        QTimer.singleShot(0, self._close_popup_and_process)

    def _close_popup_and_process(self):
        """Close popup and process data in main thread."""
        if hasattr(self, "popup") and self.popup:
            self.popup.accept()

        self._process_recording_data()

    def _process_recording_data(self):
        """Process recording data after popup closure."""
        if self.t_start_time is None or self.t_stop_time is None:
            if self.t_start_time is None:
                self.t_start_time = datetime.now()
            if self.t_stop_time is None:
                self.t_stop_time = datetime.now()

        self._update_ui_for_data_collection()

        from PyQt6.QtCore import QCoreApplication

        QCoreApplication.processEvents()

        self.worker = DataProcessingWorker(self.t_start_time, self.t_stop_time)
        self.worker.finished.connect(self._on_data_processing_finished)
        self.worker.error.connect(self._on_data_processing_error)
        self.worker.csv_generated.connect(self._on_csv_generated)
        self.worker.start()

    def _on_data_processing_finished(self):
        """Called when data processing is finished."""
        if hasattr(self, "loading_label"):
            self.loading_label.hide()

        if hasattr(self, "loading_movie") and self.loading_movie:
            self.loading_movie.stop()

        # If no CSV was generated, show error message
        if not hasattr(self, "csv_generated") or not self.worker or not hasattr(self.worker, "csv_generated"):
            self._show_error_message("No data found. Please check your timestamps or battery stats.")

        self.recording_finished.emit()

        self.worker.deleteLater()
        self.worker = None

    def _show_error_message(self, message):
        """Display an error message in the UI when data collection fails."""
        error_label = QLabel(message)
        error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        error_label.setWordWrap(True)
        error_label.setFont(QFont(self.font_family, 18, QFont.Weight.Bold))
        if self.dark_theme == "dark":
            error_label.setStyleSheet("color: #FF5555; margin: 30px 0;")
        else:
            error_label.setStyleSheet("color: #B00020; margin: 30px 0;")
        content_layout = self.main_frame.layout()
        content_layout.addWidget(error_label, alignment=Qt.AlignmentFlag.AlignCenter)
        self.update()
        self.repaint()

    def _on_data_processing_error(self, error_message):
        """Called when there's an error during data processing."""
        if hasattr(self, "loading_label"):
            self.loading_label.hide()

        if hasattr(self, "loading_movie") and self.loading_movie:
            self.loading_movie.stop()

        self._show_error_message(f"Data processing error: {error_message}")

        self.recording_finished.emit()

        if hasattr(self, "worker") and self.worker:
            self.worker.deleteLater()
            self.worker = None

    def _on_csv_generated(self, csv_file_path):
        """Called when CSV file is generated - opens battery report."""
        try:
            # Store reference to parent (homepage) to restore it later
            homepage_parent = self.parent()

            # Mark homepage to not restore itself automatically
            if homepage_parent:
                homepage_parent.should_restore_on_recording_finished = False

            # Import here to avoid circular imports
            from gui.pages.battery_report import BatteryReportDialog

            # Create and show battery report independently
            def show_battery_report():
                battery_report = BatteryReportDialog(
                    csv_file_path=csv_file_path,
                    parent=None,  # No parent since we're managing windows independently
                    dark_theme=self.dark_theme,
                    language=self.language,
                )

                # Store homepage reference to restore it later (don't create new one)
                battery_report.homepage_to_restore = homepage_parent

                # Set it to foreground mode (interactive, modal)
                battery_report.set_background_mode(False)

                # Show battery report modally
                battery_report.exec()

            # Close the record page first
            self.accept()

            # Use QTimer to show battery report after record page closes
            from PyQt6.QtCore import QTimer

            QTimer.singleShot(100, show_battery_report)

        except Exception as e:
            print(f"[PowDroid] Error opening battery report: {str(e)}")

    def _on_battery_report_closed(self, result):
        """Called when battery report is closed - clean up only since record page is already closed."""
        # The record page is already closed at this point since we call self.accept()
        # in _on_csv_generated, so this method just cleans up the battery report
        if hasattr(self, "battery_report"):
            self.battery_report.deleteLater()
            self.battery_report = None

    def _update_ui_for_data_collection(self):
        """Update UI to show data collection state."""
        if hasattr(self, "title_label"):
            self.title_label.setText("COLLECTING DATA")

        if hasattr(self, "stop_button"):
            self.stop_button.hide()

        if hasattr(self, "duration_label"):
            self.duration_label.hide()

        self._create_loading_spinner()

        content_layout = self.main_frame.layout()

        spinner_added = False
        for i in range(content_layout.count()):
            widget = content_layout.itemAt(i).widget()
            if widget == self.duration_label:
                content_layout.insertWidget(i + 1, self.loading_label)
                spinner_added = True
                break

        if not spinner_added:
            content_layout.addWidget(self.loading_label)

        self.update()
        self.repaint()

    def _create_loading_spinner(self):
        """Create loading spinner widget with message using the loading.gif resource."""
        self.loading_label = QWidget()
        loading_layout = QVBoxLayout()
        loading_layout.setSpacing(10)
        loading_layout.setContentsMargins(0, 0, 0, 0)

        spinner_label = QLabel()
        gif_path = os.path.join(self.ressources_dir, "loading.gif")
        if not os.path.exists(gif_path):
            spinner_label.setText("● ● ●")
            spinner_label.setStyleSheet("font-size: 24px; color: #5374C9;")
        else:
            self.loading_movie = QMovie(gif_path)

            if self.loading_movie.isValid():
                self.loading_movie.setScaledSize(QSize(190, 190))
                spinner_label.setMovie(self.loading_movie)
                self.loading_movie.start()
            else:
                spinner_label.setText("Loading...")
                spinner_label.setStyleSheet("font-size: 18px; color: #5374C9;")

        spinner_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        message_label = QLabel("Please wait. It may take a while.")
        message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        message_font = QFont(self.font_family, 32, QFont.Weight.DemiBold)
        message_font.setItalic(True)
        message_label.setFont(message_font)
        if self.dark_theme == "dark":
            message_label.setStyleSheet("color: #D2D2D2; margin: 10px 0;")
        else:
            message_label.setStyleSheet("color: #666666; margin: 10px 0;")

        # Add widgets to layout
        loading_layout.addWidget(spinner_label, alignment=Qt.AlignmentFlag.AlignCenter)
        loading_layout.addWidget(message_label, alignment=Qt.AlignmentFlag.AlignCenter)

        self.loading_label.setLayout(loading_layout)
        self.loading_label.show()

    def load_fonts(self):
        """Loads custom fonts from the fonts folder."""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        base_dir = os.path.join(current_dir, "..", "..")
        self.ressources_dir = os.path.normpath(
            os.path.join(base_dir, "gui", "ressources")
        )


        base_dir = os.path.join(current_dir, "..", "..")
        font_paths = [
            os.path.join(os.path.dirname(__file__), "fonts", "Inter.ttf"),
            os.path.join(os.path.dirname(__file__), "fonts", "Inter-Italic.ttf"),
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

        # Header buttons
        header_buttons_layout = QHBoxLayout()
        header_buttons_layout.setSpacing(10)
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
            close_img_path = os.path.join(self.ressources_dir, "close_white.png")
            close_button.setPixmap(
                QPixmap(close_img_path).scaled(
                    40,
                    40,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            close_img_path = os.path.join(self.ressources_dir, "close.png")
            close_button.setPixmap(
                QPixmap(close_img_path).scaled(
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

        # Logo
        logo_label = QLabel()
        logo_img_path = os.path.join(self.ressources_dir, "PowDroid_Vertical.png")
        logo_label.setPixmap(
            QPixmap(logo_img_path).scaled(
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

        # Header with title
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
        duration_font = QFont(self.font_family, 48, QFont.Weight.Bold)
        self.duration_label.setFont(duration_font)
        if self.dark_theme == "dark":
            self.duration_label.setStyleSheet("color: #FFFFFF; margin: 20px 0;")
        else:
            self.duration_label.setStyleSheet("color: #000000; margin: 20px 0;")

        # Stop button
        self.stop_button = QPushButton("STOP RECORDING")
        stop_icon_path = os.path.join(self.ressources_dir, "stop.png")
        self.stop_button.setIcon(QIcon(stop_icon_path))
        self.stop_button.setIconSize(QSize(60, 60))
        if self.dark_theme == "dark":
            self.stop_button.setStyleSheet(
                "QPushButton { color: #D2D2D2; background-color: #5374C9; border: 1px solid #3C3C3C; border-radius: 5px; text-align: center; padding: 0px; } QPushButton:hover { background-color: #3C3C3C; }"
            )
        else:
            self.stop_button.setStyleSheet(
                "QPushButton { color: #000000; background-color: #5374C9; border: 1px solid #D9D9D9; border-radius: 5px; text-align: center; padding: 0px; } QPushButton:hover { background-color: #E0E0E0; }"
            )
        self.stop_button.setCursor(Qt.CursorShape.PointingHandCursor)
        github_font = QFont(self.font_family, 24, QFont.Weight.DemiBold)
        self.stop_button.setFont(github_font)
        self.stop_button.setFixedSize(499, 100)

        self.stop_button.clicked.connect(self.stop_recording_and_close)

        # Help button
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

        content_layout.addWidget(
            self.title_frame, alignment=Qt.AlignmentFlag.AlignCenter
        )
        content_layout.addWidget(
            self.duration_label, alignment=Qt.AlignmentFlag.AlignCenter
        )
        content_layout.addWidget(
            self.stop_button, alignment=Qt.AlignmentFlag.AlignCenter
        )

        content_layout.addWidget(
            question_label,
            alignment=Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight,
        )

        self.main_frame.setLayout(content_layout)
        main_layout.addWidget(self.main_frame)
        self.setLayout(main_layout)

    def update_theme_button_icon(self):
        """Update the theme button icon based on the current theme."""
        if self.dark_theme == "dark":
            icon_path = os.path.join(self.ressources_dir, "light.png")
        else:
            icon_path = os.path.join(self.ressources_dir, "dark.png")
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

        for i in range(content_layout.count()):
            widget = content_layout.itemAt(i).widget()
            if isinstance(widget, QLabel) and widget.text() == "?":
                if self.dark_theme == "dark":
                    widget.setStyleSheet("color: #FFFFFF;")
                else:
                    widget.setStyleSheet("color: #313131;")
                break

        if hasattr(self, "duration_label"):
            if self.dark_theme == "dark":
                self.duration_label.setStyleSheet("color: #FFFFFF; margin: 20px 0;")
            else:
                self.duration_label.setStyleSheet("color: #000000; margin: 20px 0;")

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
