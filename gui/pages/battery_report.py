"""
Module for the Battery Report page of PowDroid.
Displays battery usage statistics and graphs based on CSV data.
"""

import os
import pandas as pd
import subprocess
import platform
from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QWidget,
    QSizePolicy,
    QMessageBox,
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont, QPixmap, QFontDatabase
from typing import Optional
import matplotlib

matplotlib.use("Qt5Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.dates as mdates


class BatteryReportCanvas(FigureCanvas):
    """Custom matplotlib canvas for cumulative energy graph"""

    def __init__(self, parent=None, width=12, height=6, dpi=100):
        self.figure = Figure(figsize=(width, height), dpi=dpi)
        super(BatteryReportCanvas, self).__init__(self.figure)
        self.setParent(parent)

        FigureCanvas.setSizePolicy(
            self, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        FigureCanvas.updateGeometry(self)

        plt.style.use("dark_background")
        self.figure.patch.set_facecolor("#2b2b2b")

    def plot_battery_data(self, csv_file_path):
        """Plot cumulative energy data from CSV file"""
        try:
            df = pd.read_csv(csv_file_path)

            df["start_datetime"] = pd.to_datetime(df["start_time"], unit="ms")

            df["Cumulative_Energy"] = df["Energy (J)"].cumsum()

            self.figure.clear()

            ax = self.figure.add_subplot(111)

            ax.plot(
                df["start_datetime"],
                df["Cumulative_Energy"],
                color="#5374C9",
                linewidth=2,
                marker="o",
                markersize=1,
            )

            ax.set_title(
                "Cumulative Energy Consumption", fontsize=16, color="white", pad=20
            )
            ax.set_xlabel("Time", fontsize=12, color="white")
            ax.set_ylabel("Cumulative Energy (J)", fontsize=12, color="white")
            ax.grid(True, alpha=0.3, color="white")
            ax.tick_params(colors="white")

            ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
            ax.tick_params(axis="x", rotation=45)

            ax.set_facecolor("#2b2b2b")

            self.figure.tight_layout()

            self.draw()

        except Exception as e:
            print(f"Error plotting battery data: {e}")
            self.figure.clear()
            ax = self.figure.add_subplot(111)
            ax.text(
                0.5,
                0.5,
                f"Error loading data:\n{str(e)}",
                transform=ax.transAxes,
                ha="center",
                va="center",
                fontsize=14,
                color="red",
            )
            ax.set_facecolor("#2b2b2b")
            self.draw()


class BatteryReportDialog(QDialog):
    """
    Battery Report page for PowDroid - Cumulative Energy View
    """

    def __init__(
        self,
        csv_file_path=None,
        parent: Optional[QWidget] = None,
        dark_theme="dark",
        language="en",
    ):
        """
        Initialize the Battery Report frame.

        Args:
            csv_file_path: Path to the CSV file to display
            parent: Parent widget (optional)
            dark_theme: Theme mode ("dark" or "light")
            language: Language code
        """
        super().__init__(parent)
        self.csv_file_path = csv_file_path
        self.dark_theme = dark_theme
        self.language = language
        self.setModal(True)
        self.setFixedSize(550, 900)

        self.dragging = False
        self.drag_position = None

        self.load_fonts()

        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.setup_ui()
        self.setup_styles()

        if csv_file_path and os.path.exists(csv_file_path):
            self.load_report_data(csv_file_path)

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
        """Show the about dialog."""
        from gui.popup.about import AboutDialog

        dialog = AboutDialog(self, dark_theme=self.dark_theme, language=self.language)
        dialog.exec()

    def open_file_location(self):
        """Open the directory containing the CSV file in the system file manager."""
        if not self.csv_file_path or not os.path.exists(self.csv_file_path):
            QMessageBox.warning(self, "Error", "No valid CSV file found.")
            return

        try:
            file_path = os.path.abspath(self.csv_file_path)
            directory = os.path.dirname(file_path)

            system = platform.system()
            if system == "Darwin":
                subprocess.run(["open", directory])
            elif system == "Windows":
                subprocess.run(["explorer", directory])
            elif system == "Linux":
                subprocess.run(["xdg-open", directory])
            else:
                QMessageBox.information(
                    self,
                    "Information",
                    f"Cannot open directory automatically.\n" f"Path: {directory}",
                )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Cannot open directory: {str(e)}")

    def update_file_path_label(self):
        """Update the file path label with the current CSV file path."""
        if hasattr(self, "file_path_label") and self.csv_file_path:
            file_path = Path(self.csv_file_path)
            parent_dir = file_path.parent.name
            file_name = file_path.name

            if parent_dir:
                display_text = f"📁 {parent_dir}/{file_name}"
            else:
                display_text = f"📁 {file_name}"

            self.file_path_label.setText(display_text)
            self.file_path_label.show()
        elif hasattr(self, "file_path_label"):
            self.file_path_label.hide()

    def update_theme_button_icon(self):
        """Update the theme button icon based on the current theme."""
        if self.dark_theme == "dark":
            icon_path = "gui/ressources/light.png"
        else:
            icon_path = "gui/ressources/dark.png"

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
        self.update_theme_button_icon()

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

        content_layout = self.main_frame.layout()
        for i in range(content_layout.count()):
            widget = content_layout.itemAt(i).widget()
            if isinstance(widget, QFrame) and widget.size() == QSize(499, 400):
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

        if hasattr(self, "file_path_label"):
            if self.dark_theme == "dark":
                self.file_path_label.setStyleSheet(
                    """
                    QLabel {
                        color: #A0A0A0;
                        background-color: #2b2b2b;
                        border: 1px solid #3C3C3C;
                        border-radius: 4px;
                        padding: 5px;
                    }
                    QLabel:hover {
                        color: #FFFFFF;
                        background-color: #3C3C3C;
                        border: 1px solid #4C4C4C;
                    }
                """
                )
            else:
                self.file_path_label.setStyleSheet(
                    """
                    QLabel {
                        color: #666666;
                        background-color: #F5F5F5;
                        border: 1px solid #D9D9D9;
                        border-radius: 4px;
                        padding: 5px;
                    }
                    QLabel:hover {
                        color: #333333;
                        background-color: #E8E8E8;
                        border: 1px solid #CCCCCC;
                    }
                """
                )

        if hasattr(self, "canvas"):
            self.canvas.figure.patch.set_facecolor("#2b2b2b")
            self.canvas.draw()

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

        content_layout.addLayout(header_buttons_layout)

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

        content_layout.addLayout(logo_layout)

        self.title_label = QLabel("Battery Usage Report")
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

        content_layout.addWidget(
            self.title_frame, alignment=Qt.AlignmentFlag.AlignCenter
        )

        chart_frame = QFrame()
        if self.dark_theme == "dark":
            chart_frame.setStyleSheet(
                "background-color: #282828; border: 1px solid #3C3C3C; border-radius: 8px;"
            )
        else:
            chart_frame.setStyleSheet(
                "background-color: #EEEEEE; border: 1px solid #D9D9D9; border-radius: 8px;"
            )
        chart_frame.setFixedSize(499, 400)

        chart_layout = QVBoxLayout(chart_frame)
        chart_layout.setContentsMargins(15, 15, 15, 15)

        self.canvas = BatteryReportCanvas(chart_frame, width=8, height=4, dpi=80)
        chart_layout.addWidget(self.canvas)

        content_layout.addWidget(chart_frame)

        self.file_path_label = QLabel()
        self.file_path_label.setFont(QFont(self.font_family, 10))
        self.file_path_label.setWordWrap(True)
        self.file_path_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.file_path_label.setToolTip(
            "Click to open the directory containing the file"
        )
        self.file_path_label.mousePressEvent = lambda _: self.open_file_location()
        self.file_path_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.file_path_label.setMaximumWidth(480)

        if self.dark_theme == "dark":
            self.file_path_label.setStyleSheet(
                """
                QLabel {
                    color: #A0A0A0;
                    background-color: #2b2b2b;
                    border: 1px solid #3C3C3C;
                    border-radius: 4px;
                    padding: 5px;
                }
                QLabel:hover {
                    color: #FFFFFF;
                    background-color: #3C3C3C;
                    border: 1px solid #4C4C4C;
                }
            """
            )
        else:
            self.file_path_label.setStyleSheet(
                """
                QLabel {
                    color: #666666;
                    background-color: #F5F5F5;
                    border: 1px solid #D9D9D9;
                    border-radius: 4px;
                    padding: 5px;
                }
                QLabel:hover {
                    color: #333333;
                    background-color: #E8E8E8;
                    border: 1px solid #CCCCCC;
                }
            """
            )

        if not self.csv_file_path:
            self.file_path_label.hide()
        else:
            self.update_file_path_label()

        content_layout.addWidget(
            self.file_path_label, alignment=Qt.AlignmentFlag.AlignCenter
        )

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
            question_label,
            alignment=Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight,
        )

        self.main_frame.setLayout(content_layout)
        main_layout.addWidget(self.main_frame)
        self.setLayout(main_layout)

    def setup_styles(self):
        """Configure CSS styles for the battery report dialog."""
        if self.dark_theme == "dark":
            self.setStyleSheet(
                """
                BatteryReportDialog {
                    background-color: transparent;
                }
                
                QFrame {
                    border-radius: 5px;
                    background-color: #1D1D1D;
                    opacity: 0.7;
                }
                """
            )
        else:
            self.setStyleSheet(
                """
                BatteryReportDialog {
                    background-color: transparent;
                }
                
                QFrame {
                    border-radius: 5px;
                    background-color: white;
                    opacity: 0.7;
                }
                """
            )

    def set_background_mode(self, is_background=True):
        """Set the dialog to background mode (non-interactive) or foreground mode."""
        if is_background:
            self.setWindowFlags(
                Qt.WindowType.Window
                | Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnBottomHint
            )
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
            self.setEnabled(False)
            self.setWindowOpacity(0.8)
        else:
            self.setWindowFlags(
                Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
            )
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
            self.setEnabled(True)
            self.setWindowOpacity(1.0)

    def closeEvent(self, event):
        """Handle close event to restore homepage."""
        if hasattr(self, "homepage_to_restore") and self.homepage_to_restore:
            from PyQt6.QtCore import QTimer

            def restore_homepage():
                self.homepage_to_restore.show()
                self.homepage_to_restore.raise_()
                self.homepage_to_restore.activateWindow()
                self.homepage_to_restore.should_restore_on_recording_finished = True

            QTimer.singleShot(100, restore_homepage)

        event.accept()

    def load_report_data(self, csv_file_path):
        """Load and display battery report data"""
        if not os.path.exists(csv_file_path):
            QMessageBox.warning(self, "Error", f"CSV file not found: {csv_file_path}")
            return

        try:
            # Plot cumulative energy graph
            self.canvas.plot_battery_data(csv_file_path)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load report data: {str(e)}")

    def set_csv_file(self, csv_file_path):
        """Set the CSV file path and load data"""
        self.csv_file_path = csv_file_path
        self.update_file_path_label()
        self.load_report_data(csv_file_path)


def find_latest_csv_file():
    current_dir = Path.cwd()
    csv_files = list(current_dir.glob("PowDroid_*.csv"))

    if not csv_files:
        return None

    latest_file = max(csv_files, key=os.path.getctime)
    return str(latest_file)
