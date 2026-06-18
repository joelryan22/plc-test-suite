"""
Main GUI Application for PLC Test Suite
"""

import sys
import logging
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QTableWidget, QTableWidgetItem,
    QGroupBox, QMessageBox, QComboBox, QTabWidget, QTextEdit,
    QHeaderView, QStatusBar
)
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QColor
from plc_test_suite.plc_connection import PLCConnection
from plc_test_suite.sim_tab import SimulationTab
from plc_test_suite.tag_browser import TagBrowserTab
from plc_test_suite.trend_tab import TrendTab

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PLCTestSuiteGUI(QMainWindow):
    """Main window for PLC Test Suite application"""
    
    def __init__(self):
        super().__init__()
        self.plc = PLCConnection()
        self.monitored_tags = []
        self.auto_refresh = False
        self.init_ui()
        
        # Auto-refresh timer (disabled by default)
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_tags)

        # Heartbeat timer
        self.heartbeat_timer = QTimer()
        self.heartbeat_timer.timeout.connect(self._update_heartbeat)
        self.heartbeat_value = 0
        
    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("PLC Test Suite - PlantPAx Simulation Tool")
        self.setGeometry(100, 100, 1280, 820)
        
        # Create central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Connection section
        connection_group = self.create_connection_section()
        main_layout.addWidget(connection_group)
        
        # Tab widget for different functions
        tab_widget = QTabWidget()
        
        # Tag Monitor tab
        tag_monitor_tab = self.create_tag_monitor_tab()
        tab_widget.addTab(tag_monitor_tab, "Tag Monitor")
        
        # Quick Write tab
        quick_write_tab = self.create_quick_write_tab()
        tab_widget.addTab(quick_write_tab, "Quick Write")
        
        # Simulation Modules tab (new)
        self.sim_tab = SimulationTab(self.plc)
        self.sim_tab.active_simulation_changed.connect(self._update_active_sim)
        tab_widget.addTab(self.sim_tab, "Simulation Modules")

        # Trend tab - live plotting of simulation aliases
        self.trend_tab = TrendTab(self.sim_tab)
        tab_widget.addTab(self.trend_tab, "Trend")

        # Tag Browser tab
        self.tag_browser_tab = TagBrowserTab(self.plc)
        tab_widget.addTab(self.tag_browser_tab, "Tag Browser")
        
        main_layout.addWidget(tab_widget)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.update_status("Not connected")
        
    def create_connection_section(self) -> QGroupBox:
        """Create PLC connection controls"""
        group = QGroupBox("PLC Connection")
        layout = QVBoxLayout()  # Change to VBoxLayout to stack rows
        
        # First row - IP address and connect button
        ip_row = QHBoxLayout()
        
        # IP Address input
        ip_row.addWidget(QLabel("PLC IP Address:"))
        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("192.168.1.10")
        self.ip_input.setText("192.168.1.10")  # Default for testing
        ip_row.addWidget(self.ip_input)
        
        # Connect button
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.toggle_connection)
        ip_row.addWidget(self.connect_btn)
        
        # Connection status
        self.connection_status = QLabel("⚫ Disconnected")
        ip_row.addWidget(self.connection_status)

        ip_row.addStretch()

        # Active simulation indicator (persistent across tabs)
        ip_row.addWidget(QLabel("Active Simulation:"))
        self.active_sim_label = QLabel("None")
        self.active_sim_label.setStyleSheet("font-weight: bold; color: gray;")
        ip_row.addWidget(self.active_sim_label)

        layout.addLayout(ip_row)
        
        # Second row - Heartbeat tag (NEW)
        heartbeat_row = QHBoxLayout()
        heartbeat_row.addWidget(QLabel("Heartbeat Tag:"))
        self.heartbeat_input = QLineEdit()
        self.heartbeat_input.setPlaceholderText("Optional - e.g., PLC_Heartbeat (cycles 0-100)")
        heartbeat_row.addWidget(self.heartbeat_input)
        heartbeat_row.addStretch()
        layout.addLayout(heartbeat_row)
        
        group.setLayout(layout)
        return group
    
    def create_tag_monitor_tab(self) -> QWidget:
        """Create tag monitoring interface"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Add tag controls
        add_layout = QHBoxLayout()
        add_layout.addWidget(QLabel("Tag Name:"))
        self.tag_name_input = QLineEdit()
        self.tag_name_input.setPlaceholderText("e.g., Valve_001.inp_sim")
        add_layout.addWidget(self.tag_name_input)
        
        add_tag_btn = QPushButton("Add Tag")
        add_tag_btn.clicked.connect(self.add_tag_to_monitor)
        add_layout.addWidget(add_tag_btn)
        
        layout.addLayout(add_layout)
        
        # Tag table
        self.tag_table = QTableWidget()
        self.tag_table.setColumnCount(3)
        self.tag_table.setHorizontalHeaderLabels(["Tag Name", "Value", "Actions"])
        self.tag_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tag_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tag_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.tag_table)
        
        # Refresh controls
        refresh_layout = QHBoxLayout()
        refresh_btn = QPushButton("Refresh Now")
        refresh_btn.clicked.connect(self.refresh_tags)
        refresh_layout.addWidget(refresh_btn)
        
        self.auto_refresh_btn = QPushButton("Enable Auto-Refresh (1s)")
        self.auto_refresh_btn.clicked.connect(self.toggle_auto_refresh)
        refresh_layout.addWidget(self.auto_refresh_btn)
        
        refresh_layout.addStretch()
        layout.addLayout(refresh_layout)
        
        return widget
    
    def create_quick_write_tab(self) -> QWidget:
        """Create quick tag write interface"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Input fields
        form_layout = QVBoxLayout()
        
        # Tag name
        tag_layout = QHBoxLayout()
        tag_layout.addWidget(QLabel("Tag Name:"))
        self.write_tag_input = QLineEdit()
        self.write_tag_input.setPlaceholderText("e.g., Valve_001.inp_sim")
        tag_layout.addWidget(self.write_tag_input)
        form_layout.addLayout(tag_layout)
        
        # Value
        value_layout = QHBoxLayout()
        value_layout.addWidget(QLabel("Value:"))
        self.write_value_input = QLineEdit()
        self.write_value_input.setPlaceholderText("e.g., 100.5 or True")
        value_layout.addWidget(self.write_value_input)
        form_layout.addLayout(value_layout)
        
        # Data type hint
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Data Type:"))
        self.data_type_combo = QComboBox()
        self.data_type_combo.addItems(["Auto-detect", "BOOL", "INT", "DINT", "REAL"])
        type_layout.addWidget(self.data_type_combo)
        type_layout.addStretch()
        form_layout.addLayout(type_layout)
        
        layout.addLayout(form_layout)
        
        # Write button
        write_btn = QPushButton("Write Tag")
        write_btn.clicked.connect(self.write_single_tag)
        write_btn.setMinimumHeight(40)
        layout.addWidget(write_btn)
        
        # Log output
        layout.addWidget(QLabel("Write Log:"))
        self.write_log = QTextEdit()
        self.write_log.setReadOnly(True)
        self.write_log.setMaximumHeight(200)
        layout.addWidget(self.write_log)
        
        layout.addStretch()
        return widget
    
    def create_simulation_control_tab(self) -> QWidget:
        """Create PlantPAx simulation control interface"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        layout.addWidget(QLabel("PlantPAx Device Simulation Control"))
        
        # Device name input
        device_layout = QHBoxLayout()
        device_layout.addWidget(QLabel("Device Name:"))
        self.device_name_input = QLineEdit()
        self.device_name_input.setPlaceholderText("e.g., Valve_001, LT_Tank_Level")
        device_layout.addWidget(self.device_name_input)
        layout.addLayout(device_layout)
        
        # Simulation control buttons
        btn_layout = QHBoxLayout()
        
        enable_sim_btn = QPushButton("Enable Simulation")
        enable_sim_btn.clicked.connect(lambda: self.control_simulation(True))
        btn_layout.addWidget(enable_sim_btn)
        
        disable_sim_btn = QPushButton("Disable Simulation")
        disable_sim_btn.clicked.connect(lambda: self.control_simulation(False))
        btn_layout.addWidget(disable_sim_btn)
        
        layout.addLayout(btn_layout)
        
        # Common PlantPAx tags section
        layout.addWidget(QLabel("\nCommon PlantPAx Tags:"))
        info_text = QTextEdit()
        info_text.setReadOnly(True)
        info_text.setMaximumHeight(300)
        info_text.setPlainText(
            "PlantPAx Simulation Tags Reference:\n\n"
            "Device Configuration:\n"
            "  .cfg_sim - Enable/disable simulation mode (BOOL)\n\n"
            "Analog Inputs (AI):\n"
            "  .inp_sim - Simulated process value (REAL)\n\n"
            "Analog Outputs (AO):\n"
            "  .out_sim - Simulated output value (REAL)\n\n"
            "Digital Inputs (DI):\n"
            "  .inp_sim - Simulated input state (BOOL)\n\n"
            "Digital Outputs (DO):\n"
            "  .out_sim - Simulated output state (BOOL)\n\n"
            "Valves:\n"
            "  .inp_simZSO - Valve open limit switch sim (BOOL)\n"
            "  .inp_simZSC - Valve closed limit switch sim (BOOL)\n\n"
            "Example Usage:\n"
            "  1. Enable simulation: Write TRUE to Valve_001.cfg_sim\n"
            "  2. Simulate valve open: Write TRUE to Valve_001.inp_simZSO\n"
            "  3. Simulate level: Write 75.5 to LT_Tank_001.inp_sim"
        )
        layout.addWidget(info_text)
        
        layout.addStretch()
        return widget
    
    def toggle_connection(self):
        """Connect or disconnect from PLC"""
        if not self.plc.connected:
            ip_address = self.ip_input.text().strip()
            if not ip_address:
                QMessageBox.warning(self, "Error", "Please enter a PLC IP address")
                return
            
            if self.plc.connect(ip_address):
                self.connect_btn.setText("Disconnect")
                self.connection_status.setText("🟢 Connected")
                self.connection_status.setStyleSheet("color: green;")
                self.update_status(f"Connected to {ip_address}")
                self._start_heartbeat()  # NEW - Start heartbeat
            else:
                QMessageBox.critical(self, "Connection Error", 
                                f"Failed to connect to PLC at {ip_address}")
                self.update_status("Connection failed")
        else:
            self._stop_heartbeat()  # NEW - Stop heartbeat
            self.plc.disconnect()
            self.connect_btn.setText("Connect")
            self.connection_status.setText("⚫ Disconnected")
            self.connection_status.setStyleSheet("color: gray;")
            self.update_status("Disconnected")
            if self.auto_refresh:
                self.toggle_auto_refresh()
    
    def _update_heartbeat(self):
        """Update heartbeat tag value (cycles 0-100)"""
        heartbeat_tag = self.heartbeat_input.text().strip()
        
        if not heartbeat_tag:
            return  # No heartbeat tag configured
        
        if not self.plc.connected:
            return  # Not connected
        
        try:
            # Write current heartbeat value
            self.plc.write_tag(heartbeat_tag, self.heartbeat_value)
            
            # Increment and wrap around
            self.heartbeat_value += 1
            if self.heartbeat_value > 100:
                self.heartbeat_value = 0
                
        except Exception as e:
            # Don't spam errors if heartbeat fails
            logger.debug(f"Heartbeat write failed: {e}")

    def _start_heartbeat(self):
        """Start the heartbeat timer"""
        heartbeat_tag = self.heartbeat_input.text().strip()
        
        if heartbeat_tag:
            self.heartbeat_value = 0
            self.heartbeat_timer.start(1000)  # Update every 1 second
            logger.info(f"Started heartbeat on tag: {heartbeat_tag}")

    def _stop_heartbeat(self):
        """Stop the heartbeat timer"""
        if self.heartbeat_timer.isActive():
            self.heartbeat_timer.stop()
            logger.info("Stopped heartbeat")

    def add_tag_to_monitor(self):
        """Add a tag to the monitoring table"""
        tag_name = self.tag_name_input.text().strip()
        if not tag_name:
            return
        
        # Check if tag already exists
        for tag in self.monitored_tags:
            if tag == tag_name:
                QMessageBox.warning(self, "Duplicate", "Tag already in monitor list")
                return
        
        self.monitored_tags.append(tag_name)
        
        # Add to table
        row = self.tag_table.rowCount()
        self.tag_table.insertRow(row)
        
        self.tag_table.setItem(row, 0, QTableWidgetItem(tag_name))
        self.tag_table.setItem(row, 1, QTableWidgetItem("--"))
        
        # Add remove button
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(lambda: self.remove_tag_from_monitor(row))
        self.tag_table.setCellWidget(row, 2, remove_btn)
        
        self.tag_name_input.clear()
        
        # Refresh immediately if connected
        if self.plc.connected:
            self.refresh_tags()
    
    def remove_tag_from_monitor(self, row: int):
        """Remove a tag from monitoring"""
        tag_name = self.tag_table.item(row, 0).text()
        self.monitored_tags.remove(tag_name)
        self.tag_table.removeRow(row)
    
    def refresh_tags(self):
        """Refresh all monitored tag values"""
        if not self.plc.connected or not self.monitored_tags:
            return
        
        values = self.plc.read_tags(self.monitored_tags)
        
        for row, tag_name in enumerate(self.monitored_tags):
            value = values.get(tag_name)
            if value is not None:
                self.tag_table.setItem(row, 1, QTableWidgetItem(str(value)))
            else:
                item = QTableWidgetItem("ERROR")
                item.setBackground(QColor(255, 200, 200))
                self.tag_table.setItem(row, 1, item)
    
    def toggle_auto_refresh(self):
        """Toggle automatic tag refresh"""
        self.auto_refresh = not self.auto_refresh
        
        if self.auto_refresh:
            self.refresh_timer.start(1000)  # 1 second
            self.auto_refresh_btn.setText("Disable Auto-Refresh")
            self.update_status("Auto-refresh enabled (1s)")
        else:
            self.refresh_timer.stop()
            self.auto_refresh_btn.setText("Enable Auto-Refresh (1s)")
            self.update_status("Auto-refresh disabled")
    
    def write_single_tag(self):
        """Write a value to a single tag"""
        if not self.plc.connected:
            QMessageBox.warning(self, "Not Connected", "Please connect to PLC first")
            return
        
        tag_name = self.write_tag_input.text().strip()
        value_str = self.write_value_input.text().strip()
        
        if not tag_name or not value_str:
            QMessageBox.warning(self, "Missing Information", 
                              "Please enter both tag name and value")
            return
        
        # Convert value based on type
        data_type = self.data_type_combo.currentText()
        
        try:
            if data_type == "BOOL" or value_str.lower() in ["true", "false"]:
                value = value_str.lower() == "true"
            elif data_type == "INT":
                value = int(value_str)
            elif data_type == "DINT":
                value = int(value_str)
            elif data_type == "REAL":
                value = float(value_str)
            else:  # Auto-detect
                # Try to determine type
                if value_str.lower() in ["true", "false"]:
                    value = value_str.lower() == "true"
                elif "." in value_str:
                    value = float(value_str)
                else:
                    value = int(value_str)
        except ValueError:
            QMessageBox.critical(self, "Invalid Value", 
                               f"Cannot convert '{value_str}' to appropriate data type")
            return
        
        # Write the tag
        success = self.plc.write_tag(tag_name, value)
        
        # Log the result
        if success:
            log_msg = f"✓ Successfully wrote {value} to {tag_name}"
            self.write_log.append(log_msg)
            self.update_status(f"Wrote to {tag_name}")
        else:
            log_msg = f"✗ Failed to write {value} to {tag_name}"
            self.write_log.append(log_msg)
            QMessageBox.critical(self, "Write Error", f"Failed to write to {tag_name}")
    
    def control_simulation(self, enable: bool):
        """Enable or disable simulation for a device"""
        if not self.plc.connected:
            QMessageBox.warning(self, "Not Connected", "Please connect to PLC first")
            return
        
        device_name = self.device_name_input.text().strip()
        if not device_name:
            QMessageBox.warning(self, "Missing Device Name", 
                              "Please enter a device name")
            return
        
        if enable:
            success = self.plc.enable_simulation(device_name)
            action = "enabled"
        else:
            success = self.plc.disable_simulation(device_name)
            action = "disabled"
        
        if success:
            QMessageBox.information(self, "Success", 
                                  f"Simulation {action} for {device_name}")
            self.update_status(f"Simulation {action} for {device_name}")
        else:
            QMessageBox.critical(self, "Error", 
                               f"Failed to {action[:-1]} simulation for {device_name}")
    
    def update_status(self, message: str):
        """Update status bar message"""
        self.status_bar.showMessage(message)

    def _update_active_sim(self, name: str):
        """Update the persistent active-simulation indicator in the connection box."""
        if name:
            self.active_sim_label.setText(name)
            self.active_sim_label.setStyleSheet("font-weight: bold; color: green;")
        else:
            self.active_sim_label.setText("None")
            self.active_sim_label.setStyleSheet("font-weight: bold; color: gray;")
    
    def closeEvent(self, event):
        """Handle application close"""
        self._stop_heartbeat()  # NEW - Stop heartbeat
        self.sim_tab.stop_all()
        if self.plc.connected:
            self.plc.disconnect()
        event.accept()


def main():
    """Main entry point for the application"""
    app = QApplication(sys.argv)
    window = PLCTestSuiteGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
