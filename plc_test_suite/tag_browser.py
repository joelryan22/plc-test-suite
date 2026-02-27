"""
Tag Browser - Discover and search PLC tags with UDT expansion
"""

import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QTreeWidget, QTreeWidgetItem, QHeaderView,
    QMessageBox, QApplication, QProgressDialog
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor

logger = logging.getLogger(__name__)


class TagLoadThread(QThread):
    """Background thread to load tags from PLC without freezing UI"""
    
    finished = pyqtSignal(list)  # Emits list of tag dicts
    progress = pyqtSignal(int, int)  # current, total
    error = pyqtSignal(str)
    
    def __init__(self, plc):
        super().__init__()
        self.plc = plc
        
    def run(self):
        """Load all tags from PLC"""
        try:
            if not self.plc.connected:
                self.error.emit("Not connected to PLC")
                return
            
            # Get tag list - this returns tag info including data type
            tags = self.plc.plc.get_tag_list()
            
            if not tags:
                self.error.emit("No tags found or failed to retrieve tag list")
                return
            
            tag_list = []
            for i, tag_info in enumerate(tags):
                tag_dict = {
                    'name': tag_info['tag_name'],
                    'type': tag_info.get('data_type_name', 'Unknown'),
                    'dim': tag_info.get('dim', 0),
                    'template': tag_info.get('template', None)
                }
                tag_list.append(tag_dict)
                
                if i % 50 == 0:
                    self.progress.emit(i, len(tags))
            
            self.finished.emit(tag_list)
            
        except Exception as e:
            logger.error(f"Error loading tags: {e}")
            self.error.emit(str(e))


class UDTExpandThread(QThread):
    """Background thread to expand a UDT structure"""
    
    finished = pyqtSignal(list)  # Emits list of member dicts
    error = pyqtSignal(str)
    
    def __init__(self, plc, tag_name):
        super().__init__()
        self.plc = plc
        self.tag_name = tag_name
        
    def run(self):
        """Read tag structure to get UDT members"""
        try:
            # Read the tag to get its structure
            result = self.plc.plc.read(self.tag_name)
            
            if result.error:
                # Check if it's a permission/access error (common with AOIs)
                if "path" in str(result.error).lower() or "access" in str(result.error).lower():
                    self.error.emit("Protected structure (likely AOI)")
                else:
                    self.error.emit(f"Error reading tag: {result.error}")
                return
            
            # If it's a structure, the value will be a dict
            if isinstance(result.value, dict):
                members = []
                for member_name, member_value in result.value.items():
                    member_type = type(member_value).__name__
                    # Check if member is also a UDT (dict)
                    is_udt = isinstance(member_value, dict)
                    members.append({
                        'name': member_name,
                        'value': member_value,
                        'type': 'UDT' if is_udt else member_type,
                        'is_udt': is_udt
                    })
                self.finished.emit(members)
            else:
                self.error.emit("Tag is not a UDT structure")
            
        except Exception as e:
            error_msg = str(e)
            # Check for common AOI/permission errors
            if "path" in error_msg.lower() or "permission" in error_msg.lower() or "access" in error_msg.lower():
                self.error.emit("Protected structure (AOI or system tag)")
            else:
                logger.error(f"Error expanding UDT: {e}")
                self.error.emit(str(e))


class TagBrowserTab(QWidget):
    """Tab for browsing all PLC tags with UDT expansion"""
    
    def __init__(self, plc, parent=None):
        super().__init__(parent)
        self.plc = plc
        self.all_tags = []
        self._init_ui()
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        # Top controls
        top_layout = QHBoxLayout()
        
        refresh_btn = QPushButton("🔄 Load Tags from PLC")
        refresh_btn.clicked.connect(self._load_tags)
        refresh_btn.setMinimumHeight(36)
        top_layout.addWidget(refresh_btn)
        
        top_layout.addWidget(QLabel("Search:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Type to filter tags...")
        self.search_input.textChanged.connect(self._filter_tags)
        top_layout.addWidget(self.search_input)
        
        self.tag_count_label = QLabel("0 tags")
        top_layout.addWidget(self.tag_count_label)
        
        layout.addLayout(top_layout)
        
        # Instructions
        info_label = QLabel(
            "💡 Tip: Click 'Load Tags from PLC' to discover all tags. "
            "Click ► to expand UDTs. Double-click any tag/member to copy full path to clipboard."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666; padding: 5px;")
        layout.addWidget(info_label)
        
        # Tag tree (replaces table)
        self.tag_tree = QTreeWidget()
        self.tag_tree.setColumnCount(2)
        self.tag_tree.setHeaderLabels(["Tag Name", "Data Type"])
        self.tag_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tag_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tag_tree.setAlternatingRowColors(True)
        self.tag_tree.itemDoubleClicked.connect(self._copy_tag_to_clipboard)
        self.tag_tree.itemExpanded.connect(self._on_item_expanded)
        layout.addWidget(self.tag_tree)
        
        # Bottom buttons
        bottom_layout = QHBoxLayout()
        
        copy_btn = QPushButton("📋 Copy Selected Tag")
        copy_btn.clicked.connect(self._copy_selected_tag)
        bottom_layout.addWidget(copy_btn)
        
        bottom_layout.addStretch()
        layout.addLayout(bottom_layout)
        
    def _load_tags(self):
        """Load all tags from PLC in background thread"""
        if not self.plc.connected:
            QMessageBox.warning(self, "Not Connected", 
                              "Please connect to PLC first")
            return
        
        progress = QProgressDialog("Loading tags from PLC...", "Cancel", 0, 100, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(500)
        
        self.load_thread = TagLoadThread(self.plc)
        
        def on_progress(current, total):
            if total > 0:
                progress.setValue(int(100 * current / total))
        
        def on_finished(tags):
            progress.close()
            self.all_tags = tags
            self._display_tags(tags)
            self.tag_count_label.setText(f"{len(tags)} tags")
            QMessageBox.information(self, "Success", 
                                  f"Loaded {len(tags)} tags from PLC")
        
        def on_error(error_msg):
            progress.close()
            QMessageBox.critical(self, "Error Loading Tags", 
                               f"Failed to load tags:\n{error_msg}")
        
        self.load_thread.progress.connect(on_progress)
        self.load_thread.finished.connect(on_finished)
        self.load_thread.error.connect(on_error)
        self.load_thread.start()
        
    def _display_tags(self, tags):
        """Display tags in the tree"""
        self.tag_tree.clear()
        
        for tag in tags:
            item = QTreeWidgetItem(self.tag_tree)
            item.setText(0, tag['name'])
            item.setText(1, tag['type'])
            item.setData(0, Qt.ItemDataRole.UserRole, tag['name'])  # Store full path
            
            # If it's a UDT, make it expandable
            if self._is_likely_udt(tag['type']):
                # Add dummy child to make it expandable
                dummy = QTreeWidgetItem(item)
                dummy.setText(0, "Loading...")
                item.setData(0, Qt.ItemDataRole.UserRole + 1, False)  # Not yet loaded
        
        self.tag_tree.sortItems(0, Qt.SortOrder.AscendingOrder)
        
    def _is_likely_udt(self, data_type):
        """Check if data type is likely a UDT (not a primitive type)"""
        primitives = ['BOOL', 'SINT', 'INT', 'DINT', 'LINT', 
                      'REAL', 'LREAL', 'STRING', 'DWORD', 'LWORD']
        return data_type not in primitives
        
    def _on_item_expanded(self, item):
        """When a UDT is expanded, load its members"""
        # Check if already loaded
        already_loaded = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if already_loaded:
            return
        
        # Get full tag path
        tag_path = item.data(0, Qt.ItemDataRole.UserRole)
        
        # Remove dummy child
        item.takeChildren()
        
        # Load UDT members in background
        self._expand_udt(item, tag_path)
        
    def _expand_udt(self, parent_item, tag_path):
        """Expand a UDT to show its members"""
        if not self.plc.connected:
            return
        
        expand_thread = UDTExpandThread(self.plc, tag_path)
        
        # Store thread reference to prevent premature garbage collection
        if not hasattr(self, '_expand_threads'):
            self._expand_threads = []
        self._expand_threads.append(expand_thread)
        
        def on_finished(members):
            for member in members:
                child_item = QTreeWidgetItem(parent_item)
                child_item.setText(0, member['name'])
                child_item.setText(1, member['type'])
                
                # Store full tag path (parent.member)
                full_path = f"{tag_path}.{member['name']}"
                child_item.setData(0, Qt.ItemDataRole.UserRole, full_path)
                
                # If member is also a UDT, make it expandable
                if member['is_udt']:
                    dummy = QTreeWidgetItem(child_item)
                    dummy.setText(0, "Loading...")
                    child_item.setData(0, Qt.ItemDataRole.UserRole + 1, False)
            
            # Mark as loaded
            parent_item.setData(0, Qt.ItemDataRole.UserRole + 1, True)
            
            # Clean up thread reference
            if expand_thread in self._expand_threads:
                self._expand_threads.remove(expand_thread)
        
        def on_error(error_msg):
            error_item = QTreeWidgetItem(parent_item)
            error_item.setText(0, f"Error: {error_msg}")
            error_item.setForeground(0, QColor("red"))
            
            # Clean up thread reference
            if expand_thread in self._expand_threads:
                self._expand_threads.remove(expand_thread)
        
        expand_thread.finished.connect(on_finished)
        expand_thread.error.connect(on_error)
        expand_thread.start()
        
        def on_error(error_msg):
            error_item = QTreeWidgetItem(parent_item)
            error_item.setText(0, f"Error: {error_msg}")
            error_item.setForeground(0, QColor("red"))
        
        expand_thread.finished.connect(on_finished)
        expand_thread.error.connect(on_error)
        expand_thread.start()
        
    def _filter_tags(self, search_text):
        """Filter displayed tags based on search text"""
        if not search_text:
            for i in range(self.tag_tree.topLevelItemCount()):
                self.tag_tree.topLevelItem(i).setHidden(False)
            self.tag_count_label.setText(f"{len(self.all_tags)} tags")
            return
        
        search_lower = search_text.lower()
        visible_count = 0
        
        for i in range(self.tag_tree.topLevelItemCount()):
            item = self.tag_tree.topLevelItem(i)
            tag_name = item.text(0).lower()
            matches = search_lower in tag_name
            item.setHidden(not matches)
            if matches:
                visible_count += 1
        
        self.tag_count_label.setText(
            f"{visible_count} / {len(self.all_tags)} tags"
        )
        
    def _copy_tag_to_clipboard(self, item, column):
        """Copy full tag path to clipboard"""
        # Get the full path stored in UserRole
        tag_path = item.data(0, Qt.ItemDataRole.UserRole)
        if not tag_path:
            return
        
        clipboard = QApplication.clipboard()
        clipboard.setText(tag_path)
        
        # Visual feedback
        self.tag_count_label.setText(f"✓ Copied: {tag_path}")
        self.tag_count_label.setStyleSheet("color: green; font-weight: bold;")
        
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(2000, lambda: self._reset_count_label())
        
    def _copy_selected_tag(self):
        """Copy currently selected tag"""
        item = self.tag_tree.currentItem()
        if item:
            self._copy_tag_to_clipboard(item, 0)
        
    def _reset_count_label(self):
        """Reset count label styling"""
        self.tag_count_label.setStyleSheet("")
        visible_count = sum(
            1 for i in range(self.tag_tree.topLevelItemCount())
            if not self.tag_tree.topLevelItem(i).isHidden()
        )
        total = len(self.all_tags)
        if visible_count == total:
            self.tag_count_label.setText(f"{total} tags")
        else:
            self.tag_count_label.setText(f"{visible_count} / {total} tags")

