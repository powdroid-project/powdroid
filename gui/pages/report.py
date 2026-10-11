"""Report page: summary figures, charts and the raw data table for one PowDroid CSV."""

from datetime import datetime
from itertools import accumulate, groupby

import matplotlib

matplotlib.use("QtAgg")

import matplotlib.dates as mdates  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from PyQt6.QtCore import (  # noqa: E402
    QAbstractTableModel, QModelIndex, QSignalBlocker, Qt, QTimer, QUrl, pyqtSignal,
)
from PyQt6.QtGui import QDesktopServices  # noqa: E402
from PyQt6.QtWidgets import (  # noqa: E402
    QGridLayout, QHBoxLayout, QHeaderView, QLineEdit, QMessageBox, QPushButton, QTableView,
    QTabWidget, QVBoxLayout, QWidget,
)

from core import html_report, metrics  # noqa: E402
from gui.i18n import t  # noqa: E402
from gui.theme import COMPONENT_COLORS, colors, set_role  # noqa: E402
from gui.widgets import ElidedLabel, card, label  # noqa: E402


def _local(ms):
    return datetime.fromtimestamp(ms / 1000)


class Series:
    """Everything the charts plot, computed once per report."""

    def __init__(self, rows):
        self.empty = not rows
        if self.empty:
            return
        # Matplotlib date numbers of the row edges: every row start plus the last end.
        self.x = mdates.date2num([_local(r["start_ms"]) for r in rows] + [_local(rows[-1]["end_ms"])])
        self.cumulative = [0.0, *accumulate(r["energy_j"] or 0 for r in rows)]
        # One value per row; unknown power (e.g. while plugged in) is NaN and plots as a gap.
        self.power = np.array([r["power_w"] for r in rows], dtype=float)
        # On/off bands of the components used during the session: one (start, width)
        # span per run of consecutive "on" rows.
        self.bands = {}
        for column in metrics.BOOL_COLUMNS:
            spans, i = [], 0
            for on, run in groupby(rows, key=lambda r: r[column]):
                n = len(list(run))
                if on:
                    spans.append((self.x[i], self.x[i + n] - self.x[i]))
                i += n
            if spans:
                self.bands[metrics.LABELS[column]] = spans


class Chart(FigureCanvasQTAgg):
    """One matplotlib figure: 'power' (with the component bands) or 'cumulative' energy."""

    def __init__(self, kind):
        super().__init__(Figure(figsize=(6, 4), layout="constrained"))
        self.kind = kind
        self.setMinimumHeight(260)

    def plot(self, series, theme):
        c = colors(theme)
        fig = self.figure
        fig.clear()
        fig.set_facecolor(c["panel"])
        if series.empty:
            self.draw_idle()
            return

        if self.kind == "power":
            ax, bands = fig.subplots(2, 1, sharex=True, height_ratios=[3, max(1.0, 0.3 * len(series.bands))])
        else:
            ax, bands = fig.subplots(), None

        if self.kind == "cumulative":
            ax.plot(series.x, series.cumulative, color=c["accent"], linewidth=1.8)
            ax.set_ylabel("Energy (J)")
        else:
            ax.stairs(series.power, series.x, fill=True, color=c["accent"], alpha=0.2)
            ax.stairs(series.power, series.x, baseline=None, color=c["accent"], linewidth=1.4)
            ax.set_ylabel("Power (W)")
        ax.set_ylim(bottom=0)
        ax.grid(True, color=c["grid"], linewidth=0.6)
        axes = [ax]

        if bands is not None:
            for i, spans in enumerate(series.bands.values()):
                bands.broken_barh(spans, (i + 0.15, 0.7), color=COMPONENT_COLORS[i % len(COMPONENT_COLORS)])
            names = list(series.bands)
            bands.set_yticks([i + 0.5 for i in range(len(names))], names)
            bands.set_ylim(0, len(names))
            bands.invert_yaxis()
            axes.append(bands)

        for a in axes:
            a.set_facecolor(c["panel"])
            a.tick_params(colors=c["muted"], labelsize=9)
            a.yaxis.label.set_color(c["text"])
            for spine in a.spines.values():
                spine.set_color(c["border"])
        axes[-1].xaxis_date()
        axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
        axes[-1].set_xlabel(t("report.time"), color=c["text"])
        self.draw_idle()


def _display(column, value):
    if value is None:
        return ""
    if column in ("start_ms", "end_ms"):
        return _local(value).strftime("%H:%M:%S.%f")[:-3]
    if column in metrics.BOOL_COLUMNS:
        return "ON" if value else ""
    if isinstance(value, float):
        return f"{value:.0f}" if value.is_integer() else f"{value:.4f}"
    return str(value)


class RowsModel(QAbstractTableModel):
    """Read-only table of rows, with its own sorting and filtering.

    Both work on plain Python lists: a QSortFilterProxyModel would call data() for every
    cell, which is slow for long sessions. Cells are formatted only when displayed.
    """

    TIME_COLUMNS = {"start_ms", "end_ms", "elapsed_s"}  # already in row order
    FILTERED_COLUMNS = ("top_app", "wakelocks")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        self.order = []  # indices of the visible rows, in display order
        self.sort_column, self.descending = "start_ms", False
        self.filter_text = ""

    def set_rows(self, rows):
        """Show new rows, in time order and unfiltered."""
        self.beginResetModel()
        self.rows, self.order = rows, list(range(len(rows)))
        self.sort_column, self.descending, self.filter_text = "start_ms", False, ""
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.order)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(metrics.COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return metrics.COLUMNS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        column = metrics.COLUMNS[index.column()]
        return _display(column, self.rows[self.order[index.row()]][column])

    def sort(self, column, order=Qt.SortOrder.AscendingOrder):
        self.sort_column = metrics.COLUMNS[column]
        self.descending = order == Qt.SortOrder.DescendingOrder
        self._refresh()

    def set_filter(self, text):
        """Keep the rows whose top app or wakelocks contain the text (case-insensitive)."""
        self.filter_text = text.strip().lower()
        self._refresh()

    def _refresh(self):
        indices = range(len(self.rows))
        if self.filter_text:
            indices = [i for i in indices if any(
                self.filter_text in (self.rows[i][c] or "").lower() for c in self.FILTERED_COLUMNS)]
        column = self.sort_column
        if column in self.TIME_COLUMNS:
            indices = list(reversed(indices) if self.descending else indices)
        else:
            known = [i for i in indices if self.rows[i][column] is not None]
            known.sort(key=lambda i: self.rows[i][column], reverse=self.descending)
            indices = known + [i for i in indices if self.rows[i][column] is None]  # empty cells last
        self.beginResetModel()
        self.order = indices
        self.endResetModel()


class ReportPage(QWidget):
    new_recording = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.result = None  # the session.Result shown
        self.series = Series([])
        self.theme = "dark"
        self.stale = set()  # charts to redraw when they are next shown

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 8, 24, 24)
        layout.setSpacing(12)

        layout.addWidget(label(t("report.title"), "title"))
        self.subtitle = ElidedLabel(role="muted")
        layout.addWidget(self.subtitle)

        self.warnings = label(role="warning", wrap=True)
        layout.addWidget(self.warnings)

        stats = QGridLayout()
        stats.setSpacing(10)
        self.stats = {}
        for i, key in enumerate(metrics.SUMMARY_LABELS):
            value = label(role="stat-value")
            frame, _ = card(label(t(f"report.{key}"), "stat-label"), value)
            stats.addWidget(frame, i // 4, i % 4)
            self.stats[key] = value
        self.stats["coverage"].setToolTip(t("report.coverage_tooltip"))
        layout.addLayout(stats)

        self.tabs = QTabWidget()
        self.charts = [Chart("power"), Chart("cumulative")]
        for chart, key in zip(self.charts, ("tab_power", "tab_cumulative")):
            self.tabs.addTab(chart, t(f"report.{key}"))
        self.tabs.currentChanged.connect(self._draw_current)

        data_tab = QWidget()
        data_layout = QVBoxLayout(data_tab)
        self.filter = QLineEdit(placeholderText=t("report.filter"))
        self.filter.setClearButtonEnabled(True)
        filter_timer = QTimer(self, singleShot=True, interval=200)
        filter_timer.timeout.connect(lambda: self.model.set_filter(self.filter.text()))
        self.filter.textChanged.connect(filter_timer.start)
        self.model = RowsModel(self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.horizontalHeader().setSortIndicator(0, Qt.SortOrder.AscendingOrder)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setResizeContentsPrecision(50)  # cells of a column have similar widths
        data_layout.addWidget(self.filter)
        data_layout.addWidget(self.table)
        self.tabs.addTab(data_tab, t("report.tab_data"))
        layout.addWidget(self.tabs, 1)

        buttons = QHBoxLayout()
        for key, slot in (("open_folder", self._open_folder), ("export_html", self._export_html)):
            button = QPushButton(t(f"report.{key}"))
            button.clicked.connect(slot)
            buttons.addWidget(button)
        buttons.addStretch()
        new = QPushButton(t("report.new_recording"))
        set_role(new, "primary")
        new.clicked.connect(self.new_recording.emit)
        buttons.addWidget(new)
        layout.addLayout(buttons)

    def show_result(self, result, theme):
        """Show a session.Result (just recorded, or loaded from a CSV)."""
        self.result = result
        self.subtitle.setFullText(str(result.csv_path) + ("" if result.rows else f" — {t('report.empty')}"))
        for key, text in metrics.summary_items(result.summary).items():
            self.stats[key].setText(text)
        self.warnings.setText("\n".join(f"⚠ {w}" for w in result.warnings))
        self.warnings.setVisible(bool(result.warnings))

        with QSignalBlocker(self.filter):
            self.filter.clear()
        with QSignalBlocker(self.table.horizontalHeader()):  # the rows already are in time order
            self.table.horizontalHeader().setSortIndicator(0, Qt.SortOrder.AscendingOrder)
        self.model.set_rows(result.rows)
        self.table.resizeColumnsToContents()
        self.series = Series(result.rows)
        self.set_theme(theme)

    def set_theme(self, theme):
        """Redraw the visible chart now and the others when their tab is opened."""
        self.theme = theme
        self.stale = set(self.charts)
        self._draw_current()

    def _draw_current(self):
        chart = self.tabs.currentWidget()
        if chart in self.stale:
            self.stale.discard(chart)
            chart.plot(self.series, self.theme)

    def _open_folder(self):
        if self.result:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.result.csv_path.parent)))

    def _export_html(self):
        if not self.result:
            return
        try:
            path = html_report.write(self.result)
        except OSError as e:
            QMessageBox.warning(self, t("report.export_html"), str(e))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        self.subtitle.setFullText(t("report.exported", path=path))
