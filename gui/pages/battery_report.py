"""
Module for the Battery Report page of PowDroid.
Displays battery usage statistics and graphs based on CSV data.
"""

import os
import pandas as pd
from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QWidget,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QGridLayout,
    QMessageBox,
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont, QPixmap, QIcon, QFontDatabase
from typing import Optional
import matplotlib

matplotlib.use("Qt5Agg")  # Use Qt5Agg backend for PyQt6 compatibility
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.dates as mdates
from datetime import datetime
import numpy as np
from gui.i18n import t


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

        # Set dark theme for matplotlib
        plt.style.use("dark_background")
        self.figure.patch.set_facecolor("#2b2b2b")

    def plot_battery_data(self, csv_file_path):
        """Plot cumulative energy data from CSV file"""
        try:
            # Read CSV data
            df = pd.read_csv(csv_file_path)

            # Convert timestamps to datetime
            df["start_datetime"] = pd.to_datetime(df["start_time"], unit="ms")

            # Calculate cumulative energy
            df["Cumulative_Energy"] = df["Energy (J)"].cumsum()

            # Clear previous plots
            self.figure.clear()

            # Create single plot for cumulative energy
            ax = self.figure.add_subplot(111)

            # Plot cumulative energy
            ax.plot(
                df["start_datetime"],
                df["Cumulative_Energy"],
                color="#5374C9",
                linewidth=2,
                marker="o",
                markersize=1,
            )

            # Styling for dark theme
            ax.set_title(
                "Cumulative Energy Consumption", fontsize=16, color="white", pad=20
            )
            ax.set_xlabel("Time", fontsize=12, color="white")
            ax.set_ylabel("Cumulative Energy (J)", fontsize=12, color="white")
            ax.grid(True, alpha=0.3, color="white")
            ax.tick_params(colors="white")

            # Format x-axis
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
            ax.tick_params(axis="x", rotation=45)

            # Set background color
            ax.set_facecolor("#2b2b2b")

            # Adjust layout
            self.figure.tight_layout()

            # Refresh canvas
            self.draw()

        except Exception as e:
            print(f"Error plotting battery data: {e}")
            # Show error on canvas
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

    def toggle_theme(self):
        """Toggle between dark and light theme and update the interface."""
        self.dark_theme = "light" if self.dark_theme == "dark" else "dark"

        self.setup_styles()

        # Update close button icon
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

        # Update title label style
        if hasattr(self, "title_label"):
            if self.dark_theme == "dark":
                self.title_label.setStyleSheet("color: #D2D2D2;")
            else:
                self.title_label.setStyleSheet("color: #000000;")

        # Update title frame style
        if hasattr(self, "title_frame"):
            if self.dark_theme == "dark":
                self.title_frame.setStyleSheet(
                    "background-color: #282828; border: 1px solid #3C3C3C; border-radius: 8px;"
                )
            else:
                self.title_frame.setStyleSheet(
                    "background-color: #EEEEEE; border: 1px solid #D9D9D9; border-radius: 8px;"
                )

        # Update chart frame style
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

        # Update question mark style
        for i in range(content_layout.count()):
            widget = content_layout.itemAt(i).widget()
            if isinstance(widget, QLabel) and widget.text() == "?":
                if self.dark_theme == "dark":
                    widget.setStyleSheet("color: #FFFFFF;")
                else:
                    widget.setStyleSheet("color: #313131;")
                break

        # Update matplotlib canvas background
        if hasattr(self, "canvas"):
            self.canvas.figure.patch.set_facecolor(
                "#2b2b2b" if self.dark_theme == "dark" else "white"
            )
            self.canvas.draw()

    def setup_ui(self):
        """Configure the user interface."""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.main_frame = QFrame()

        content_layout = QVBoxLayout()
        content_layout.setSpacing(10)
        content_layout.setContentsMargins(20, 20, 20, 20)

        # Header with theme toggle and close button - matching record page style
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

        # Close button
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

        # Logo - matching homepage style
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

        # Header with title
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

        # Chart frame - matching homepage frame style
        chart_frame = QFrame()
        if self.dark_theme == "dark":
            chart_frame.setStyleSheet(
                "background-color: #282828; border: 1px solid #3C3C3C; border-radius: 8px;"
            )
        else:
            chart_frame.setStyleSheet(
                "background-color: #EEEEEE; border: 1px solid #D9D9D9; border-radius: 8px;"
            )
        chart_frame.setFixedSize(499, 400)  # Adjusted size for smaller window

        chart_layout = QVBoxLayout(chart_frame)
        chart_layout.setContentsMargins(15, 15, 15, 15)

        # Add graphs canvas
        self.canvas = BatteryReportCanvas(chart_frame, width=8, height=4, dpi=80)
        chart_layout.addWidget(self.canvas)

        content_layout.addWidget(chart_frame)

        # Question mark - matching homepage style
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
                /* Main dialog style (transparent) */
                BatteryReportDialog {
                    background-color: transparent;
                }
                
                /* Main frame style with rounded corners */
                QFrame {
                    border-radius: 5px;
                    background-color: #1D1D1D;
                }
                """
            )
        else:
            self.setStyleSheet(
                """
                /* Main dialog style (transparent) */
                BatteryReportDialog {
                    background-color: transparent;
                }
                
                /* Main frame style with rounded corners */
                QFrame {
                    border-radius: 5px;
                    background-color: white;
                }
                """
            )

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
        self.load_report_data(csv_file_path)


def find_latest_csv_file():
    """Find the latest generated CSV file in the current directory"""
    current_dir = Path.cwd()
    csv_files = list(current_dir.glob("PowDroid_*.csv"))

    if not csv_files:
        return None

    # Return the most recent file
    latest_file = max(csv_files, key=os.path.getctime)
    return str(latest_file)


if __name__ == "__main__":
    """Test the battery report dialog"""
    import sys
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    # Find latest CSV file for testing
    csv_file = find_latest_csv_file()
    if csv_file:
        dialog = BatteryReportDialog(csv_file_path=csv_file)
        dialog.show()
        sys.exit(app.exec())
    else:
        print("No CSV file found for testing")
