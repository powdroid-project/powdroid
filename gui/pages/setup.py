"""
Fenêtre de configuration utilisant PyQt5.
"""

from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QScrollArea,
    QWidget,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from core.utils import adb_runner as adb
from gui.i18n import t

from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QTextEdit
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont
from core.utils import adb_runner as adb


class SetupWorker(QThread):
    """Worker pour vérifier le setup dans un thread séparé."""

    result_ready = pyqtSignal(str, bool)  # message, success

    def run(self):
        """Vérifie le setup ADB."""
        try:
            # Test de base ADB
            if adb.is_adb_available():
                if adb.is_device_connected():
                    device_info = adb.get_device_info()
                    if device_info:
                        model = device_info.get("model", "Unknown")
                        manufacturer = device_info.get("manufacturer", "Unknown")
                        message = f"✓ Setup OK<br><br>Device détecté:<br>{manufacturer} {model}"
                    else:
                        message = "✓ ADB disponible<br>✓ Device connecté<br><br>Setup complet !"
                    self.result_ready.emit(message, True)
                else:
                    message = "✓ ADB disponible<br>✗ Aucun device connecté<br><br>Connectez votre smartphone en mode débogage USB."
                    self.result_ready.emit(message, False)
            else:
                message = "✗ ADB non disponible<br><br>Vérifiez l'installation d'Android SDK Platform-Tools."
                self.result_ready.emit(message, False)

        except Exception as e:
            message = f"✗ Erreur lors de la vérification:<br>{str(e)}"
            self.result_ready.emit(message, False)


def show_setup_window(parent, ico_dir):
    """Affiche la fenêtre de vérification du setup."""
    dialog = QDialog(parent)
    dialog.setWindowTitle("Vérification du Setup")
    dialog.setFixedSize(500, 400)
    dialog.setModal(True)

    layout = QVBoxLayout()
    dialog.setLayout(layout)

    # Titre
    title = QLabel("Vérification de la Configuration")
    title.setAlignment(Qt.AlignCenter)
    title_font = QFont()
    title_font.setPointSize(16)
    title_font.setBold(True)
    title.setFont(title_font)
    layout.addWidget(title)

    # Zone de texte pour les résultats
    result_text = QTextEdit()
    result_text.setReadOnly(True)
    result_text.setText("Vérification en cours...")
    layout.addWidget(result_text)

    # Boutons
    check_btn = QPushButton("Vérifier à nouveau")
    close_btn = QPushButton("Fermer")

    layout.addWidget(check_btn)
    layout.addWidget(close_btn)

    # Worker pour les vérifications
    worker = SetupWorker()

    def on_result(message, success):
        result_text.setText(message)
        if success:
            result_text.setStyleSheet("color: #4caf50;")
        else:
            result_text.setStyleSheet("color: #e53935;")

    def start_check():
        result_text.setText("Vérification en cours...")
        result_text.setStyleSheet("color: #1976d2;")
        if not worker.isRunning():
            worker.start()

    # Connexions
    worker.result_ready.connect(on_result)
    check_btn.clicked.connect(start_check)
    close_btn.clicked.connect(dialog.accept)

    # Lancer la première vérification
    start_check()

    dialog.exec_()
