"""Record page: unplug → record → replug → collect, as an explicit state machine."""

from datetime import datetime
from enum import Enum, auto

from PyQt6.QtCore import QElapsedTimer, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QMovie, QPixmap
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from core import session
from core.metrics import format_duration
from gui import workers
from gui.i18n import t
from gui.theme import resource, set_role
from gui.widgets import label


class State(Enum):
    WAIT_UNPLUG = auto()
    RECORDING = auto()
    WAIT_REPLUG = auto()
    PROCESSING = auto()
    ERROR = auto()


STEPS = [State.WAIT_UNPLUG, State.RECORDING, State.WAIT_REPLUG, State.PROCESSING]

# Per state: title key, hint key and image (None: the loading animation).
STATE_UI = {
    State.WAIT_UNPLUG: ("step_unplug", "step_unplug_hint", "phone_plugged.png"),
    State.RECORDING: ("step_recording", "step_recording_hint", "record.png"),
    State.WAIT_REPLUG: ("step_replug", "step_replug_hint", "plug_the_phone.png"),
    State.PROCESSING: ("step_processing", "processing_offset", None),
    State.ERROR: ("step_error", None, "remove.png"),
}
CENTER = Qt.AlignmentFlag.AlignCenter


class RecordPage(QWidget):
    finished = pyqtSignal(object)  # session.Result
    cancelled = pyqtSignal()
    collecting = pyqtSignal(bool)  # True while the batterystats dump runs (device polling is paused)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = None
        self.device = None
        self.output_dir = None
        self.start_time = None
        self.stop_time = None
        self.elapsed = QElapsedTimer()
        self.tick = QTimer(self)
        self.tick.timeout.connect(self._update_timer)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 8, 24, 24)
        layout.setSpacing(16)

        self.step_labels = []
        steps = QHBoxLayout()
        for state in STEPS:
            step = label(t(f"record.{STATE_UI[state][0]}"), wrap=True, align=CENTER)
            steps.addWidget(step, 1)
            self.step_labels.append(step)
        layout.addLayout(steps)
        layout.addStretch()

        self.image = label(align=CENTER)
        self.spinner = QMovie(resource("loading.gif"), parent=self)
        self.spinner.setScaledSize(QSize(96, 96))
        layout.addWidget(self.image)

        self.title = label(role="title", align=CENTER)
        self.timer_label = label(role="timer", align=CENTER)
        self.hint = label(role="muted", wrap=True, align=CENTER)
        self.warning = label(t("record.replugged_warning"), "warning", wrap=True, align=CENTER)
        self.error = label(role="error", wrap=True, align=CENTER)
        self.error.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        for w in (self.title, self.timer_label, self.hint, self.warning, self.error):
            layout.addWidget(w)
        layout.addStretch()

        self.stop_button = QPushButton(t("record.stop"))
        set_role(self.stop_button, "danger")
        self.stop_button.clicked.connect(self._stop_recording)
        self.retry_button = QPushButton(t("record.retry"))
        set_role(self.retry_button, "primary")
        self.retry_button.clicked.connect(self._collect)
        self.cancel_button = QPushButton(t("record.cancel"))
        self.cancel_button.clicked.connect(self._cancel)
        for w in (self.stop_button, self.retry_button, self.cancel_button):
            layout.addWidget(w)

    # -- public API -------------------------------------------------------

    def begin(self, device, output_dir):
        """Called once the device has been prepared (stats reset)."""
        self.device = device
        self.output_dir = output_dir
        self.start_time = self.stop_time = None
        self._set_state(State.WAIT_UNPLUG)

    def is_busy(self):
        return self.state in (State.RECORDING, State.WAIT_REPLUG, State.PROCESSING)

    def on_device_changed(self, device):
        if self.state is None:
            return  # not recording
        connected = device is not None and device.ready and device.serial == self.device.serial
        if self.state == State.WAIT_UNPLUG and not connected:
            self.start_time = datetime.now()
            self.elapsed.start()
            self._set_state(State.RECORDING)
        elif self.state == State.RECORDING:
            self.warning.setVisible(connected)
        elif self.state == State.WAIT_REPLUG and connected:
            self._collect()

    # -- transitions ------------------------------------------------------

    def _set_state(self, state):
        self.state = state
        current = STEPS.index(state) if state in STEPS else STEPS.index(State.PROCESSING)
        for i, step in enumerate(self.step_labels):
            set_role(step, None if i == current else "muted")
            font = step.font()
            font.setBold(i == current)
            step.setFont(font)

        title, hint, image = STATE_UI[state]
        self.title.setText(t(f"record.{title}"))
        self.hint.setText(t(f"record.{hint}") if hint else "")
        if state == State.RECORDING:
            self.hint.setText(self.hint.text() + "\n" + t("record.started_at", time=f"{self.start_time:%H:%M:%S}"))

        if image is None:
            self.image.setMovie(self.spinner)
            self.spinner.start()
        else:
            self.spinner.stop()
            self.image.setPixmap(QPixmap(resource(image)).scaled(
                120, 120, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

        recording = state == State.RECORDING
        if recording:
            self.tick.start(500)
            self._update_timer()
        else:
            self.tick.stop()
        self.timer_label.setVisible(recording or state == State.WAIT_REPLUG)
        self.warning.setVisible(False)
        self.error.setVisible(state == State.ERROR)
        self.stop_button.setVisible(recording)
        self.retry_button.setVisible(state == State.ERROR)
        self.cancel_button.setVisible(state != State.PROCESSING)

    def _update_timer(self):
        self.timer_label.setText(format_duration(self.elapsed.elapsed() / 1000))

    def _stop_recording(self):
        self.stop_time = datetime.now()
        self._update_timer()
        self._set_state(State.WAIT_REPLUG)

    def _collect(self):
        self._set_state(State.PROCESSING)
        self.collecting.emit(True)
        task = workers.Task(session.collect, self.device, self.start_time, self.stop_time,
                            self.output_dir, with_progress=True, parent=self)
        task.progress.connect(lambda step: self.hint.setText(t(f"record.processing_{step}")))
        task.succeeded.connect(self._collected)
        task.failed.connect(self._failed)
        task.start()

    def _collected(self, result):
        self.collecting.emit(False)
        self.state = None
        self.finished.emit(result)

    def _failed(self, message):
        self.collecting.emit(False)
        self.error.setText(message)
        self._set_state(State.ERROR)

    def _cancel(self):
        self.tick.stop()
        self.state = None
        self.cancelled.emit()

