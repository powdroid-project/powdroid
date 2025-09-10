from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QScrollArea,
    QWidget,
    QGridLayout,
    QComboBox,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QPixmap, QPalette
from core.utils import setup
from gui.i18n import t, switch_language, get_current_language, get_available_languages


class ChecklistItem(QFrame):
    def __init__(self, title, description=""):
        super().__init__()
        self.setFrameStyle(QFrame.NoFrame)
        self.setFixedHeight(95)

        layout = QHBoxLayout()
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(15)
        self.setLayout(layout)

        # Status icon
        self.status_label = QLabel("⏳")
        self.status_label.setFixedSize(40, 40)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet(
            "QLabel { font-size: 24px; border-radius: 20px; "
            "background-color: #3a3a3a; color: #cccccc; }"
        )
        layout.addWidget(self.status_label)

        # Text content
        text_layout = QVBoxLayout()

        self.title_label = QLabel(title)
        self.title_label.setFont(QFont("Arial", 14, QFont.Bold))
        self.title_label.setStyleSheet("color: #ffffff;")
        text_layout.addWidget(self.title_label)

        self.description_label = QLabel(description)
        self.description_label.setFont(QFont("Arial", 12))
        self.description_label.setStyleSheet("color: #bbbbbb;")
        text_layout.addWidget(self.description_label)

        layout.addLayout(text_layout)
        layout.addStretch()

        self.set_status("waiting")

    def set_status(self, status, details=""):
        styles = {
            "waiting": ("⏳", "#3a3a3a", "#cccccc", "#2b2b2b"),
            "checking": ("🔄", "#1a237e", "#64b5f6", "#1a1a2e"),
            "success": ("✅", "#1b5e20", "#81c784", "#0d1a0d"),
            "error": ("❌", "#b71c1c", "#ef9a9a", "#1a0d0d"),
        }

        if status in styles:
            icon, bg_color, text_color, frame_bg = styles[status]
            self.status_label.setText(icon)
            self.status_label.setStyleSheet(
                f"QLabel {{ font-size: 24px; border-radius: 20px; "
                f"background-color: {bg_color}; color: {text_color}; border: none; }}"
            )
            self.setStyleSheet(
                f"QFrame {{ border: none; background-color: {frame_bg}; border-radius: 8px; }}"
            )

        if details:
            self.description_label.setText(details)


class SetupWorker(QThread):
    check_started = pyqtSignal(int)
    check_completed = pyqtSignal(int, bool, str, str)
    all_completed = pyqtSignal(bool)

    def run(self):
        try:
            checks = [
                ("Android SDK", setup.check_android_sdk),
                ("Python", setup.check_python_version),
                ("Pandas", setup.check_pandas_module),
                ("GUI Modules", setup.check_gui_modules),
                ("Go Runtime", setup.check_go_runtime),
                ("ADB Server", lambda: setup.initialize_adb_server(verbose=False)),
            ]

            all_good = True

            for i, (name, check_func) in enumerate(checks):
                self.check_started.emit(i)
                self.msleep(500)

                try:
                    result = check_func()
                    details = result.details or result.error or ""
                    self.check_completed.emit(
                        i, result.success, result.message, details
                    )

                    if not result.success:
                        all_good = False

                except Exception as e:
                    error_msg = t("setup.status.error_checking", component=name)
                    self.check_completed.emit(i, False, error_msg, str(e))
                    all_good = False

                self.msleep(300)

            self.all_completed.emit(all_good)

        except Exception:
            self.all_completed.emit(False)


def show_setup_window(parent, ico_dir):
    dialog = QDialog(parent)
    dialog.setWindowTitle(t("setup.title"))
    dialog.setFixedSize(650, 650)
    dialog.setModal(True)

    dialog.setStyleSheet("QDialog { background-color: #1e1e1e; color: #ffffff; }")

    layout = QVBoxLayout()
    dialog.setLayout(layout)

    # Main title
    title = QLabel(t("setup.configuration_check"))
    title.setAlignment(Qt.AlignCenter)
    title_font = QFont()
    title_font.setPointSize(22)
    title_font.setBold(True)
    title.setFont(title_font)
    title.setStyleSheet("QLabel { margin: 15px; color: #ffffff; }")
    layout.addWidget(title)

    # Language selector
    lang_frame = QFrame()
    lang_layout = QHBoxLayout()
    lang_frame.setLayout(lang_layout)
    lang_frame.setStyleSheet(
        "QFrame { background-color: #2b2b2b; border-radius: 8px; "
        "margin: 10px 15px; padding: 10px; }"
    )

    lang_label = QLabel(f"{t('setup.language_selector.label')}:")
    lang_label.setFont(QFont("Arial", 12, QFont.Bold))
    lang_label.setStyleSheet("color: #ffffff; margin-right: 10px;")
    lang_layout.addWidget(lang_label)

    lang_combo = QComboBox()
    available_langs = get_available_languages()
    current_lang = get_current_language()

    for code, name in available_langs.items():
        lang_combo.addItem(name, code)
        if code == current_lang:
            lang_combo.setCurrentText(name)

    # Construire le chemin correct pour l'image de la flèche
    down_arrow_path = str(ico_dir / "down_arrow.png").replace("\\", "/")

    lang_combo.setStyleSheet(
        f"""
        QComboBox {{
            background-color: #3a3a3a; color: #ffffff; border: 1px solid #555555;
            border-radius: 5px; padding: 5px 10px; font-size: 12px; min-width: 120px;
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding; subcontrol-position: top right; width: 20px;
            border-left-width: 1px; border-left-color: #555555; border-left-style: solid;
            border-top-right-radius: 1px; border-bottom-right-radius: 5px;
            background-color: #4a4a4a;
        }}
        QComboBox::down-arrow {{ image: url({down_arrow_path}); width: 12px; height: 12px; }}
        QComboBox QAbstractItemView {{
            background-color: #3a3a3a; color: #ffffff;
            selection-background-color: #555555; border: 1px solid #555555;
        }}
        """
    )

    def handle_language_change():
        selected_code = lang_combo.currentData()
        if selected_code and selected_code != current_lang:
            switch_language(selected_code)
            info_msg = QLabel(f"i {t('setup.language_selector.change_restart')}")
            info_msg.setFont(QFont("Arial", 10))
            info_msg.setStyleSheet("color: #64b5f6; margin-left: 10px;")

            # Remove previous info messages
            for i in range(lang_layout.count()):
                item = lang_layout.itemAt(i)
                if (
                    item
                    and item.widget()
                    and isinstance(item.widget(), QLabel)
                    and "i" in item.widget().text()
                ):
                    item.widget().deleteLater()

            lang_layout.insertWidget(2, info_msg)
            QTimer.singleShot(
                4000, lambda: info_msg.deleteLater() if info_msg else None
            )

    lang_combo.currentTextChanged.connect(handle_language_change)
    lang_layout.addWidget(lang_combo)
    lang_layout.addStretch()

    layout.addWidget(lang_frame)

    # Scrollable checklist area
    scroll_area = QScrollArea()
    scroll_widget = QWidget()
    scroll_layout = QVBoxLayout()
    scroll_layout.setContentsMargins(15, 15, 15, 15)
    scroll_layout.setSpacing(0)
    scroll_widget.setLayout(scroll_layout)

    # Create checklist items
    checklist_items = []
    checks_data = [
        (
            t("setup.checks.android_sdk.title"),
            t("setup.checks.android_sdk.description"),
        ),
        (t("setup.checks.python.title"), t("setup.checks.python.description")),
        (t("setup.checks.pandas.title"), t("setup.checks.pandas.description")),
        (
            t("setup.checks.gui_modules.title"),
            t("setup.checks.gui_modules.description"),
        ),
        (t("setup.checks.go_runtime.title"), t("setup.checks.go_runtime.description")),
        (t("setup.checks.adb_server.title"), t("setup.checks.adb_server.description")),
    ]

    for title, description in checks_data:
        item = ChecklistItem(title, description)
        checklist_items.append(item)
        scroll_layout.addWidget(item)
        scroll_layout.addSpacing(8)

    scroll_layout.addStretch()
    scroll_area.setWidget(scroll_widget)
    scroll_area.setWidgetResizable(True)
    scroll_area.setStyleSheet(
        """
        QScrollArea { border: none; border-radius: 8px; background-color: #2b2b2b; }
        QScrollBar:vertical {
            background-color: #3a3a3a; width: 12px; border-radius: 6px; border: none;
        }
        QScrollBar::handle:vertical {
            background-color: #555555; border-radius: 6px; min-height: 20px; border: none;
        }
        QScrollBar::handle:vertical:hover { background-color: #666666; }
    """
    )
    layout.addWidget(scroll_area)

    # Global status bar
    status_frame = QFrame()
    status_layout = QHBoxLayout()
    status_frame.setLayout(status_layout)

    global_status = QLabel(t("setup.status.ready"))
    global_status.setFont(QFont("Arial", 13, QFont.Bold))
    global_status.setStyleSheet("QLabel { color: #cccccc; padding: 8px; }")
    status_layout.addWidget(global_status)
    status_layout.addStretch()

    layout.addWidget(status_frame)

    # Buttons
    button_layout = QHBoxLayout()

    check_btn = QPushButton(f"🔄 {t('setup.buttons.check')}")
    check_btn.setFixedHeight(40)
    check_btn.setStyleSheet(
        """
        QPushButton {
            background-color: #2e7d32; color: white; border: none;
            padding: 12px 24px; border-radius: 5px; font-weight: bold; font-size: 14px;
        }
        QPushButton:hover { background-color: #45a049; }
        QPushButton:pressed { background-color: #3d8b40; }
        QPushButton:disabled { background-color: #424242; color: #777777; }
    """
    )

    close_btn = QPushButton(t("setup.buttons.close"))
    close_btn.setFixedHeight(40)
    close_btn.setStyleSheet(
        """
        QPushButton {
            background-color: #424242; color: white; border: none;
            padding: 12px 24px; border-radius: 5px; font-weight: bold; font-size: 14px;
        }
        QPushButton:hover { background-color: #616161; }
        QPushButton:pressed { background-color: #212121; }
    """
    )

    button_layout.addWidget(check_btn)
    button_layout.addWidget(close_btn)
    layout.addLayout(button_layout)

    # Setup verification worker
    worker = SetupWorker()

    def on_check_started(index):
        if index < len(checklist_items):
            checklist_items[index].set_status("checking")

    def on_check_completed(index, success, message, details):
        if index < len(checklist_items):
            status = "success" if success else "error"
            display_details = details if details else message
            checklist_items[index].set_status(status, display_details)

    def on_all_completed(all_success):
        if all_success:
            global_status.setText(f"✅ {t('setup.status.complete_success')}")
            global_status.setStyleSheet(
                "QLabel { color: #81c784; padding: 5px; font-weight: bold; }"
            )
        else:
            global_status.setText(f"⚠️ {t('setup.status.complete_errors')}")
            global_status.setStyleSheet(
                "QLabel { color: #ef9a9a; padding: 5px; font-weight: bold; }"
            )

        check_btn.setEnabled(True)
        check_btn.setText(f"🔄 {t('setup.buttons.recheck')}")

    def start_check():
        global_status.setText(f"🔄 {t('setup.status.checking')}")
        global_status.setStyleSheet(
            "QLabel { color: #64b5f6; padding: 5px; font-weight: bold; }"
        )

        for item in checklist_items:
            item.set_status("waiting")

        check_btn.setEnabled(False)

        if not worker.isRunning():
            worker.start()

    worker.check_started.connect(on_check_started)
    worker.check_completed.connect(on_check_completed)
    worker.all_completed.connect(on_all_completed)
    check_btn.clicked.connect(start_check)
    close_btn.clicked.connect(dialog.accept)

    QTimer.singleShot(500, start_check)
    dialog.exec_()
