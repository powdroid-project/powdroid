"""Report page: summary figures, charts and the raw data table for one PowDroid CSV."""

from datetime import datetime
from itertools import accumulate, groupby
from pathlib import Path

import matplotlib

matplotlib.use("QtAgg")

import matplotlib.dates as mdates  # noqa: E402
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from PyQt6.QtCore import (  # noqa: E402
    QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, QTimer, QUrl, pyqtSignal,
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
        # Matplotlib date numbers for every boundary: row starts plus the last end.
        self.x = mdates.date2num([_local(r["start_time"]) for r in rows] + [_local(rows[-1]["end_time"])])
        self.energy = [r["Energy (J)"] or 0 for r in rows]
        self.cumulative = [0.0, *accumulate(self.energy)]
        self.power = [r["Power (W)"] or 0 for r in rows]
        # On/off bands: one (start, width) span per run of consecutive "on" rows.
        self.bands = {}
        for column, name in metrics.BOOL_COLUMNS.items():
            spans, i = [], 0
            for on, run in groupby(rows, key=lambda r: r[column]):
                n = len(list(run))
                if on:
                    spans.append((self.x[i], self.x[i + n] - self.x[i]))
                i += n
            self.bands[name] = spans


class Chart(FigureCanvasQTAgg):
    """One matplotlib figure; kind is 'energy', 'cumulative' or 'power'."""

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
            ax, bands = fig.subplots(2, 1, sharex=True, height_ratios=[3, 1.6])
        else:
            ax, bands = fig.subplots(), None

        if self.kind == "cumulative":
            ax.plot(series.x, series.cumulative, color=c["accent"], linewidth=1.8)
            ax.set_ylabel("Energy (J)")
        else:
            values = series.power if self.kind == "power" else series.energy
            y = values + values[-1:]
            ax.step(series.x, y, where="post", color=c["accent"], linewidth=1.4)
            ax.fill_between(series.x, y, step="post", color=c["accent"], alpha=0.2)
            ax.set_ylabel("Power (W)" if self.kind == "power" else "Energy (J)")
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


class RowsModel(QAbstractTableModel):
    """Read-only table of rows; display strings and sort keys are computed once."""

    def __init__(self, rows, parent=None):
        super().__init__(parent)
        self.display = [[self._display(c, r.get(c)) for c in metrics.COLUMNS] for r in rows]
        self.keys = [[self._key(c, r.get(c)) for c in metrics.COLUMNS] for r in rows]

    @staticmethod
    def _display(column, value):
        if value is None:
            return ""
        if column in ("start_time", "end_time"):
            return _local(value).strftime("%H:%M:%S.%f")[:-3]
        if column in metrics.BOOL_COLUMNS:
            return "ON" if value else ""
        if isinstance(value, float):
            return f"{value:.0f}" if value.is_integer() else f"{value:.4f}"
        return str(value)

    @staticmethod
    def _key(column, value):
        if column in metrics.NUMERIC_COLUMNS:
            return float("-inf") if value is None else value
        return "" if value is None else str(value)

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.display)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(metrics.COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return metrics.COLUMNS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            return self.display[index.row()][index.column()]
        if role == Qt.ItemDataRole.UserRole:  # sort key
            return self.keys[index.row()][index.column()]
        return None


class ReportPage(QWidget):
    new_recording = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.csv_path = None
        self.series = Series([])
        self.theme = "dark"
        self.stale = set()  # charts to redraw when they are next shown

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 8, 24, 24)
        layout.setSpacing(12)

        layout.addWidget(label(t("report.title"), "title"))
        self.subtitle = ElidedLabel(role="muted")
        layout.addWidget(self.subtitle)

        stats = QGridLayout()
        stats.setSpacing(10)
        self.stats = {}
        for i, key in enumerate(("duration", "energy", "mean_power", "peak_power", "charge", "voltage")):
            value = label(role="stat-value")
            frame, _ = card(label(t(f"report.{key}"), "stat-label"), value)
            stats.addWidget(frame, i // 3, i % 3)
            self.stats[key] = value
        layout.addLayout(stats)

        self.tabs = QTabWidget()
        self.charts = [Chart("energy"), Chart("cumulative"), Chart("power")]
        for chart, key in zip(self.charts, ("tab_energy", "tab_cumulative", "tab_power")):
            self.tabs.addTab(chart, t(f"report.{key}"))
        self.tabs.currentChanged.connect(self._draw_current)

        data_tab = QWidget()
        data_layout = QVBoxLayout(data_tab)
        self.filter = QLineEdit(placeholderText=t("report.filter"))
        self.filter.setClearButtonEnabled(True)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setFilterKeyColumn(-1)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy.setSortRole(Qt.ItemDataRole.UserRole)
        filter_timer = QTimer(self, singleShot=True, interval=200)
        filter_timer.timeout.connect(lambda: self.proxy.setFilterFixedString(self.filter.text()))
        self.filter.textChanged.connect(filter_timer.start)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
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

    def load(self, csv_path, theme):
        """Load a CSV; returns False (after telling the user) if it cannot be read."""
        try:
            rows = metrics.read_csv(csv_path)
            if rows and "Energy (J)" not in rows[0]:
                raise ValueError("not a PowDroid CSV")
        except (OSError, ValueError, KeyError) as e:
            QMessageBox.warning(self, t("report.title"), t("report.load_error", error=e))
            return False
        self.csv_path = Path(csv_path)
        self.subtitle.setFullText(str(self.csv_path) + ("" if rows else f" — {t('report.empty')}"))
        for key, text in metrics.summary_items(metrics.summarize(rows)):
            self.stats[key].setText(text)

        self.proxy.setSourceModel(RowsModel(rows, self))
        self.table.resizeColumnsToContents()
        self.filter.clear()
        self.series = Series(rows)
        self.set_theme(theme)
        return True

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
        if self.csv_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.csv_path.parent)))

    def _export_html(self):
        if not self.csv_path:
            return
        try:
            path = html_report.write(self.csv_path)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, t("report.export_html"), str(e))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        self.subtitle.setFullText(t("report.exported", path=path))
