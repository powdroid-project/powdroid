"""Record page: unplug → record → replug → collect, as an explicit state machine.

Over Wi-Fi, the phone stays connected: "unplugged" means running on battery (polled with
`dumpsys battery` while waiting for it, never while recording), and the data is collected
right after the recording stops, without plugging the phone back in.
"""

import logging
import time
from datetime import datetime
from enum import Enum, auto
from functools import partial

from PyQt6.QtCore import QElapsedTimer, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QKeySequence, QMovie, QPixmap, QShortcut
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from powdroid.core import adb, pending, session
from powdroid.core.metrics import format_duration
from powdroid.gui import workers
from powdroid.gui.i18n import t
from powdroid.gui.theme import resource, set_role
from powdroid.gui.widgets import label


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
# Over Wi-Fi: the title and hint keys that replace those of STATE_UI.
WIFI_UI = {
    State.WAIT_UNPLUG: ("step_unplug_wifi", "step_unplug_wifi_hint"),
    State.WAIT_REPLUG: ("step_reconnect_wifi", "step_reconnect_wifi_hint"),
}
POWER_POLL_MS = 1000
CENTER = Qt.AlignmentFlag.AlignCenter

logger = logging.getLogger("powdroid.gui")


class RecordPage(QWidget):
    finished = pyqtSignal(object)  # session.Result
    cancelled = pyqtSignal()
    collecting = pyqtSignal(bool)  # True while the batterystats dump runs (device polling is paused)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = None
        self.device = None
        self.output_dir = None
        self.preparation = session.Preparation()
        self.wireless = False  # the device is connected over Wi-Fi
        self.connected = True  # whether adb lists the device as ready
        self.start_time = None
        self.stop_time = None
        self.markers = []  # [{"time": computer time, "label": text}]
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
        self.no_coulomb = label(t("record.no_coulomb"), "warning", wrap=True, align=CENTER)
        self.perfetto_note = label(role="muted", wrap=True, align=CENTER)  # why Perfetto is not used
        self.marker_list = label(role="muted", wrap=True, align=CENTER)
        self.marker_list.setTextFormat(Qt.TextFormat.PlainText)
        self.error = label(role="error", wrap=True, align=CENTER)
        self.error.setTextFormat(Qt.TextFormat.PlainText)  # may quote adb output
        self.error.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        for w in (self.title, self.timer_label, self.hint, self.warning, self.no_coulomb, self.perfetto_note,
                  self.marker_list, self.error):
            layout.addWidget(w)
        layout.addStretch()

        self.marker_button = QPushButton(t("record.add_marker"))
        self.marker_button.setToolTip(t("record.add_marker_tooltip"))
        self.marker_button.clicked.connect(self.add_marker)
        QShortcut(QKeySequence("M"), self, self.add_marker)
        self.stop_button = QPushButton(t("record.stop"))
        set_role(self.stop_button, "danger")
        self.stop_button.clicked.connect(self._stop_recording)
        self.retry_button = QPushButton(t("record.retry"))
        set_role(self.retry_button, "primary")
        self.retry_button.clicked.connect(self._collect)
        self.cancel_button = QPushButton(t("record.cancel"))
        self.cancel_button.clicked.connect(self._cancel)
        for w in (self.marker_button, self.stop_button, self.retry_button, self.cancel_button):
            layout.addWidget(w)

    # -- public API -------------------------------------------------------

    def begin(self, device, output_dir, preparation):
        """Called once the device has been prepared (session.prepare: stats reset, Perfetto trace started).

        A battery without a coulomb counter is warned about (the session must be long), and
        Perfetto not being available is mentioned.
        """
        self.device = device
        self.output_dir = output_dir
        self.preparation = preparation
        self.wireless, self.connected = device.wireless, True
        self.perfetto_note.setText(preparation.perfetto_notice or "")
        self.start_time = self.stop_time = None
        self.markers = []
        for state, step in zip(STEPS, self.step_labels):
            step.setText(t(f"record.{WIFI_UI.get(state, STATE_UI[state])[0] if self.wireless else STATE_UI[state][0]}"))
        self._save()
        self._set_state(State.WAIT_UNPLUG)
        if self.wireless:
            self._poll_power()

    def add_marker(self):
        """Mark this moment of the recording (button or M key)."""
        if self.state != State.RECORDING:
            return
        marker = {"time": time.time(), "label": t("record.marker_label", number=len(self.markers) + 1)}
        self.markers.append(marker)
        self._save()
        logger.info("Marker %r at %s", marker["label"], datetime.fromtimestamp(marker["time"]))
        self.marker_list.setText(", ".join(
            f"{m['label']} ({format_duration(m['time'] - self.start_time)})" for m in self.markers))
        self.marker_list.setVisible(True)

    def is_busy(self):
        return self.state in (State.RECORDING, State.WAIT_REPLUG, State.PROCESSING)

    def on_devices_changed(self, devices):
        """Follow the recorded device (other devices may be connected too)."""
        if self.state is None:
            return  # not recording
        connected = self.connected = any(d.ready and d.serial == self.device.serial for d in devices)
        logger.debug("Device %s while %s", "connected" if connected else "disconnected", self.state.name)
        if self.state == State.WAIT_REPLUG and connected:
            self._collect()
        elif self.wireless:
            return  # the connection says nothing about the power: see _poll_power
        elif self.state == State.WAIT_UNPLUG and not connected:
            self._start_recording()
        elif self.state == State.RECORDING:
            self.warning.setVisible(connected)

    def _poll_power(self):
        """Over Wi-Fi, while waiting for the phone to run on battery: ask it every second."""
        if self.state != State.WAIT_UNPLUG:
            return
        task = workers.Task(adb.battery_status, self.device.serial, parent=self)
        task.succeeded.connect(self._power_known)
        task.failed.connect(lambda message: QTimer.singleShot(POWER_POLL_MS, self._poll_power))
        task.start()

    def _power_known(self, status):
        if self.state != State.WAIT_UNPLUG:
            return
        if status.plugged is False:
            self._start_recording()
        else:
            QTimer.singleShot(POWER_POLL_MS, self._poll_power)

    # -- transitions ------------------------------------------------------

    def _set_state(self, state):
        logger.info("Recording page: %s", state.name)
        self.state = state
        current = STEPS.index(state) if state in STEPS else STEPS.index(State.PROCESSING)
        for i, step in enumerate(self.step_labels):
            set_role(step, None if i == current else "muted")
            font = step.font()
            font.setBold(i == current)
            step.setFont(font)

        title, hint, image = STATE_UI[state]
        if self.wireless:
            title, hint = WIFI_UI.get(state, (title, hint))
        self.title.setText(t(f"record.{title}"))
        self.hint.setText(t(f"record.{hint}") if hint else "")
        if state == State.RECORDING:
            started = datetime.fromtimestamp(self.start_time)
            self.hint.setText(self.hint.text() + "\n" + t("record.started_at", time=f"{started:%H:%M:%S}"))

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
        before_replug = state in (State.WAIT_UNPLUG, State.RECORDING)
        # An unknown counter (None) is not warned about: the results will tell.
        self.no_coulomb.setVisible(self.preparation.coulomb is False and before_replug)
        self.perfetto_note.setVisible(bool(self.preparation.perfetto_notice) and before_replug)
        self.error.setVisible(state == State.ERROR)
        self.stop_button.setVisible(recording)
        self.marker_button.setVisible(recording)
        self.marker_list.setVisible(bool(self.markers) and state != State.ERROR)
        self.retry_button.setVisible(state == State.ERROR)
        self.cancel_button.setVisible(state != State.PROCESSING)

    def _update_timer(self):
        self.timer_label.setText(format_duration(self.elapsed.elapsed() / 1000))

    def _save(self):
        """Keep what collecting this session needs, in case PowDroid stops before (core/pending.py)."""
        pending.save(self.device, self.preparation, self.output_dir, start=self.start_time, stop=self.stop_time,
                     markers=self.markers)

    def _start_recording(self):
        self.start_time = time.time()
        self.elapsed.start()
        self._save()
        self._set_state(State.RECORDING)

    def _stop_recording(self):
        self.stop_time = time.time()
        self._save()
        logger.info("Recording from %s to %s", *(datetime.fromtimestamp(t) for t in (self.start_time, self.stop_time)))
        self._update_timer()
        if self.wireless and self.connected:
            self._collect()  # no need to plug the phone back in
        else:
            self._set_state(State.WAIT_REPLUG)

    def _collect(self):
        self._set_state(State.PROCESSING)
        self.collecting.emit(True)
        task = workers.Task(partial(session.collect, preparation=self.preparation, markers=self.markers),
                            self.device, self.start_time, self.stop_time, self.output_dir, with_progress=True,
                            parent=self)
        task.progress.connect(lambda step: self.hint.setText(t(f"record.processing_{step}")))
        task.succeeded.connect(self._collected)
        task.failed.connect(self._failed)
        task.start()

    def _collected(self, result):
        self.collecting.emit(False)
        self.state = None
        pending.clear(self.device.serial)
        self.finished.emit(result)

    def _failed(self, message):
        self.collecting.emit(False)
        self.error.setText(message)
        self._set_state(State.ERROR)

    def _cancel(self):
        logger.info("Recording cancelled")
        self.tick.stop()
        self.state = None
        workers.Task(session.cancel, self.preparation, parent=self).start()
        pending.clear(self.device.serial)
        self.cancelled.emit()

    def quit(self):
        """When the application quits before a prepared session is collected.

        Before recording, the phone is given back. A recorded session is kept, to be
        collected when PowDroid starts again (the home page offers it).
        """
        if self.state == State.WAIT_UNPLUG:
            logger.info("Quitting before recording: the session is cancelled")
            self.state = None
            session.cancel(self.preparation)
            pending.clear(self.device.serial)
        elif self.state in (State.RECORDING, State.WAIT_REPLUG, State.ERROR):
            logger.info("Quitting while %s: the session is kept to be collected later", self.state.name)
            self.tick.stop()
            self.state = None

