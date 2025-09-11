"""
Module for the "Instruction Popup" GUI of PowDroid.
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


class InformationPopup(QDialog):
    """
    "Instruction" dialog.
    """

    def load_fonts(self):
        """Loads custom fonts from the fonts folder."""
        # Get the absolute path of the current script
        current_dir = os.path.dirname(os.path.abspath(__file__))
        base_dir = os.path.join(current_dir, "..", "..")
        font_paths = [
            os.path.join(base_dir, "gui", "ressources", "fonts", "Inter.ttf"),
            os.path.join(base_dir, "gui", "ressources", "fonts", "Inter-Italic.ttf"),
        ]

        self.font_family = "Arial"  # Fallback font

        for font_path in font_paths:
            # Normalize the path
            font_path = os.path.normpath(font_path)

            # Check if the file exists
            if not os.path.exists(font_path):
                continue

            font_id = QFontDatabase.addApplicationFont(font_path)
            if font_id != -1:
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    self.font_family = families[0]
                    break

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        dark_theme="dark",
        language="en",
        plugged=True,
    ):
        """
        Initialize the About dialog.

        Args:
            parent: Parent widget (optional)
        """
        super().__init__(parent)
        self.dark_theme = dark_theme
        self.language = language
        self.plugged = plugged
        self.setModal(True)
        self.setFixedSize(356, 375)

        self.load_fonts()

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
        content_layout.setContentsMargins(10, 10, 10, 10)

        # Header with the title of the window inside a square box (Not USED)
        title_label = QLabel(t("information_popup.title", language=self.language))
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
        title_frame.setFixedSize(326, 49)
        title_layout = QHBoxLayout()
        title_layout.addWidget(title_label)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_frame.setLayout(title_layout)

        picture_label = QLabel()
        if self.plugged:
            message_label = QLabel(
                t("information_popup.unplug", language=self.language)
            )
            picture_label.setPixmap(
                QPixmap("gui/ressources/phone_plugged.png").scaled(
                    184,
                    184,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            message_label = QLabel(t("information_popup.plug", language=self.language))
            picture_label.setPixmap(
                QPixmap("gui/ressources/plug_the_phone.png").scaled(
                    184,
                    184,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

        message_font = QFont(self.font_family, 24, QFont.Weight.DemiBold)
        message_font.setItalic(True)
        message_label.setFont(message_font)
        message_label.setWordWrap(True)
        message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if self.dark_theme == "dark":
            message_label.setStyleSheet("color: #D2D2D2;")
        else:
            message_label.setStyleSheet("color: #000000;")

        content_layout.addWidget(title_frame, alignment=Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(picture_label, alignment=Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(message_label, alignment=Qt.AlignmentFlag.AlignCenter)

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


if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    dialog = InformationPopup(dark_theme="dark", language="en")
    dialog.show()
    sys.exit(app.exec())
