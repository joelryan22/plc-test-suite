"""Offscreen smoke tests for the Trend tab and the engine sample hook.
Run with: QT_QPA_PLATFORM=offscreen pytest -q
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication, QFileDialog
from PyQt6.QtCore import QObject, pyqtSignal

from plc_test_suite.sim_module import SimModule, SimEngine, TagEntry
from plc_test_suite.user_inputs import UserInput


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _DummyPLC:
    def read_tags(self, names):
        return {}

    def write_tags(self, pairs):
        return True


class _SimTabStub(QObject):
    """Minimal stand-in for SimulationTab exposing the signals TrendTab uses."""
    simulation_started = pyqtSignal(object)
    simulation_stopped = pyqtSignal()
    sample_logged = pyqtSignal(float, dict)

    def get_alias_names(self):
        return []


def _module():
    return SimModule(
        input_tags=[TagEntry("Valve.out_cv", "valve_cmd")],
        output_tags=[TagEntry("LT.inp_sim", "tank_level")],
        user_inputs=[UserInput(alias="manual", input_type="toggle",
                               label="Manual", default_value=False)],
    )


def test_engine_sample_values_numeric_only():
    engine = SimEngine(_module(), _DummyPLC())
    assert engine.trendable_aliases() == ["valve_cmd", "tank_level", "manual"]
    engine._script_ns = {"valve_cmd": 12.5, "tank_level": 3, "manual": True,
                         "note": "skip-me"}
    sample = engine._sample_values()
    assert sample == {"valve_cmd": 12.5, "tank_level": 3.0, "manual": 1.0}
    # non-numeric values are excluded
    assert "note" not in sample


def test_engine_emits_sample_via_callback():
    engine = SimEngine(_module(), _DummyPLC())
    engine._script_ns = {"valve_cmd": 1.0, "tank_level": 2.0, "manual": False}
    got = []
    engine.on_sample = lambda t, s: got.append((t, s))
    engine._emit_sample()
    assert len(got) == 1
    _t, s = got[0]
    assert s["tank_level"] == 2.0


def test_trend_buffers_and_round_trips_csv(app, tmp_path, monkeypatch):
    from plc_test_suite.trend_tab import TrendTab
    stub = _SimTabStub()
    trend = TrendTab(stub)

    # Start a run and feed two samples
    mod = _module()
    stub.simulation_started.emit(mod)
    stub.sample_logged.emit(0.0, {"valve_cmd": 0.0, "tank_level": 0.0})
    stub.sample_logged.emit(1.0, {"valve_cmd": 50.0, "tank_level": 2.0})
    stub.simulation_stopped.emit()

    assert trend._data["tank_level"] == ([0.0, 1.0], [0.0, 2.0])

    # Save, then load into a fresh tab and confirm data + colors round-trip
    csv_path = str(tmp_path / "trend.csv")
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (csv_path, "CSV")))
    trend._save()
    assert os.path.exists(csv_path)

    trend2 = TrendTab(_SimTabStub())
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (csv_path, "CSV")))
    trend2._load()
    assert trend2._data["tank_level"][1] == [0.0, 2.0]
    assert "tank_level" in trend2._series
    assert trend2._series["tank_level"]["color"].startswith("#")


def test_trend_overwrites_on_restart(app):
    from plc_test_suite.trend_tab import TrendTab
    stub = _SimTabStub()
    trend = TrendTab(stub)
    mod = _module()

    stub.simulation_started.emit(mod)
    stub.sample_logged.emit(0.0, {"tank_level": 5.0})
    assert trend._data["tank_level"][1] == [5.0]

    # Starting again wipes the previous trend
    stub.simulation_started.emit(mod)
    assert trend._data.get("tank_level", ([], []))[1] == []
