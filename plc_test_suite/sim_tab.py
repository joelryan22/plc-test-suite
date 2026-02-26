"""
Simulation Module Editor - GUI widget for creating and running simulation modules
"""

import json
import logging
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QSplitter, QGroupBox, QListWidget, QListWidgetItem,
    QFileDialog, QMessageBox, QDoubleSpinBox, QTextEdit,
    QPlainTextEdit, QTabWidget, QFrame, QComboBox
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont

from plc_test_suite.sim_module import SimModule, SimEngine, TagEntry
from plc_test_suite.syntax_highlighter import PythonHighlighter

from plc_test_suite.user_inputs import UserInput, UserInputsPanel

logger = logging.getLogger(__name__)


class ScriptEditor(QPlainTextEdit):
    """Code editor with Python syntax highlighting and monospace font"""

    def __init__(self, parent=None):
        super().__init__(parent)
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1E1E1E;
                color: #D4D4D4;
                border: 1px solid #3C3C3C;
                padding: 4px;
            }
        """)
        self.setTabStopDistance(28)  # ~4 spaces width
        PythonHighlighter(self.document())

    def keyPressEvent(self, event):
        """Convert Tab key to 4 spaces"""
        if event.key() == Qt.Key.Key_Tab:
            self.insertPlainText("    ")
        else:
            super().keyPressEvent(event)


class TagTableWidget(QWidget):
    """
    Reusable widget for a table of (tag, alias) pairs.
    Used for both input_tags and output_tags.
    """

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
        remove_btn.clicked.connect(lambda: self.table.removeRow(self.table.indexAt(remove_btn.pos()).row()))
        self.table.setCellWidget(row, 2, remove_btn)

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
            "Loop Script — runs every interval. Use aliases to read inputs and write outputs."))
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
        
        # Clear input fields
        self.input_alias_edit.clear()
        self.input_label_edit.clear()


class SimulationTab(QWidget):
    """
    Top-level simulation tab that contains:
      - Left panel: module list + new/save/load buttons
      - Right panel: ModuleEditorWidget + run controls + live log
    """

    def __init__(self, plc, parent=None):
        super().__init__(parent)
        self.plc = plc
        self._engine: Optional[SimEngine] = None
        self._modules: list[SimModule] = []
        self._current_index: int = -1
        self._init_ui()

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

    def _start_module(self):
        if not self.plc.connected:
            QMessageBox.warning(self, "Not Connected", "Please connect to PLC first.")
            return

        self._save_current_to_list()
        if self._current_index < 0:
            return

        module = self._modules[self._current_index]
        self._engine = SimEngine(module, self.plc, log_callback=self._append_log)

        if module.user_inputs:
            def get_user_input_values():
                return self.editor.user_inputs_panel.get_values()
            self._engine.set_user_input_callback(get_user_input_values)

        if self._engine.start():
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.status_label.setText("● Running")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
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

    def _append_log(self, msg: str, level: str = "info"):
        color = {"error": "#FF6B6B", "warn": "#FFD93D"}.get(level, "#D4D4D4")
        self.log_output.append(f'<span style="color:{color}">{msg}</span>')

    def stop_all(self):
        """Called when application closes"""
        if self._engine and self._engine.is_running:
            self._engine.stop()
