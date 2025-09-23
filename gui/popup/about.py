"""
Module for the "About" GUI of PowDroid.
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
from PyQt6.QtCore import Qt, QSize, QRect, QUrl
from PyQt6.QtGui import QFont, QPixmap, QIcon, QDesktopServices, QFontDatabase
from typing import Optional
from gui.i18n import t
import os


class AboutDialog(QDialog):
    """
    "About" dialog.
    """

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
        self.setFixedSize(550, 900)

        self.load_fonts()

        # Initialisation du chemin absolu vers le dossier des ressources
        current_dir = os.path.dirname(os.path.abspath(__file__))
        base_dir = os.path.join(current_dir, "..", "..")
        self.ressources_dir = os.path.normpath(
            os.path.join(base_dir, "gui", "ressources")
        )

        # Configuration of flags for rounded corners and remove title bar and buttons
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)

        # Make the background transparent
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Interface configuration
        self.setup_ui()
        self.setup_styles()

    def setup_ui(self):
        """Configure the user interface."""
        # Main layout of the dialog (transparent)
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Create the main QFrame with rounded corners
        self.main_frame = QFrame()

        # Content layout inside the frame
        content_layout = QVBoxLayout()
        content_layout.setSpacing(10)
        content_layout.setContentsMargins(20, 20, 20, 20)

        # Cross button on the top right corner to close the dialog based on an icon
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

        # Method to handle the click
        def close_dialog(event):
            self.close()

        close_button.mousePressEvent = close_dialog

        # Header with the title of the window inside a square box (Not USED)
        title_label = QLabel("ABOUT")
        title_font = QFont(self.font_family, 20, QFont.Weight.DemiBold)
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

        # Header with the logo of PowDroid and the subtitle "Android Energy Profiler"
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
        # subtitle_label = QLabel("Android Energy Profiler")
        # subtitle_font = QFont(self.font_family, 24, QFont.Weight.Normal)
        # subtitle_label.setFont(subtitle_font)
        # subtitle_label.setStyleSheet("color: #57C18B;")
        # subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_layout = QVBoxLayout()
        logo_layout.addWidget(logo_label)
        # logo_layout.addWidget(subtitle_label)
        logo_layout.setContentsMargins(0, 0, 0, 0)

        # Label with the version of PowDroid aligned to the right
        version_label = QLabel("Version " + t("version", language=self.language))
        version_font = QFont(self.font_family, 16, QFont.Weight.Medium)
        version_label.setFont(version_font)
        if self.dark_theme == "dark":
            version_label.setStyleSheet("color: #D2D2D2;")
        else:
            version_label.setStyleSheet("color: #000000;")

        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_label.setContentsMargins(0, 0, 0, 0)

        # Label for the description of PowDroid application
        description_label = QLabel(t("about.description", language=self.language))
        description_font = QFont(self.font_family, 20, QFont.Weight.Medium)
        description_label.setFont(description_font)
        if self.dark_theme == "dark":
            description_label.setStyleSheet("color: #D2D2D2;")
        else:
            description_label.setStyleSheet("color: #000000;")
        description_label.setWordWrap(True)
        description_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        description_label.setContentsMargins(0, 0, 0, 0)

        # Label for the license of PowDroid
        license_label = QLabel(t("about.license", language=self.language))
        license_font = QFont(self.font_family, 20)
        license_font.setItalic(True)
        license_label.setFont(license_font)
        if self.dark_theme == "dark":
            license_label.setStyleSheet("color: #D2D2D2;")
        else:
            license_label.setStyleSheet("color: #000000;")
        license_label.setWordWrap(True)
        license_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        license_label.setContentsMargins(0, 0, 0, 0)

        # Button with the GitHub logo and a title that opens the GitHub page of PowDroid when clicked
        github_button = QPushButton(t("about.github_repo", language=self.language))
        github_button.setIcon(QIcon(os.path.join(self.ressources_dir, "github.png")))
        github_button.setIconSize(QSize(40, 40))
        if self.dark_theme == "dark":
            github_button.setStyleSheet(
                "QPushButton { color: #D2D2D2; background-color: #282828; border: 1px solid #3C3C3C; border-radius: 8px; text-align: center; padding: 0px; } QPushButton:hover { background-color: #3C3C3C; }"
            )
        else:
            github_button.setStyleSheet(
                "QPushButton { color: #000000; background-color: #EEEEEE; border: 1px solid #D9D9D9; border-radius: 8px; text-align: center; padding: 0px; } QPushButton:hover { background-color: #E0E0E0; }"
            )
        github_button.setCursor(Qt.CursorShape.PointingHandCursor)
        github_button.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl("https://github.com/powdroid-project/powdroid")
            )
        )
        github_font = QFont(self.font_family, 24, QFont.Weight.DemiBold)
        github_button.setFont(github_font)
        github_button.setFixedSize(499, 49)

        content_layout.addWidget(
            close_button,
            alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight,
        )
        content_layout.addLayout(logo_layout)
        content_layout.addWidget(
            version_label,
            alignment=Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignCenter,
        )
        content_layout.addWidget(
            description_label, alignment=Qt.AlignmentFlag.AlignCenter
        )
        content_layout.addWidget(
            license_label,
            alignment=Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignCenter,
        )
        content_layout.addWidget(
            github_button,
            alignment=Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignCenter,
        )

        # Apply the layout to the frame
        self.main_frame.setLayout(content_layout)

        # Add the frame to the main layout
        main_layout.addWidget(self.main_frame)

        self.setLayout(main_layout)

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

                """
            )
