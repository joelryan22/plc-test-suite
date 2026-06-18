"""
Simulation Module Editor - GUI widget for creating and running simulation modules
"""

import json
import keyword
import logging
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QSplitter, QGroupBox, QListWidget, QListWidgetItem,
    QFileDialog, QMessageBox, QDoubleSpinBox, QTextEdit,
    QTabWidget, QFrame, QComboBox, QToolTip
)
from PyQt6.QtCore import Qt, QTimer, QPoint, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.Qsci import QsciScintilla, QsciLexerPython, QsciAPIs, QsciStyle

from plc_test_suite.sim_module import SimModule, SimEngine, TagEntry

from plc_test_suite.user_inputs import UserInput, UserInputsPanel

logger = logging.getLogger(__name__)


# Stdlib modules pre-injected into the script namespace
# (kept in sync with SimEngine._build_namespace in sim_module.py)
WHITELIST_MODULES = ["math", "time", "random"]

# Closing character inserted when the opener is typed
_AUTO_CLOSE = {"(": ")", "[": "]", "{": "}", '"': '"', "'": "'"}


class ScriptEditor(QsciScintilla):
    """Python code editor backed by QScintilla.

    Features: syntax highlighting, line-number gutter, auto-indent, brace
    matching, bracket auto-close, alias-aware autocompletion (QsciAPIs),
    Jedi-powered hover help, and compile-only syntax checking.

    The QPlainTextEdit-style ``setPlainText``/``toPlainText``/
    ``setPlaceholderText`` methods are shimmed so existing call sites keep
    working unchanged.
    """

    # (ok, message, line_number) — emitted after each live syntax check
    syntax_status = pyqtSignal(bool, str, int)

    _MARKER_ERROR = 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self._known_names: list[str] = []

        # Jedi is optional — never let it break the editor
        try:
            import jedi
            self._jedi = jedi
        except Exception:  # pragma: no cover - defensive
            self._jedi = None

        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)

        # --- Lexer (syntax highlighting) ---
        self._lexer = QsciLexerPython(self)
        self._lexer.setDefaultFont(font)
        self._lexer.setFont(font)
        self._apply_theme()
        self.setLexer(self._lexer)

        # --- Autocompletion (QsciAPIs) ---
        self._apis = QsciAPIs(self._lexer)
        self._base_words = self._compute_base_words()
        self._rebuild_apis()
        self.setAutoCompletionSource(QsciScintilla.AutoCompletionSource.AcsAPIs)
        self.setAutoCompletionThreshold(2)
        self.setAutoCompletionCaseSensitivity(False)
        self.setAutoCompletionReplaceWord(True)

        # --- Editor behaviour / appearance ---
        self.setUtf8(True)
        self.setIndentationsUseTabs(False)
        self.setTabWidth(4)
        self.setAutoIndent(True)
        self.setIndentationGuides(True)
        self.setBraceMatching(QsciScintilla.BraceMatch.SloppyBraceMatch)
        self.setCaretLineVisible(True)
        self.setCaretLineBackgroundColor(QColor("#2A2A2A"))
        self.setCaretForegroundColor(QColor("#D4D4D4"))
        self.setMinimumHeight(200)

        # Line-number margin (0) and symbol margin (1) for the error marker
        self.setMarginType(0, QsciScintilla.MarginType.NumberMargin)
        self.setMarginWidth(0, "0000")
        self.setMarginsBackgroundColor(QColor("#1E1E1E"))
        self.setMarginsForegroundColor(QColor("#858585"))
        self.setMarginType(1, QsciScintilla.MarginType.SymbolMargin)
        self.setMarginWidth(1, 14)
        self.setMarginSensitivity(1, False)
        self.markerDefine(QsciScintilla.MarkerSymbol.RightTriangle, self._MARKER_ERROR)
        self.setMarkerBackgroundColor(QColor("#FF6B6B"), self._MARKER_ERROR)
        self.setMarkerForegroundColor(QColor("#FF6B6B"), self._MARKER_ERROR)
        self.setMarginMarkerMask(1, 1 << self._MARKER_ERROR)

        # Inline error annotation
        self.setAnnotationDisplay(QsciScintilla.AnnotationDisplay.AnnotationBoxed)
        try:
            self._err_style = QsciStyle(
                -1, "syntax_error", QColor("#FF6B6B"), QColor("#3A1E1E"), font)
        except Exception:  # pragma: no cover - defensive
            self._err_style = None

        # --- Hover help (Jedi) ---
        self.SendScintilla(QsciScintilla.SCI_SETMOUSEDWELLTIME, 500)
        self.SCN_DWELLSTART.connect(self._on_dwell_start)
        self.SCN_DWELLEND.connect(self._on_dwell_end)

        # --- Live, debounced syntax check ---
        self._syntax_timer = QTimer(self)
        self._syntax_timer.setSingleShot(True)
        self._syntax_timer.setInterval(400)
        self._syntax_timer.timeout.connect(self._run_live_syntax_check)
        self.textChanged.connect(self._syntax_timer.start)

    # ------------------------------------------------------------------
    # QPlainTextEdit compatibility shims
    # ------------------------------------------------------------------

    def setPlainText(self, text: str):
        self.setText(text or "")

    def toPlainText(self) -> str:
        return self.text()

    def setPlaceholderText(self, text: str):
        # QScintilla has no placeholder; the default script comment templates
        # act as the on-screen hint. Intentionally a no-op.
        pass

    # ------------------------------------------------------------------
    # Theming & autocompletion data
    # ------------------------------------------------------------------

    def _apply_theme(self):
        """Colour the Python lexer to match the previous VS Code-ish scheme."""
        lex = self._lexer
        paper = QColor("#1E1E1E")
        default_fg = QColor("#D4D4D4")
        lex.setDefaultPaper(paper)
        lex.setDefaultColor(default_fg)
        for style in range(0, 16):
            lex.setPaper(paper, style)
            lex.setColor(default_fg, style)
        colors = {
            QsciLexerPython.Keyword: "#569CD6",
            QsciLexerPython.ClassName: "#4EC9B0",
            QsciLexerPython.FunctionMethodName: "#4EC9B0",
            QsciLexerPython.Comment: "#6A9955",
            QsciLexerPython.CommentBlock: "#6A9955",
            QsciLexerPython.Number: "#B5CEA8",
            QsciLexerPython.DoubleQuotedString: "#CE9178",
            QsciLexerPython.SingleQuotedString: "#CE9178",
            QsciLexerPython.TripleSingleQuotedString: "#CE9178",
            QsciLexerPython.TripleDoubleQuotedString: "#CE9178",
            QsciLexerPython.UnclosedString: "#CE9178",
            QsciLexerPython.Decorator: "#DCDCAA",
        }
        for style, hexc in colors.items():
            lex.setColor(QColor(hexc), style)

    def _compute_base_words(self) -> list[str]:
        """Always-available completion words: keywords, builtins and the
        whitelisted modules with their public members (dotted)."""
        words = list(keyword.kwlist)
        words += [
            "print", "len", "range", "int", "float", "str", "bool", "abs",
            "min", "max", "round", "type", "list", "dict", "set", "tuple",
            "sum", "enumerate", "zip", "sorted", "reversed", "any", "all",
            "True", "False", "None",
            # Injected into the script namespace by SimEngine
            "stop", "stop_simulation",
        ]
        import importlib
        for mod_name in WHITELIST_MODULES:
            words.append(mod_name)
            try:
                mod = importlib.import_module(mod_name)
                for member in dir(mod):
                    if not member.startswith("_"):
                        words.append(f"{mod_name}.{member}")
            except Exception:  # pragma: no cover - defensive
                pass
        return words

    def _rebuild_apis(self):
        """Repopulate the autocompletion API with base words + known aliases."""
        self._apis.clear()
        for word in self._base_words + self._known_names:
            self._apis.add(word)
        self._apis.prepare()

    def set_known_names(self, names):
        """Update the alias names available to autocompletion (called by the
        editor host whenever input/output/user-input aliases change)."""
        self._known_names = [n for n in names if n]
        self._rebuild_apis()

    # ------------------------------------------------------------------
    # Bracket / quote auto-close
    # ------------------------------------------------------------------

    def keyPressEvent(self, event):
        ch = event.text()
        if ch in _AUTO_CLOSE and not self.hasSelectedText():
            super().keyPressEvent(event)
            self.insert(_AUTO_CLOSE[ch])
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Syntax checking (compile-only — never flags undefined names)
    # ------------------------------------------------------------------

    def check_syntax(self):
        """Return (ok, message, line_number). line_number is 1-based, -1 if ok."""
        try:
            compile(self.text(), "<script>", "exec")
            return True, "", -1
        except SyntaxError as e:
            return False, e.msg, (e.lineno or 1)

    def _run_live_syntax_check(self):
        self.markerDeleteAll(self._MARKER_ERROR)
        self.clearAnnotations()
        ok, msg, lineno = self.check_syntax()
        if not ok:
            line0 = max(0, lineno - 1)
            self.markerAdd(line0, self._MARKER_ERROR)
            if self._err_style is not None:
                self.annotate(line0, f"SyntaxError: {msg}", self._err_style)
        self.syntax_status.emit(ok, msg, lineno)

    # ------------------------------------------------------------------
    # Jedi hover help
    # ------------------------------------------------------------------

    def _jedi_preamble(self) -> str:
        """Source prepended before the editor text so Jedi resolves injected
        imports and alias names. Returns the preamble text (newline-terminated)."""
        lines = [f"import {', '.join(WHITELIST_MODULES)}"]
        lines += [f"{name} = 0" for name in self._known_names]
        return "\n".join(lines) + "\n"

    def _on_dwell_start(self, position, x, y):
        if self._jedi is None:
            return
        try:
            line, index = self.lineIndexFromPosition(position)
            preamble = self._jedi_preamble()
            offset = preamble.count("\n")
            source = preamble + self.text()
            script = self._jedi.Script(code=source)
            # Jedi lines are 1-based; editor line is 0-based
            jline = line + offset + 1
            help_text = ""
            sigs = script.get_signatures(jline, index)
            if sigs:
                help_text = sigs[0].to_string()
            else:
                names = script.help(jline, index)
                if names:
                    name = names[0]
                    doc = (name.docstring() or "").strip()
                    if doc:
                        help_text = doc.split("\n\n")[0]
            if help_text:
                QToolTip.showText(self.mapToGlobal(QPoint(x, y)), help_text, self)
        except Exception:  # pragma: no cover - hover must never crash editing
            pass

    def _on_dwell_end(self, position, x, y):
        QToolTip.hideText()


class TagTableWidget(QWidget):
    """
    Reusable widget for a table of (tag, alias) pairs.
    Used for both input_tags and output_tags.
    """

    # Emitted whenever rows (and therefore aliases) change
    tags_changed = pyqtSignal()

    def __init__(self, title: str, alias_hint: str = "e.g. tank_level", parent=None):
        super().__init__(parent)
        self.alias_hint = alias_hint
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Add row controls
        add_layout = QHBoxLayout()
        self.tag_input = QLineEdit()
        self.tag_input.setPlaceholderText("Full tag name  e.g. LT_Tank_001.inp_sim")
        self.alias_input = QLineEdit()
        self.alias_input.setPlaceholderText(alias_hint)
        self.alias_input.setMaximumWidth(160)
        add_btn = QPushButton("Add")
        add_btn.setMaximumWidth(60)
        add_btn.clicked.connect(self._add_row)
        add_layout.addWidget(QLabel("Tag:"))
        add_layout.addWidget(self.tag_input)
        add_layout.addWidget(QLabel("Alias:"))
        add_layout.addWidget(self.alias_input)
        add_layout.addWidget(add_btn)
        layout.addLayout(add_layout)

        # Table
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Tag Name", "Alias", ""])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(2, 60)
        self.table.setMaximumHeight(160)
        layout.addWidget(self.table)

    def _add_row(self):
        tag = self.tag_input.text().strip()
        alias = self.alias_input.text().strip()
        if not tag or not alias:
            return
        # Validate alias - no spaces or dots
        if " " in alias or "." in alias:
            QMessageBox.warning(self, "Invalid Alias",
                                "Alias cannot contain spaces or periods.")
            return
        # Check for duplicate alias
        for row in range(self.table.rowCount()):
            if self.table.item(row, 1) and self.table.item(row, 1).text() == alias:
                QMessageBox.warning(self, "Duplicate Alias",
                                    f"Alias '{alias}' is already used.")
                return
        self._insert_row(tag, alias)
        self.tag_input.clear()
        self.alias_input.clear()

    def _insert_row(self, tag: str, alias: str):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(tag))
        self.table.setItem(row, 1, QTableWidgetItem(alias))
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(lambda: self._remove_row(remove_btn))
        self.table.setCellWidget(row, 2, remove_btn)
        self.tags_changed.emit()

    def _remove_row(self, remove_btn: QPushButton):
        self.table.removeRow(self.table.indexAt(remove_btn.pos()).row())
        self.tags_changed.emit()

    def get_entries(self) -> list[TagEntry]:
        entries = []
        for row in range(self.table.rowCount()):
            tag_item = self.table.item(row, 0)
            alias_item = self.table.item(row, 1)
            if tag_item and alias_item:
                entries.append(TagEntry(tag=tag_item.text(), alias=alias_item.text()))
        return entries

    def load_entries(self, entries: list[TagEntry]):
        self.table.setRowCount(0)
        for entry in entries:
            self._insert_row(entry.tag, entry.alias)


class SimTagListWidget(QWidget):
    """Simple list widget for sim_tags (no alias needed)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        add_layout = QHBoxLayout()
        self.tag_input = QLineEdit()
        self.tag_input.setPlaceholderText("e.g. Valve_001.cfg_sim")
        add_btn = QPushButton("Add")
        add_btn.setMaximumWidth(60)
        add_btn.clicked.connect(self._add_tag)
        add_layout.addWidget(QLabel("Tag:"))
        add_layout.addWidget(self.tag_input)
        add_layout.addWidget(add_btn)
        layout.addLayout(add_layout)

        self.list_widget = QListWidget()
        self.list_widget.setMaximumHeight(120)
        layout.addWidget(self.list_widget)

        remove_btn = QPushButton("Remove Selected")
        remove_btn.clicked.connect(self._remove_selected)
        layout.addWidget(remove_btn)

    def _add_tag(self):
        tag = self.tag_input.text().strip()
        if tag:
            self.list_widget.addItem(tag)
            self.tag_input.clear()

    def _remove_selected(self):
        for item in self.list_widget.selectedItems():
            self.list_widget.takeItem(self.list_widget.row(item))

    def get_tags(self) -> list[str]:
        return [self.list_widget.item(i).text()
                for i in range(self.list_widget.count())]

    def load_tags(self, tags: list[str]):
        self.list_widget.clear()
        for tag in tags:
            self.list_widget.addItem(tag)


class ModuleEditorWidget(QWidget):
    """
    Full editor for a single SimModule.
    Emits module_changed when any field is edited.
    """
    module_changed = pyqtSignal()
    # Emitted whenever the set of alias names changes (tag tables, user inputs,
    # or a module load) so other views (e.g. the Trend tab) can resync live.
    aliases_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._module: Optional[SimModule] = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Name / description / interval row
        meta_layout = QHBoxLayout()
        meta_layout.addWidget(QLabel("Name:"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Module name")
        meta_layout.addWidget(self.name_edit)

        meta_layout.addWidget(QLabel("Description:"))
        self.desc_edit = QLineEdit()
        self.desc_edit.setPlaceholderText("What does this module test?")
        meta_layout.addWidget(self.desc_edit)

        meta_layout.addWidget(QLabel("Interval (s):"))
        self.interval_spin = QDoubleSpinBox()
        self.interval_spin.setRange(0.1, 60.0)
        self.interval_spin.setSingleStep(0.5)
        self.interval_spin.setValue(1.0)
        self.interval_spin.setMaximumWidth(80)
        meta_layout.addWidget(self.interval_spin)
        layout.addLayout(meta_layout)

        # Tag configuration split into three groups
        tags_splitter = QSplitter(Qt.Orientation.Horizontal)

        sim_group = QGroupBox("Simulation Tags  (set True on start, False on stop)")
        sg_layout = QVBoxLayout(sim_group)
        self.sim_tags_widget = SimTagListWidget()
        sg_layout.addWidget(self.sim_tags_widget)
        tags_splitter.addWidget(sim_group)

        in_group = QGroupBox("Input Tags  (read only)")
        ig_layout = QVBoxLayout(in_group)
        self.input_tags_widget = TagTableWidget("Input Tags", "e.g. valve_cmd")
        ig_layout.addWidget(self.input_tags_widget)
        tags_splitter.addWidget(in_group)

        out_group = QGroupBox("Output Tags  (written by simulation)")
        og_layout = QVBoxLayout(out_group)
        self.output_tags_widget = TagTableWidget("Output Tags", "e.g. tank_level")
        og_layout.addWidget(self.output_tags_widget)
        tags_splitter.addWidget(out_group)

        layout.addWidget(tags_splitter)

        # Script editors
        script_tabs = QTabWidget()

        init_widget = QWidget()
        init_layout = QVBoxLayout(init_widget)
        init_layout.addWidget(QLabel(
            "Init Script — runs once at startup. Read inputs, set initial output values."))
        self.init_editor = ScriptEditor()
        self.init_editor.setMinimumHeight(200)  # Add this line
        self.init_editor.setPlaceholderText(
            "# Example:\n# tank_level = 0.0\n# flow = 0.0\n")
        init_layout.addWidget(self.init_editor)
        script_tabs.addTab(init_widget, "Init Script")

        loop_widget = QWidget()
        loop_layout = QVBoxLayout(loop_widget)
        loop_layout.addWidget(QLabel(
            "Loop Script — runs every interval. Use aliases to read inputs and write "
            "outputs. Call stop(\"reason\") to end the simulation."))
        self.loop_editor = ScriptEditor()
        self.loop_editor.setMinimumHeight(200)
        self.loop_editor.setPlaceholderText(
            "# Example:\n# if valve_cmd > 0:\n#     flow = 200.0\n#     tank_level += 1.5\n# else:\n#     flow = 0.0\n")
        loop_layout.addWidget(self.loop_editor)
        script_tabs.addTab(loop_widget, "Loop Script")

        # User Inputs tab
        user_inputs_widget = QWidget()
        user_inputs_layout = QVBoxLayout(user_inputs_widget)
        user_inputs_layout.addWidget(QLabel(
            "User Inputs — Interactive controls you can change while simulation runs"))
        
        # List of current user inputs with edit/delete
        inputs_group = QGroupBox("Current User Inputs")
        inputs_group_layout = QVBoxLayout(inputs_group)
        
        self.user_inputs_list = QListWidget()
        self.user_inputs_list.setMaximumHeight(120)
        inputs_group_layout.addWidget(self.user_inputs_list)
        
        list_buttons = QHBoxLayout()
        edit_input_btn = QPushButton("Edit Selected")
        edit_input_btn.clicked.connect(self._edit_user_input)
        list_buttons.addWidget(edit_input_btn)
        
        delete_input_btn = QPushButton("Delete Selected")
        delete_input_btn.clicked.connect(self._delete_user_input)
        list_buttons.addWidget(delete_input_btn)
        list_buttons.addStretch()
        
        inputs_group_layout.addLayout(list_buttons)
        user_inputs_layout.addWidget(inputs_group)
        
        # Live controls panel
        controls_group = QGroupBox("Live Controls (active during simulation)")
        controls_layout = QVBoxLayout(controls_group)
        self.user_inputs_panel = UserInputsPanel()
        controls_layout.addWidget(self.user_inputs_panel)
        user_inputs_layout.addWidget(controls_group)
        
        # Add new user input
        add_group = QGroupBox("Add New User Input")
        add_layout = QVBoxLayout(add_group)
        
        add_input_layout = QHBoxLayout()
        add_input_layout.addWidget(QLabel("Alias:"))
        self.input_alias_edit = QLineEdit()
        self.input_alias_edit.setPlaceholderText("e.g. manual_mode")
        add_input_layout.addWidget(self.input_alias_edit)
        
        add_input_layout.addWidget(QLabel("Type:"))
        self.input_type_combo = QComboBox()
        self.input_type_combo.addItems(["float", "int", "momentary", "toggle"])
        add_input_layout.addWidget(self.input_type_combo)
        
        add_input_layout.addWidget(QLabel("Label:"))
        self.input_label_edit = QLineEdit()
        self.input_label_edit.setPlaceholderText("e.g. Manual Mode")
        add_input_layout.addWidget(self.input_label_edit)
        
        add_layout.addLayout(add_input_layout)
        
        add_input_btn = QPushButton("Add Input")
        add_input_btn.clicked.connect(self._add_user_input)
        add_layout.addWidget(add_input_btn)
        
        user_inputs_layout.addWidget(add_group)
        
        script_tabs.addTab(user_inputs_widget, "User Inputs")

        layout.addWidget(script_tabs)

        # Keep editor autocompletion in sync with tag aliases as they change
        self.input_tags_widget.tags_changed.connect(self._refresh_editor_names)
        self.output_tags_widget.tags_changed.connect(self._refresh_editor_names)
        self._refresh_editor_names()

    def get_alias_names(self) -> list:
        """All alias names in the current module: input + output + user inputs."""
        names = []
        names += [e.alias for e in self.input_tags_widget.get_entries()]
        names += [e.alias for e in self.output_tags_widget.get_entries()]
        if self._module and self._module.user_inputs:
            names += [u.alias for u in self._module.user_inputs]
        return names

    def _refresh_editor_names(self):
        """Push the current set of alias names into both script editors so
        autocompletion knows about them, and notify other views."""
        names = self.get_alias_names()
        self.init_editor.set_known_names(names)
        self.loop_editor.set_known_names(names)
        self.aliases_changed.emit()

    def _add_user_input(self):
        """Add a user input control"""
        alias = self.input_alias_edit.text().strip()
        label = self.input_label_edit.text().strip()
        input_type = self.input_type_combo.currentText()

        if not alias or not label:
            QMessageBox.warning(self, "Missing Info", "Please enter alias and label")
            return

        # Determine default value based on type
        if input_type in ['float', 'int']:
            default_value = 0.0 if input_type == 'float' else 0
        else:
            default_value = False

        user_input = UserInput(
            alias=alias,
            input_type=input_type,
            label=label,
            default_value=default_value
        )

        # Get current inputs from the loaded module and append
        if not hasattr(self, '_module') or self._module is None:
            self._module = SimModule()
        
        self._module.user_inputs.append(user_input)  # Append to existing list
        
        # Reload to refresh display
        self.user_inputs_panel.set_inputs(self._module.user_inputs)
        
        # Clear input fields
        self.input_alias_edit.clear()
        self.input_label_edit.clear()

    def load_module(self, module: SimModule):
        """Populate UI from a SimModule"""
        self._module = module
        self.name_edit.setText(module.name)
        self.desc_edit.setText(module.description)
        self.interval_spin.setValue(module.interval_seconds)
        self.sim_tags_widget.load_tags(module.sim_tags)
        self.input_tags_widget.load_entries(module.input_tags)
        self.output_tags_widget.load_entries(module.output_tags)
        self._refresh_user_inputs_list()
        self.user_inputs_panel.set_inputs(module.user_inputs)
        self.init_editor.setPlainText(module.init_script)
        self.loop_editor.setPlainText(module.loop_script)
        self._refresh_editor_names()

    def collect_module(self) -> SimModule:
        """Build and return a SimModule from current UI state"""
        # Get user inputs from the module if it exists, otherwise empty list
        if hasattr(self, '_module') and self._module and hasattr(self._module, 'user_inputs'):
            user_inputs = self._module.user_inputs
        else:
            user_inputs = []
        
        return SimModule(
            name=self.name_edit.text().strip() or "Unnamed",
            description=self.desc_edit.text().strip(),
            sim_tags=self.sim_tags_widget.get_tags(),
            input_tags=self.input_tags_widget.get_entries(),
            output_tags=self.output_tags_widget.get_entries(),
            user_inputs=user_inputs,
            init_script=self.init_editor.toPlainText(),
            loop_script=self.loop_editor.toPlainText(),
            interval_seconds=self.interval_spin.value(),
        )

    def _refresh_user_inputs_list(self):
        """Refresh the list widget showing current user inputs"""
        self.user_inputs_list.clear()
        if hasattr(self, '_module') and self._module and self._module.user_inputs:
            for inp in self._module.user_inputs:
                self.user_inputs_list.addItem(f"{inp.alias} ({inp.input_type}) - {inp.label}")
    
    def _edit_user_input(self):
        """Edit the selected user input"""
        current_row = self.user_inputs_list.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "No Selection", "Please select a user input to edit")
            return
        
        if not hasattr(self, '_module') or not self._module:
            return
        
        user_input = self._module.user_inputs[current_row]
        
        # Populate edit fields with current values
        self.input_alias_edit.setText(user_input.alias)
        self.input_label_edit.setText(user_input.label)
        self.input_type_combo.setCurrentText(user_input.input_type)
        
        # Remove the old one (will be re-added when user clicks Add)
        self._module.user_inputs.pop(current_row)
        self._refresh_user_inputs_list()
        self.user_inputs_panel.set_inputs(self._module.user_inputs)
        self._refresh_editor_names()

    def _delete_user_input(self):
        """Delete the selected user input"""
        current_row = self.user_inputs_list.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "No Selection", "Please select a user input to delete")
            return
        
        if not hasattr(self, '_module') or not self._module:
            return
        
        user_input = self._module.user_inputs[current_row]
        
        confirm = QMessageBox.question(
            self, "Delete User Input",
            f"Delete user input '{user_input.alias}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if confirm == QMessageBox.StandardButton.Yes:
            self._module.user_inputs.pop(current_row)
            self._refresh_user_inputs_list()
            self.user_inputs_panel.set_inputs(self._module.user_inputs)
            self._refresh_editor_names()

    def _add_user_input(self):
        """Add a user input control"""
        alias = self.input_alias_edit.text().strip()
        label = self.input_label_edit.text().strip()
        input_type = self.input_type_combo.currentText()
        
        if not alias or not label:
            QMessageBox.warning(self, "Missing Info", "Please enter alias and label")
            return
        
        # Determine default value based on type
        if input_type in ['float', 'int']:
            default_value = 0.0 if input_type == 'float' else 0
        else:
            default_value = False
        
        user_input = UserInput(
            alias=alias,
            input_type=input_type,
            label=label,
            default_value=default_value
        )
        
        # Get current inputs from the loaded module and append
        if not hasattr(self, '_module') or self._module is None:
            self._module = SimModule()
        
        self._module.user_inputs.append(user_input)

        # Refresh displays
        self._refresh_user_inputs_list()
        self.user_inputs_panel.set_inputs(self._module.user_inputs)
        self._refresh_editor_names()
        
        # Clear input fields
        self.input_alias_edit.clear()
        self.input_label_edit.clear()


class SimulationTab(QWidget):
    """
    Top-level simulation tab that contains:
      - Left panel: module list + new/save/load buttons
      - Right panel: ModuleEditorWidget + run controls + live log
    """

    # Emitted (possibly from the engine's worker thread) when the engine stops
    # on its own — e.g. a script called stop(). Queued to the main thread.
    engine_finished = pyqtSignal()

    # Trend-tab integration. simulation_started carries the started SimModule;
    # sample_logged carries (elapsed_seconds, {alias: value}) each cycle and is
    # emitted from the engine's worker thread (Qt queues it to the main thread).
    simulation_started = pyqtSignal(object)
    simulation_stopped = pyqtSignal()
    sample_logged = pyqtSignal(float, dict)

    def __init__(self, plc, parent=None):
        super().__init__(parent)
        self.plc = plc
        self._engine: Optional[SimEngine] = None
        self._modules: list[SimModule] = []
        self._current_index: int = -1
        self._init_ui()
        self.engine_finished.connect(self._on_engine_finished)

    def _init_ui(self):
        outer = QHBoxLayout(self)

        # ── Left panel ──────────────────────────────────────────────
        left_panel = QWidget()
        left_panel.setMaximumWidth(220)
        left_layout = QVBoxLayout(left_panel)
        left_layout.addWidget(QLabel("Modules"))

        self.module_list = QListWidget()
        self.module_list.currentRowChanged.connect(self._on_module_selected)
        left_layout.addWidget(self.module_list)

        new_btn = QPushButton("+ New Module")
        new_btn.clicked.connect(self._new_module)
        left_layout.addWidget(new_btn)

        save_btn = QPushButton("💾 Save Module")
        save_btn.clicked.connect(self._save_module)
        left_layout.addWidget(save_btn)

        load_btn = QPushButton("📂 Load Module")
        load_btn.clicked.connect(self._load_module)
        left_layout.addWidget(load_btn)

        delete_btn = QPushButton("🗑 Delete Module")
        delete_btn.clicked.connect(self._delete_module)
        left_layout.addWidget(delete_btn)

        left_layout.addStretch()

        # Included libraries reference (available for use in scripts)
        libs_group = QGroupBox("Included Libraries")
        libs_layout = QVBoxLayout(libs_group)
        libs_layout.setContentsMargins(8, 4, 8, 4)
        libs_label = QLabel("\n".join(WHITELIST_MODULES))
        libs_label.setStyleSheet("color: #4EC9B0;")
        libs_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        libs_label.setToolTip("Python modules packaged with the app and available "
                              "to import/use in your scripts.")
        libs_layout.addWidget(libs_label)
        left_layout.addWidget(libs_group)

        outer.addWidget(left_panel)

        # ── Right panel ─────────────────────────────────────────────
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        self.editor = ModuleEditorWidget()
        right_layout.addWidget(self.editor, stretch=5)  # Give editor MORE space

        # Run controls - keep compact
        run_group = QGroupBox("Run Controls")
        run_layout = QHBoxLayout(run_group)

        self.start_btn = QPushButton("▶  Start Module")
        self.start_btn.setMinimumHeight(36)
        self.start_btn.clicked.connect(self._start_module)
        run_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("⏹  Stop Module")
        self.stop_btn.setMinimumHeight(36)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_module)
        run_layout.addWidget(self.stop_btn)

        self.status_label = QLabel("Stopped")
        self.status_label.setStyleSheet("color: gray; font-weight: bold;")
        run_layout.addWidget(self.status_label)
        run_layout.addStretch()

        right_layout.addWidget(run_group)

        # Collapsible log
        self.log_toggle_btn = QPushButton("▼ Execution Log")
        self.log_toggle_btn.setCheckable(True)
        self.log_toggle_btn.setChecked(True)
        self.log_toggle_btn.clicked.connect(self._toggle_log)
        right_layout.addWidget(self.log_toggle_btn)

        self.log_group = QGroupBox()
        log_layout = QVBoxLayout(self.log_group)
        log_layout.setContentsMargins(5, 5, 5, 5)
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumHeight(140)
        self.log_output.setFont(QFont("Consolas", 9))
        log_layout.addWidget(self.log_output)
        clear_log_btn = QPushButton("Clear Log")
        clear_log_btn.setMaximumWidth(100)
        clear_log_btn.clicked.connect(self.log_output.clear)
        log_layout.addWidget(clear_log_btn)
        right_layout.addWidget(self.log_group, stretch=1)  # Less space for log

        outer.addWidget(right_panel, stretch=1)

        # Start with one blank module
        self._new_module()

    def _toggle_log(self):
        """Toggle execution log visibility"""
        if self.log_toggle_btn.isChecked():
            self.log_group.show()
            self.log_toggle_btn.setText("▼ Execution Log")
        else:
            self.log_group.hide()
            self.log_toggle_btn.setText("▶ Execution Log (collapsed)")

    # ------------------------------------------------------------------
    # Module list management
    # ------------------------------------------------------------------

    def _new_module(self):
        """Add a blank module and select it"""
        self._save_current_to_list()
        module = SimModule(name=f"Module {len(self._modules) + 1}")
        self._modules.append(module)
        item = QListWidgetItem(module.name)
        self.module_list.addItem(item)
        self.module_list.setCurrentRow(len(self._modules) - 1)

    def _on_module_selected(self, index: int):
        if index < 0 or index >= len(self._modules):
            return
        self._save_current_to_list()
        self._current_index = index
        self.editor.load_module(self._modules[index])

    def _save_current_to_list(self):
        """Persist editor state back into the modules list"""
        if self._current_index < 0 or self._current_index >= len(self._modules):
            return
        updated = self.editor.collect_module()
        self._modules[self._current_index] = updated
        self.module_list.item(self._current_index).setText(updated.name)

    def _delete_module(self):
        if self._current_index < 0:
            return
        confirm = QMessageBox.question(self, "Delete Module",
                                       "Are you sure you want to delete this module?")
        if confirm == QMessageBox.StandardButton.Yes:
            self._modules.pop(self._current_index)
            self.module_list.takeItem(self._current_index)
            self._current_index = max(0, self._current_index - 1)
            if self._modules:
                self.module_list.setCurrentRow(self._current_index)

    # ------------------------------------------------------------------
    # Save / Load
    # ------------------------------------------------------------------

    def _save_module(self):
        self._save_current_to_list()
        if self._current_index < 0:
            return
        module = self._modules[self._current_index]
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Module", f"{module.name}.simmod", "Sim Module (*.simmod);;JSON (*.json)"
        )
        if path:
            module.save(path)
            self._append_log(f"Saved to {path}")

    def _load_module(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Module", "", "Sim Module (*.simmod);;JSON (*.json);;All (*)"
        )
        if not path:
            return
        try:
            module = SimModule.load(path)
            self._save_current_to_list()
            self._modules.append(module)
            item = QListWidgetItem(module.name)
            self.module_list.addItem(item)
            self.module_list.setCurrentRow(len(self._modules) - 1)
            self._append_log(f"Loaded: {module.name}")
        except Exception as e:
            QMessageBox.critical(self, "Load Error", f"Failed to load module:\n{e}")

    # ------------------------------------------------------------------
    # Run controls
    # ------------------------------------------------------------------

    def get_alias_names(self) -> list:
        """All alias names in the current module (delegates to the editor).
        Used by the Trend tab to populate its channel list."""
        return self.editor.get_alias_names()

    def _start_module(self):
        if not self.plc.connected:
            QMessageBox.warning(self, "Not Connected", "Please connect to PLC first.")
            return

        self._save_current_to_list()
        if self._current_index < 0:
            return

        module = self._modules[self._current_index]

        # Pre-run syntax gate — never run a syntax-broken script against the PLC
        for label, script in (("Init", module.init_script),
                              ("Loop", module.loop_script)):
            try:
                compile(script, "<script>", "exec")
            except SyntaxError as e:
                line = e.lineno or 1
                self._append_log(
                    f"{label} script syntax error (line {line}): {e.msg}", "error")
                QMessageBox.warning(
                    self, "Syntax Error",
                    f"{label} script has a syntax error on line {line}:\n\n{e.msg}\n\n"
                    "Fix it before starting the simulation.")
                return

        self._engine = SimEngine(module, self.plc, log_callback=self._append_log)
        # Reset the UI if the engine stops itself (script called stop()).
        # emit is thread-safe — delivers to _on_engine_finished on the main thread.
        self._engine.on_finished = self.engine_finished.emit
        # Forward per-cycle samples to the Trend tab (emitted from the loop
        # thread; Qt queues the signal to the main thread).
        self._engine.on_sample = lambda t, s: self.sample_logged.emit(t, s)

        if module.user_inputs:
            def get_user_input_values():
                return self.editor.user_inputs_panel.get_values()
            self._engine.set_user_input_callback(get_user_input_values)

        if self._engine.start():
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.status_label.setText("● Running")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
            self.simulation_started.emit(module)
        else:
            self._engine = None
            QMessageBox.critical(self, "Start Error",
                                 "Module failed to start. Check log for details.")

    def _stop_module(self):
        if self._engine:
            self._engine.stop()
            self._engine = None
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText("Stopped")
        self.status_label.setStyleSheet("color: gray; font-weight: bold;")
        self.simulation_stopped.emit()

    def _on_engine_finished(self):
        """Reset the UI after the engine stopped itself (script called stop()).
        Runs on the main thread via the engine_finished signal."""
        self._engine = None
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText("Stopped (by script)")
        self.status_label.setStyleSheet("color: gray; font-weight: bold;")
        self.simulation_stopped.emit()

    def _append_log(self, msg: str, level: str = "info"):
        color = {"error": "#FF6B6B", "warn": "#FFD93D"}.get(level, "#D4D4D4")
        self.log_output.append(f'<span style="color:{color}">{msg}</span>')

    def stop_all(self):
        """Called when application closes"""
        if self._engine and self._engine.is_running:
            self._engine.stop()
