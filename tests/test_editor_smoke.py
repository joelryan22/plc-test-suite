"""Offscreen smoke tests for the QScintilla-based script editor and the
script namespace whitelist. Run with: QT_QPA_PLATFORM=offscreen pytest -q

These don't need a display or a PLC.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.Qsci import QsciScintilla


@pytest.fixture(scope="module")
def app():
    app = QApplication.instance() or QApplication([])
    yield app


def test_editor_is_qscintilla_and_roundtrips(app):
    from plc_test_suite.sim_tab import ModuleEditorWidget
    w = ModuleEditorWidget()
    assert isinstance(w.init_editor, QsciScintilla)
    assert isinstance(w.loop_editor, QsciScintilla)
    # QPlainTextEdit-style shims still work
    w.init_editor.setPlainText("x = 1\n")
    assert w.init_editor.toPlainText() == "x = 1\n"
    # set_known_names accepts aliases without error
    w.init_editor.set_known_names(["tank_level", "valve_cmd"])
    assert "tank_level" in w.init_editor._known_names


def test_syntax_check_is_compile_only(app):
    from plc_test_suite.sim_tab import ScriptEditor
    ed = ScriptEditor()

    # Real syntax error → reported with a line number
    ed.setPlainText("def (:\n")
    ok, msg, line = ed.check_syntax()
    assert ok is False and line >= 1 and msg

    # Valid code → ok
    ed.setPlainText("y = 1 + 2\n")
    ok, _, _ = ed.check_syntax()
    assert ok is True

    # Undefined name must NOT be flagged (aliases are injected at runtime)
    ed.setPlainText("y = tank_level + 1\n")
    ok, _, _ = ed.check_syntax()
    assert ok is True


def test_namespace_includes_whitelisted_modules():
    import types
    from plc_test_suite.sim_module import SimModule, SimEngine

    class _DummyPLC:
        def read_tags(self, names):
            return {}

    engine = SimEngine(SimModule(), _DummyPLC())
    ns = engine._build_namespace()
    for mod in ("math", "time", "random"):
        assert isinstance(ns[mod], types.ModuleType)
