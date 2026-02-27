"""
User Input Controls - Interactive widgets for live simulation control
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QDoubleSpinBox, QSpinBox, QGroupBox, QScrollArea,
    QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from dataclasses import dataclass
from typing import Any, List, Dict


@dataclass
class UserInput:
    """Represents a user-controllable input"""
    alias: str          # Variable name in script namespace
    input_type: str     # 'float', 'int', 'momentary', 'toggle'
    label: str          # Display label
    default_value: Any  # Default value
    min_val: float = None
    max_val: float = None


class FloatInputWidget(QWidget):
    """Widget for a float value with spinbox"""
    
    def __init__(self, user_input: UserInput, parent=None):
        super().__init__(parent)
        self.user_input = user_input
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        label = QLabel(f"{user_input.label}:")
        label.setMinimumWidth(150)
        layout.addWidget(label)
        
        self.spinbox = QDoubleSpinBox()
        self.spinbox.setRange(
            user_input.min_val if user_input.min_val is not None else -999999.0,
            user_input.max_val if user_input.max_val is not None else 999999.0
        )
        self.spinbox.setValue(user_input.default_value)
        self.spinbox.setSingleStep(0.1)
        self.spinbox.setDecimals(2)
        layout.addWidget(self.spinbox)
        
        layout.addStretch()
        
    def get_value(self):
        return self.spinbox.value()


class IntInputWidget(QWidget):
    """Widget for an integer value with spinbox"""
    
    def __init__(self, user_input: UserInput, parent=None):
        super().__init__(parent)
        self.user_input = user_input
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        label = QLabel(f"{user_input.label}:")
        label.setMinimumWidth(150)
        layout.addWidget(label)
        
        self.spinbox = QSpinBox()
        self.spinbox.setRange(
            int(user_input.min_val) if user_input.min_val is not None else -999999,
            int(user_input.max_val) if user_input.max_val is not None else 999999
        )
        self.spinbox.setValue(int(user_input.default_value))
        layout.addWidget(self.spinbox)
        
        layout.addStretch()
        
    def get_value(self):
        return self.spinbox.value()


class MomentaryButtonWidget(QWidget):
    """Widget for a momentary button (True while pressed)"""
    
    def __init__(self, user_input: UserInput, parent=None):
        super().__init__(parent)
        self.user_input = user_input
        self._pressed = False
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        label = QLabel(f"{user_input.label}:")
        label.setMinimumWidth(150)
        layout.addWidget(label)
        
        self.button = QPushButton("Press & Hold")
        self.button.setMinimumWidth(120)
        self.button.pressed.connect(self._on_pressed)
        self.button.released.connect(self._on_released)
        layout.addWidget(self.button)
        
        self.status_label = QLabel("False")
        self.status_label.setStyleSheet("color: gray;")
        layout.addWidget(self.status_label)
        
        layout.addStretch()
        
    def _on_pressed(self):
        self._pressed = True
        self.button.setStyleSheet("background-color: #4CAF50; color: white;")
        self.status_label.setText("True")
        self.status_label.setStyleSheet("color: green; font-weight: bold;")
        
    def _on_released(self):
        self._pressed = False
        self.button.setStyleSheet("")
        self.status_label.setText("False")
        self.status_label.setStyleSheet("color: gray;")
        
    def get_value(self):
        return self._pressed


class ToggleButtonWidget(QWidget):
    """Widget for a toggle button (ON/OFF state)"""
    
    def __init__(self, user_input: UserInput, parent=None):
        super().__init__(parent)
        self.user_input = user_input
        self._state = bool(user_input.default_value)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        label = QLabel(f"{user_input.label}:")
        label.setMinimumWidth(150)
        layout.addWidget(label)
        
        self.button = QPushButton("OFF")
        self.button.setMinimumWidth(120)
        self.button.setCheckable(True)
        self.button.setChecked(self._state)
        self.button.clicked.connect(self._on_clicked)
        layout.addWidget(self.button)
        
        self.status_label = QLabel("False")
        self.status_label.setStyleSheet("color: gray;")
        layout.addWidget(self.status_label)
        
        layout.addStretch()
        
        # Update initial display
        self._update_display()
        
    def _on_clicked(self):
        self._state = self.button.isChecked()
        self._update_display()
        
    def _update_display(self):
        if self._state:
            self.button.setText("ON")
            self.button.setStyleSheet("background-color: #2196F3; color: white;")
            self.status_label.setText("True")
            self.status_label.setStyleSheet("color: blue; font-weight: bold;")
        else:
            self.button.setText("OFF")
            self.button.setStyleSheet("")
            self.status_label.setText("False")
            self.status_label.setStyleSheet("color: gray;")
        
    def get_value(self):
        return self._state


class UserInputsPanel(QWidget):
    """Panel containing all user inputs for a simulation module"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._inputs: List[UserInput] = []
        self._widgets: List[QWidget] = []
        self._init_ui()
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Scrollable area for inputs
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        self.inputs_container = QWidget()
        self.inputs_layout = QVBoxLayout(self.inputs_container)
        self.inputs_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        scroll.setWidget(self.inputs_container)
        layout.addWidget(scroll)
        
    def set_inputs(self, inputs: List[UserInput]):
        """Set the list of user inputs and create widgets"""
        # Clear existing widgets
        while self.inputs_layout.count():
            item = self.inputs_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        self._inputs = inputs
        self._widgets = []
        
        if not inputs:
            no_inputs_label = QLabel("No user inputs defined")
            no_inputs_label.setStyleSheet("color: gray; font-style: italic; padding: 20px;")
            no_inputs_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.inputs_layout.addWidget(no_inputs_label)
            return
        
        # Create widgets for each input
        for user_input in inputs:
            if user_input.input_type == 'float':
                widget = FloatInputWidget(user_input)
            elif user_input.input_type == 'int':
                widget = IntInputWidget(user_input)
            elif user_input.input_type == 'momentary':
                widget = MomentaryButtonWidget(user_input)
            elif user_input.input_type == 'toggle':
                widget = ToggleButtonWidget(user_input)
            else:
                continue
            
            self._widgets.append(widget)
            self.inputs_layout.addWidget(widget)
        
        self.inputs_layout.addStretch()
        
    def get_values(self) -> Dict[str, Any]:
        """Get current values of all inputs as a dict {alias: value}"""
        values = {}
        for widget in self._widgets:
            values[widget.user_input.alias] = widget.get_value()
        return values
