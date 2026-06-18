"""Offscreen tests for Run All / Run Single multi-engine behavior.
Run with: QT_QPA_PLATFORM=offscreen pytest -q
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from plc_test_suite.sim_tab import SimulationTab


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _FakePLC:
    connected = True

    def read_tags(self, names):
        return {}

    def write_tags(self, pairs):
        return True


def _make_tab():
    tab = SimulationTab(_FakePLC())
    # The tab constructs one blank module; add a second so "Run all" has >1
    tab._new_module()
    # Keep intervals short so stop()/join is quick in tests
    for m in tab._modules:
        m.interval_seconds = 0.05
    return tab


def test_run_single_starts_one_engine(app):
    tab = _make_tab()
    tab.run_all_cb.setChecked(False)
    tab._start_module()
    assert len(tab._engines) == 1
    assert not tab._qualify
    tab._stop_module()
    assert tab._engines == []
    assert tab.start_btn.isEnabled()


def test_run_all_starts_all_engines(app):
    tab = _make_tab()
    tab.run_all_cb.setChecked(True)
    tab._start_module()
    assert len(tab._engines) == 2
    assert tab._qualify  # >1 module → channels get module-name prefixes
    tab._stop_module()
    assert tab._engines == []


def test_trend_channels_prefixed_when_multiple(app):
    tab = _make_tab()
    # Give each module a distinct alias via its input tags
    from plc_test_suite.sim_module import TagEntry
    tab._modules[0].input_tags = [TagEntry("A.inp", "level")]
    tab._modules[1].input_tags = [TagEntry("B.inp", "level")]
    # Reflect the selected module in the editor so _save_current_to_list (called
    # inside get_trend_channels) doesn't overwrite it with stale empty state.
    tab.editor.load_module(tab._modules[tab._current_index])

    tab.run_all_cb.setChecked(False)
    assert tab.get_trend_channels() == tab.editor.get_alias_names()  # bare

    tab.run_all_cb.setChecked(True)
    channels = tab.get_trend_channels()
    assert any(c.endswith(": level") for c in channels)
    # Same alias from two modules stays distinct via the prefix
    assert len([c for c in channels if c.endswith(": level")]) == 2


def test_active_simulation_label(app):
    tab = _make_tab()
    seen = []
    tab.active_simulation_changed.connect(seen.append)

    tab.run_all_cb.setChecked(False)
    tab._start_module()
    assert seen[-1] == tab._engines[0].module.name  # single module name
    tab._stop_module()
    assert seen[-1] == ""                            # cleared on stop

    tab.run_all_cb.setChecked(True)
    tab._start_module()
    assert seen[-1] == "All Modules"                 # several running
    tab._stop_module()
    assert seen[-1] == ""


def test_script_stop_leaves_others_running_until_last(app):
    tab = _make_tab()

    class _FakeModule:
        name = "M"

    class _FakeEngine:
        is_running = True
        module = _FakeModule()

        def stop(self):
            pass

    e1, e2 = _FakeEngine(), _FakeEngine()
    tab._engines = [e1, e2]
    tab._stopping = False
    tab.start_btn.setEnabled(False)
    tab.stop_btn.setEnabled(True)

    # One module's script calls stop() → that engine finishes
    tab._on_engine_finished(e1)
    assert tab._engines == [e2]
    assert tab.stop_btn.isEnabled()      # still running
    assert not tab.start_btn.isEnabled()

    # Last engine finishes → UI resets
    tab._on_engine_finished(e2)
    assert tab._engines == []
    assert tab.start_btn.isEnabled()
    assert not tab.stop_btn.isEnabled()
