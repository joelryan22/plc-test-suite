"""
Trend Tab - live plotting of simulation aliases.

Works in tandem with the Simulation Modules tab: the running SimEngine emits a
sample each cycle (via SimulationTab.sample_logged), which this tab buffers and plots
with pyqtgraph. Channels (input/output/user-input aliases) can be toggled and
recolored; the trend stays viewable after a run stops and can be saved to / loaded
from a reloadable CSV.
"""

import csv
import logging

import pyqtgraph as pg
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox,
    QScrollArea, QColorDialog, QFileDialog, QMessageBox, QFrame
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor

logger = logging.getLogger(__name__)

# Default color palette assigned to new channels (VS Code-ish, readable on dark)
_PALETTE = [
    "#E06C75", "#61AFEF", "#98C379", "#E5C07B", "#C678DD", "#56B6C2",
    "#D19A66", "#BE5046", "#528BFF", "#7F848E",
]

# Match the app's dark theme
pg.setConfigOption("background", "#1E1E1E")
pg.setConfigOption("foreground", "#D4D4D4")
pg.setConfigOptions(antialias=True)


class TrendTab(QWidget):
    """Live trend plot driven by the simulation engine's per-cycle samples."""

    def __init__(self, sim_tab, parent=None):
        super().__init__(parent)
        self._sim_tab = sim_tab

        # alias -> {"color": "#RRGGBB", "checked": bool}
        self._series: dict = {}
        # alias -> ([times], [values])
        self._data: dict = {}
        # alias -> pyqtgraph PlotDataItem
        self._curves: dict = {}
        # alias -> (QCheckBox, color QPushButton)
        self._rows: dict = {}
        self._running = False
        self._palette_index = 0

        self._init_ui()

        # React to the simulation lifecycle
        sim_tab.simulation_started.connect(self._on_started)
        sim_tab.simulation_stopped.connect(self._on_stopped)
        sim_tab.sample_logged.connect(self._on_sample)
        # Show channels as soon as their aliases are added (no run required)
        sim_tab.editor.aliases_changed.connect(self._on_aliases_changed)

        # Redraw timer (active only while recording, to decouple draw rate from
        # the sample rate)
        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._redraw)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _init_ui(self):
        outer = QHBoxLayout(self)

        # ── Left: channel controls ──────────────────────────────────
        left = QWidget()
        left.setMaximumWidth(240)
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Trend Channels"))

        self._rows_container = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(self._rows_container)
        scroll.setWidgetResizable(True)
        left_layout.addWidget(scroll, 1)

        self._empty_hint = QLabel(
            "Add input/output tags or user inputs on the Simulation Modules tab, "
            "then start a simulation.")
        self._empty_hint.setWordWrap(True)
        self._empty_hint.setStyleSheet("color: #858585;")
        left_layout.addWidget(self._empty_hint)

        btn_row = QHBoxLayout()
        self._save_btn = QPushButton("Save Trend…")
        self._save_btn.clicked.connect(self._save)
        self._load_btn = QPushButton("Load Trend…")
        self._load_btn.clicked.connect(self._load)
        btn_row.addWidget(self._save_btn)
        btn_row.addWidget(self._load_btn)
        left_layout.addLayout(btn_row)

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear)
        left_layout.addWidget(clear_btn)

        self._status = QLabel("Idle")
        self._status.setStyleSheet("color: #858585;")
        left_layout.addWidget(self._status)

        outer.addWidget(left)

        # ── Right: plot ─────────────────────────────────────────────
        self._plot = pg.PlotWidget()
        self._plot.addLegend()
        self._plot.showGrid(x=True, y=True, alpha=0.3)
        self._plot.setLabel("bottom", "Time (s)")
        self._plot.setLabel("left", "Value")
        outer.addWidget(self._plot, 1)

    def showEvent(self, event):
        """Refresh the channel list from the current module when shown."""
        super().showEvent(event)
        if not self._running:
            self._sync_aliases(self._sim_tab.get_alias_names())

    def _on_aliases_changed(self):
        """An alias was added/removed on the Simulation tab — resync the channel
        list immediately so it appears without needing a run."""
        if not self._running:
            self._sync_aliases(self._sim_tab.get_alias_names())

    # ------------------------------------------------------------------
    # Channel list management
    # ------------------------------------------------------------------

    def _next_color(self) -> str:
        color = _PALETTE[self._palette_index % len(_PALETTE)]
        self._palette_index += 1
        return color

    def _sync_aliases(self, names):
        """Ensure a row exists for each alias (plus any alias that holds data),
        preserving existing color/checked state."""
        names = list(dict.fromkeys(list(names) + list(self._data.keys())))
        for alias in names:
            if alias not in self._series:
                self._series[alias] = {"color": self._next_color(), "checked": False}
        self._rebuild_rows(names)

    def _rebuild_rows(self, aliases):
        # Clear existing rows (keep the trailing stretch)
        while self._rows_layout.count() > 1:
            item = self._rows_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._rows = {}

        for alias in aliases:
            info = self._series[alias]
            row = QFrame()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)

            cb = QCheckBox(alias)
            cb.setChecked(info["checked"])
            cb.toggled.connect(lambda checked, a=alias: self._on_toggle(a, checked))
            row_layout.addWidget(cb, 1)

            color_btn = QPushButton()
            color_btn.setFixedWidth(28)
            self._style_color_btn(color_btn, info["color"])
            color_btn.clicked.connect(lambda _, a=alias: self._pick_color(a))
            row_layout.addWidget(color_btn)

            self._rows_layout.insertWidget(self._rows_layout.count() - 1, row)
            self._rows[alias] = (cb, color_btn)

        self._empty_hint.setVisible(not aliases)

    def _style_color_btn(self, btn, color):
        btn.setStyleSheet(f"background-color: {color}; border: 1px solid #3C3C3C;")

    def _on_toggle(self, alias, checked):
        self._series[alias]["checked"] = checked
        self._update_curve(alias)

    def _pick_color(self, alias):
        current = QColor(self._series[alias]["color"])
        chosen = QColorDialog.getColor(current, self, f"Color for {alias}")
        if chosen.isValid():
            self._series[alias]["color"] = chosen.name()
            _cb, btn = self._rows[alias]
            self._style_color_btn(btn, chosen.name())
            # Recreate the curve so the legend/pen pick up the new color
            self._remove_curve(alias)
            self._update_curve(alias)

    # ------------------------------------------------------------------
    # Simulation lifecycle
    # ------------------------------------------------------------------

    def _on_started(self, module):
        # Overwrite the previous trend
        self._clear_plot()
        self._data = {}
        names = [t.alias for t in module.input_tags]
        names += [t.alias for t in module.output_tags]
        names += [u.alias for u in module.user_inputs]
        self._sync_aliases(names)
        self._running = True
        self._timer.start()
        self._status.setText("● Recording")
        self._status.setStyleSheet("color: #98C379;")

    def _on_sample(self, t, values):
        for alias, val in values.items():
            buf = self._data.setdefault(alias, ([], []))
            buf[0].append(t)
            buf[1].append(val)

    def _on_stopped(self):
        self._running = False
        self._timer.stop()
        self._redraw()
        n = max((len(v[0]) for v in self._data.values()), default=0)
        self._status.setText(f"Stopped — {n} samples")
        self._status.setStyleSheet("color: #858585;")

    # ------------------------------------------------------------------
    # Plotting
    # ------------------------------------------------------------------

    def _update_curve(self, alias):
        info = self._series.get(alias)
        if info and info["checked"] and alias in self._data:
            curve = self._curves.get(alias)
            if curve is None:
                curve = self._plot.plot(
                    [], [], name=alias,
                    pen=pg.mkPen(info["color"], width=2))
                self._curves[alias] = curve
            times, values = self._data[alias]
            curve.setData(times, values)
        else:
            self._remove_curve(alias)

    def _remove_curve(self, alias):
        curve = self._curves.pop(alias, None)
        if curve is not None:
            self._plot.removeItem(curve)

    def _redraw(self):
        for alias in list(self._series.keys()):
            self._update_curve(alias)

    def _clear_plot(self):
        for alias in list(self._curves.keys()):
            self._remove_curve(alias)

    def _clear(self):
        if self._running:
            QMessageBox.information(self, "Clear Trend",
                                    "Stop the simulation before clearing.")
            return
        self._clear_plot()
        self._data = {}
        self._status.setText("Cleared")
        self._status.setStyleSheet("color: #858585;")

    # ------------------------------------------------------------------
    # Save / load (reloadable CSV)
    # ------------------------------------------------------------------

    def _save(self):
        if not self._data:
            QMessageBox.information(self, "Save Trend", "No trend data to save.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Trend", "trend.csv", "CSV (*.csv)")
        if not path:
            return

        aliases = list(self._data.keys())
        # Master sorted set of all sample times
        all_times = sorted({t for a in aliases for t in self._data[a][0]})
        lookup = {a: dict(zip(self._data[a][0], self._data[a][1])) for a in aliases}

        try:
            with open(path, "w", newline="") as f:
                meta = "; ".join(f"{a}={self._series[a]['color']}" for a in aliases)
                f.write("# plc-test-suite trend v1\n")
                f.write(f"# series: {meta}\n")
                writer = csv.writer(f)
                writer.writerow(["time"] + aliases)
                for t in all_times:
                    row = [f"{t:.3f}"]
                    for a in aliases:
                        v = lookup[a].get(t)
                        row.append("" if v is None else f"{v:g}")
                    writer.writerow(row)
            self._status.setText(f"Saved {len(all_times)} samples")
            self._status.setStyleSheet("color: #858585;")
        except OSError as e:
            QMessageBox.critical(self, "Save Error", f"Could not save:\n{e}")

    def _load(self):
        if self._running:
            QMessageBox.information(self, "Load Trend",
                                    "Stop the simulation before loading a trend.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Trend", "", "CSV (*.csv);;All (*)")
        if not path:
            return
        try:
            colors = {}
            data_lines = []
            with open(path, "r", newline="") as f:
                for line in f:
                    if line.startswith("# series:"):
                        for part in line[len("# series:"):].strip().split(";"):
                            if "=" in part:
                                a, c = part.split("=", 1)
                                colors[a.strip()] = c.strip()
                    elif line.startswith("#"):
                        continue
                    else:
                        data_lines.append(line)

            reader = csv.reader(data_lines)
            header = next(reader, None)
            if not header or header[0] != "time":
                raise ValueError("Not a recognized trend CSV (missing time header).")
            aliases = header[1:]

            self._clear_plot()
            self._data = {a: ([], []) for a in aliases}
            for row in reader:
                if not row:
                    continue
                t = float(row[0])
                for i, a in enumerate(aliases, start=1):
                    if i < len(row) and row[i] != "":
                        self._data[a][0].append(t)
                        self._data[a][1].append(float(row[i]))

            # Reset series with loaded colors, all checked on by default
            self._series = {}
            for a in aliases:
                self._series[a] = {
                    "color": colors.get(a, self._next_color()),
                    "checked": True,
                }
            self._rebuild_rows(aliases)
            self._redraw()
            self._status.setText(f"Loaded {len(aliases)} channels")
            self._status.setStyleSheet("color: #858585;")
        except (OSError, ValueError, StopIteration) as e:
            QMessageBox.critical(self, "Load Error", f"Could not load trend:\n{e}")
