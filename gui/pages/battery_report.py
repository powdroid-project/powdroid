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
    QTabWidget,
    QApplication,
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
    def enterEvent(self, event):
        from PyQt6.QtGui import QCursor
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.unsetCursor()
        super().leaveEvent(event)
    """Custom matplotlib canvas for cumulative energy graph"""

    def __init__(
        self,
        parent=None,
        width=12,
        height=6,
        dpi=100,
        dark_theme="dark",
        is_fullscreen=False,
    ):
        self.figure = Figure(figsize=(width, height), dpi=dpi)
        super(BatteryReportCanvas, self).__init__(self.figure)
        self.setParent(parent)
        self.dark_theme = dark_theme
        self.csv_data = None  # Store data for re-plotting
        self.parent_dialog = parent  # Store reference to parent dialog
        self.is_fullscreen = is_fullscreen  # Flag to disable clicks in fullscreen

        # Initialisation du chemin absolu vers le dossier des ressources
        current_dir = os.path.dirname(os.path.abspath(__file__))
        base_dir = os.path.join(current_dir, "..", "..")
        self.ressources_dir = os.path.normpath(
            os.path.join(base_dir, "gui", "ressources")
        )

        FigureCanvas.setSizePolicy(
            self, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        FigureCanvas.updateGeometry(self)

        self.apply_theme()

        # Add click event handler only if not in fullscreen
        if not self.is_fullscreen:
            self.mpl_connect("button_press_event", self.on_click)

    def on_click(self, event):
        """Handle mouse click events to open full screen"""
        if event.inaxes is not None and hasattr(self, "csv_data") and self.csv_data:
            # Find the main dialog parent to get theme and csv path
            parent = self.parent_dialog
            while parent and not hasattr(parent, "dark_theme"):
                parent = parent.parent() if hasattr(parent, "parent") else None

            if parent and hasattr(parent, "dark_theme"):
                full_screen_dialog = FullScreenGraphDialog(
                    csv_file_path=self.csv_data,
                    graph_type="cumulative",
                    dark_theme=parent.dark_theme,
                    parent=parent,
                )
                full_screen_dialog.exec()

    def apply_theme(self):
        """Apply theme-specific styling to the matplotlib figure"""
        if self.dark_theme == "dark":
            plt.style.use("dark_background")
            self.figure.patch.set_facecolor("#2b2b2b")
        else:
            plt.style.use("default")
            self.figure.patch.set_facecolor("#f5f5f5")

    def update_theme(self, dark_theme):
        """Update the theme and re-plot the data"""
        self.dark_theme = dark_theme
        self.apply_theme()
        if self.csv_data is not None:
            self.plot_battery_data(self.csv_data)

    def get_theme_colors(self):
        """Get colors based on current theme"""
        if self.dark_theme == "dark":
            return {
                "line_color": "#FF6B6B",
                "text_color": "white",
                "grid_color": "white",
                "background_color": "#2b2b2b",
            }
        else:
            return {
                "line_color": "#D63384",
                "text_color": "black",
                "grid_color": "gray",
                "background_color": "#f5f5f5",
            }

    def plot_battery_data(self, csv_file_path):
        """Plot cumulative energy data from CSV file"""
        try:
            self.csv_data = csv_file_path  # Store for re-plotting
            df = pd.read_csv(csv_file_path)

            df["start_datetime"] = pd.to_datetime(df["start_time"], unit="ms")
            df["Cumulative_Energy"] = df["Energy (J)"].cumsum()

            self.figure.clear()
            colors = self.get_theme_colors()

            ax = self.figure.add_subplot(111)

            ax.plot(
                df["start_datetime"],
                df["Cumulative_Energy"],
                color=colors["line_color"],
                linewidth=2,
                marker="o",
                markersize=1,
            )

            ax.set_title(
                "Cumulative Energy Consumption",
                fontsize=16,
                color=colors["text_color"],
                pad=20,
            )
            ax.set_xlabel("Elapsed Time (s)", fontsize=12, color=colors["text_color"])
            ax.set_ylabel(
                "Cumulative Energy (J)", fontsize=12, color=colors["text_color"]
            )
            ax.grid(True, alpha=0.3, color=colors["grid_color"])
            ax.tick_params(colors=colors["text_color"])

            ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
            ax.tick_params(axis="x", rotation=45)

            ax.set_facecolor(colors["background_color"])

            # Adjust layout to fit the frame better
            self.figure.tight_layout(pad=1.0)

            # Additional adjustment for better fit
            self.figure.subplots_adjust(left=0.1, right=0.95, top=0.9, bottom=0.22)

            self.draw()

        except Exception as e:
            print(f"Error plotting battery data: {e}")
            self.figure.clear()
            colors = self.get_theme_colors()
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
            ax.set_facecolor(colors["background_color"])
            self.draw()


class EnergyCanvas(FigureCanvas):
    def enterEvent(self, event):
        from PyQt6.QtGui import QCursor
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.unsetCursor()
        super().leaveEvent(event)
    """Custom matplotlib canvas for normal energy graph"""

    def __init__(
        self,
        parent=None,
        width=12,
        height=6,
        dpi=100,
        dark_theme="dark",
        is_fullscreen=False,
    ):
        self.figure = Figure(figsize=(width, height), dpi=dpi)
        super(EnergyCanvas, self).__init__(self.figure)
        self.setParent(parent)
        self.dark_theme = dark_theme
        self.csv_data = None  # Store data for re-plotting
        self.parent_dialog = parent  # Store reference to parent dialog
        self.is_fullscreen = is_fullscreen  # Flag to disable clicks in fullscreen

        FigureCanvas.setSizePolicy(
            self, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        FigureCanvas.updateGeometry(self)

        self.apply_theme()

        # Add click event handler only if not in fullscreen
        if not self.is_fullscreen:
            self.mpl_connect("button_press_event", self.on_click)

    def on_click(self, event):
        """Handle mouse click events to open full screen"""
        if event.inaxes is not None and hasattr(self, "csv_data") and self.csv_data:
            # Find the main dialog parent to get theme and csv path
            parent = self.parent_dialog
            while parent and not hasattr(parent, "dark_theme"):
                parent = parent.parent() if hasattr(parent, "parent") else None

            if parent and hasattr(parent, "dark_theme"):
                full_screen_dialog = FullScreenGraphDialog(
                    csv_file_path=self.csv_data,
                    graph_type="energy",
                    dark_theme=parent.dark_theme,
                    parent=parent,
                )
                full_screen_dialog.exec()

    def apply_theme(self):
        """Apply theme-specific styling to the matplotlib figure"""
        if self.dark_theme == "dark":
            plt.style.use("dark_background")
            self.figure.patch.set_facecolor("#2b2b2b")
        else:
            plt.style.use("default")
            self.figure.patch.set_facecolor("#f5f5f5")

    def update_theme(self, dark_theme):
        """Update the theme and re-plot the data"""
        self.dark_theme = dark_theme
        self.apply_theme()
        if self.csv_data is not None:
            self.plot_energy_data(self.csv_data)

    def get_theme_colors(self):
        """Get colors based on current theme"""
        if self.dark_theme == "dark":
            return {
                "line_color": "#FF6B6B",
                "text_color": "white",
                "grid_color": "white",
                "background_color": "#2b2b2b",
            }
        else:
            return {
                "line_color": "#D63384",
                "text_color": "black",
                "grid_color": "gray",
                "background_color": "#f5f5f5",
            }

    def plot_energy_data(self, csv_file_path):
        """Plot normal energy data from CSV file"""
        try:
            self.csv_data = csv_file_path  # Store for re-plotting
            df = pd.read_csv(csv_file_path)

            df["start_datetime"] = pd.to_datetime(df["start_time"], unit="ms")

            self.figure.clear()
            colors = self.get_theme_colors()

            ax = self.figure.add_subplot(111)

            ax.plot(
                df["start_datetime"],
                df["Energy (J)"],
                color=colors["line_color"],
                linewidth=2,
                marker="o",
                markersize=1,
            )

            ax.set_title(
                "Energy Consumption over time", fontsize=16, color=colors["text_color"], pad=20
            )
            ax.set_xlabel("Elapsed Time (s)", fontsize=12, color=colors["text_color"])
            ax.set_ylabel("Energy (J)", fontsize=12, color=colors["text_color"])
            ax.grid(True, alpha=0.3, color=colors["grid_color"])
            ax.tick_params(colors=colors["text_color"])

            ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
            ax.tick_params(axis="x", rotation=45)

            ax.set_facecolor(colors["background_color"])

            # Adjust layout to fit the frame better
            self.figure.tight_layout(pad=1.0)

            # Additional adjustment for better fit
            self.figure.subplots_adjust(left=0.1, right=0.95, top=0.9, bottom=0.22)

            self.draw()

        except Exception as e:
            print(f"Error plotting energy data: {e}")
            self.figure.clear()
            colors = self.get_theme_colors()
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
            ax.set_facecolor(colors["background_color"])
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

            
            display_text = '<span style="font-size:16px;">🔗</span> <span>Click here to see raw data</span>'
            

            self.file_path_label.setText(display_text)
            self.file_path_label.show()
        elif hasattr(self, "file_path_label"):
            self.file_path_label.hide()

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
        self.update_theme_button_icon()

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

  

        if hasattr(self, "energy_total_label"):
            if self.dark_theme == "dark":
                self.energy_total_label.setStyleSheet(
                    "color: #D2D2D2; margin: 10px 0px;"
                )
            else:
                self.energy_total_label.setStyleSheet(
                    "color: #000000; margin: 10px 0px;"
                )

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

        if hasattr(self, "cumulative_canvas") and hasattr(self, "energy_canvas"):
            # Update theme for both canvas
            self.cumulative_canvas.update_theme(self.dark_theme)
            self.energy_canvas.update_theme(self.dark_theme)

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

        content_layout.addLayout(header_buttons_layout)

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

        # Create tab widget for different chart views
        self.tab_widget = QTabWidget()
        self.tab_widget.setFixedSize(499, 440)

        # Cumulative Energy Tab
        cumulative_tab = QWidget()
        cumulative_layout = QVBoxLayout(cumulative_tab)
        cumulative_layout.setContentsMargins(10, 10, 10, 10)
        cumulative_layout.setSpacing(0)

        self.cumulative_canvas = BatteryReportCanvas(
            self,
            width=8,
            height=4,
            dpi=80,
            dark_theme=self.dark_theme,
            is_fullscreen=False,
        )
        cumulative_layout.addWidget(self.cumulative_canvas)

        self.tab_widget.addTab(cumulative_tab, "Cumulative Energy")

        # Normal Energy Tab
        energy_tab = QWidget()
        energy_layout = QVBoxLayout(energy_tab)
        energy_layout.setContentsMargins(10, 10, 10, 10)
        energy_layout.setSpacing(0)

        self.energy_canvas = EnergyCanvas(
            self,
            width=8,
            height=4,
            dpi=80,
            dark_theme=self.dark_theme,
            is_fullscreen=False,
        )
        energy_layout.addWidget(self.energy_canvas)

        self.tab_widget.addTab(energy_tab, "Energy Over Time")

        content_layout.addWidget(self.tab_widget)

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
                    color: #4FC3F7;
                    background: none;
                    border: none;
                    font-style: italic;
                    text-decoration: underline;
                }
                QLabel:hover {
                    color: #82B1FF;
                    text-decoration: underline;
                }
                """
            )
        else:
            self.file_path_label.setStyleSheet(
                """
                QLabel {
                    color: #1976D2;
                    background: none;
                    border: none;
                    font-style: italic;
                    text-decoration: underline;
                }
                QLabel:hover {
                    color: #1565C0;
                    text-decoration: underline;
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

        # Energy total label

        self.energy_total_label = QLabel("🔋⚡ Total Energy: -- J")
        energy_total_font = QFont(self.font_family, 14, QFont.Weight.DemiBold)
        self.energy_total_label.setFont(energy_total_font)
        self.energy_total_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        if self.dark_theme == "dark":
            self.energy_total_label.setStyleSheet(
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
            self.energy_total_label.setStyleSheet(
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

        content_layout.addWidget(
            self.energy_total_label, alignment=Qt.AlignmentFlag.AlignCenter
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
                
                QTabWidget::pane {
                    border: 1px solid #3C3C3C;
                    background-color: #282828;
                    border-radius: 8px;
                }
                
                QTabWidget::tab-bar {
                    alignment: center;
                }
                
                QTabBar::tab {
                    background-color: #1D1D1D;
                    color: #D2D2D2;
                    border: 1px solid #3C3C3C;
                    padding: 8px 16px;
                    margin-right: 2px;
                    border-top-left-radius: 8px;
                    border-top-right-radius: 8px;
                    min-width: 120px;
                }
                
                QTabBar::tab:selected {
                    background-color: #282828;
                    color: #FFFFFF;
                    border-bottom: 1px solid #282828;
                }
                
                QTabBar::tab:hover {
                    background-color: #3C3C3C;
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
                
                QTabWidget::pane {
                    border: 1px solid #D9D9D9;
                    background-color: #EEEEEE;
                    border-radius: 8px;
                }
                
                QTabWidget::tab-bar {
                    alignment: center;
                }
                
                QTabBar::tab {
                    background-color: #F5F5F5;
                    color: #333333;
                    border: 1px solid #D9D9D9;
                    padding: 8px 16px;
                    margin-right: 2px;
                    border-top-left-radius: 8px;
                    border-top-right-radius: 8px;
                    min-width: 120px;
                }
                
                QTabBar::tab:selected {
                    background-color: #EEEEEE;
                    color: #000000;
                    border-bottom: 1px solid #EEEEEE;
                }
                
                QTabBar::tab:hover {
                    background-color: #E0E0E0;
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
            # Calculate total energy from CSV
            df = pd.read_csv(csv_file_path)
            if "Energy (J)" in df.columns:
                total_energy = df["Energy (J)"].sum()
                self.update_energy_total_label(total_energy)

            # Plot cumulative energy graph
            if hasattr(self, "cumulative_canvas"):
                self.cumulative_canvas.plot_battery_data(csv_file_path)

            # Plot normal energy graph
            if hasattr(self, "energy_canvas"):
                self.energy_canvas.plot_energy_data(csv_file_path)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load report data: {str(e)}")
            # Set error message for energy total if CSV can't be read
            if hasattr(self, "energy_total_label"):
                self.energy_total_label.setText("Energy total: Error reading data")

    def update_energy_total_label(self, total_energy):
        """Update the energy total label with formatted value"""
        if hasattr(self, "energy_total_label"):
            # Format the energy value with appropriate units
            if total_energy >= 1000000:  # >= 1 MJ
                formatted_energy = f"{total_energy/1000000:.2f} MJ"
            elif total_energy >= 1000:  # >= 1 kJ
                formatted_energy = f"{total_energy/1000:.2f} kJ"
            else:
                formatted_energy = f"{total_energy:.2f} J"

            self.energy_total_label.setText(f"🔋⚡ Total energy: {formatted_energy}")

    def set_csv_file(self, csv_file_path):
        """Set the CSV file path and load data"""
        self.csv_file_path = csv_file_path
        self.update_file_path_label()
        self.load_report_data(csv_file_path)


class FullScreenGraphDialog(QDialog):
    """Full screen dialog for displaying graphs"""

    def __init__(self, csv_file_path, graph_type, dark_theme="dark", parent=None):
        """
        Initialize the full screen graph dialog.

        Args:
            csv_file_path: Path to the CSV file
            graph_type: Type of graph ("cumulative" or "energy")
            dark_theme: Theme mode ("dark" or "light")
            parent: Parent widget
        """
        super().__init__(parent)
        self.csv_file_path = csv_file_path
        self.graph_type = graph_type
        self.dark_theme = dark_theme

        # macOS-compatible full screen setup
        self.setWindowFlags(Qt.WindowType.Window)
        self.setModal(True)

        # Get screen geometry
        screen = QApplication.primaryScreen()
        screen_geometry = screen.geometry()

        # Set window to cover the entire screen
        self.setGeometry(screen_geometry)
        self.setWindowState(Qt.WindowState.WindowMaximized)

        self.setup_ui()
        self.setup_styles()

        # Load the graph data
        if csv_file_path and os.path.exists(csv_file_path):
            self.load_graph_data()

    def setup_ui(self):
        """Setup the full screen UI"""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(40, 40, 40, 40)

        # (Titre supprimé dans la boîte de dialogue plein écran)

        # Graph canvas
        if self.graph_type == "cumulative":
            self.canvas = BatteryReportCanvas(
                self,
                width=18,
                height=12,
                dpi=100,
                dark_theme=self.dark_theme,
                is_fullscreen=True,
            )
        else:
            self.canvas = EnergyCanvas(
                self,
                width=18,
                height=12,
                dpi=100,
                dark_theme=self.dark_theme,
                is_fullscreen=True,
            )

        main_layout.addWidget(self.canvas)

        # Instructions
        instruction_label = QLabel("Press ESC to exit full screen")
        instruction_label.setFont(QFont("Arial", 12))
        instruction_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(instruction_label)

        self.setLayout(main_layout)

    def setup_styles(self):
        """Setup styles based on theme"""
        if self.dark_theme == "dark":
            self.setStyleSheet(
                """
                FullScreenGraphDialog {
                    background-color: #1D1D1D;
                }
                QLabel {
                    color: white;
                }
            """
            )
        else:
            self.setStyleSheet(
                """
                FullScreenGraphDialog {
                    background-color: white;
                }
                QLabel {
                    color: black;
                }
            """
            )

    def load_graph_data(self):
        """Load and display the graph data"""
        try:
            if self.graph_type == "cumulative":
                self.canvas.plot_battery_data(self.csv_file_path)
            else:
                self.canvas.plot_energy_data(self.csv_file_path)
        except Exception as e:
            print(f"Error loading full screen graph: {e}")

    def keyPressEvent(self, event):
        """Handle key press events"""
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        super().keyPressEvent(event)


def find_latest_csv_file():
    current_dir = Path.cwd()
    csv_files = list(current_dir.glob("PowDroid_*.csv"))

    if not csv_files:
        return None

    latest_file = max(csv_files, key=os.path.getctime)
    return str(latest_file)
