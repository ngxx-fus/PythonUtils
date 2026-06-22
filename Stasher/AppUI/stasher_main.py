import os
import sys
import json
import yaml
import shutil
import subprocess
import threading
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QMenu,
    QTreeWidgetItem, QMessageBox, QDialog, QHeaderView,
    QTextEdit, QProgressDialog, QLabel,
    QVBoxLayout, QHBoxLayout, QGridLayout
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QAction, QPalette

# Import UI classes compiled from the respective .ui files
from stasher_ui import Ui_StasherMain
from stasher_newrecord_ui import Ui_NewRecord

CONFIG_FILE = "stasher_config.json"
DEFAULT_STORAGE = r"C:\Users\phu.nguyen-thanh\Documents\UserData"


"""
/*
 * Loads application configuration from a JSON file, creating defaults if missing.
 */
"""
def load_config():
    # Check if config file exists
    if not os.path.exists(CONFIG_FILE):
        default = {"PATH_STORAGE": DEFAULT_STORAGE}
        with open(CONFIG_FILE, "w", encoding='utf-8') as f:
            json.dump(default, f, indent=4)
        # Return default configuration
        return default

    with open(CONFIG_FILE, "r", encoding='utf-8') as f:
        try:
            # Return parsed configuration
            return json.load(f)
        except Exception:
            # Return default configuration on failure
            return {"PATH_STORAGE": DEFAULT_STORAGE}


# ---------------- WORKER THREAD ----------------
class BackupWorker(QThread):
    progress = Signal(int, str)
    finished = Signal(bool, str)
    ask_error = Signal(str, str)

    """
    /*
     * Initializes the backup worker thread.
     */
    """
    def __init__(self, root_path, storage_path, relative_list, record_name, record_desc):
        super().__init__()
        self.root_path = root_path
        self.storage_path = storage_path
        self.relative_list = relative_list
        self.record_name = record_name
        self.record_desc = record_desc
        self._is_cancelled = False
        self.sync_event = threading.Event()
        self.error_action = None
        self.skip_all_errors = False

    """
    /*
     * Cancels the active worker thread.
     */
    """
    def cancel(self):
        self._is_cancelled = True

    """
    /*
     * Sets the error handling action and resumes thread execution.
     */
    """
    def set_error_action(self, action):
        self.error_action = action
        self.sync_event.set()

    """
    /*
     * Executes the main backup routine.
     */
    """
    def run(self):
        try:
            folder_name = f"Record_{datetime.now().strftime('%Y_%B_%d_%H%M%S')}"
            record_path = os.path.join(self.storage_path, folder_name)
            os.makedirs(record_path, exist_ok=True)
            
            self.progress.emit(0, "Calculating files...")
            total_files = 0
            
            # Iterate through the relative list to count files
            for rel in self.relative_list:
                src = os.path.join(self.root_path, rel)
                # Check if path is a directory
                if rel.endswith('/') or os.path.isdir(src):
                    # Walk the directory tree
                    for dirpath, _, filenames in os.walk(src):
                        total_files += len(filenames)
                else:
                    total_files += 1

            # Check if total files is zero to prevent division by zero
            if total_files == 0:
                total_files = 1
                
            copied_files = 0

            def safe_copy(src_file, dst_file):
                # Loop to retry copying safely
                while True:
                    # Check if cancellation was requested
                    if self._is_cancelled:
                        raise Exception("Backup cancelled by user.")
                    try:
                        os.makedirs(os.path.dirname(dst_file), exist_ok=True)
                        shutil.copy2(src_file, dst_file)
                        nonlocal copied_files
                        copied_files += 1
                        percent = int((copied_files / total_files) * 100)
                        percent = min(percent, 99)
                        self.progress.emit(percent, f"Copying: {os.path.basename(src_file)}")
                        # Break retry loop on success
                        break
                    except Exception as e:
                        # Check if skipping all errors is enabled
                        if self.skip_all_errors:
                            # Break loop to skip file
                            break
                        self.sync_event.clear()
                        self.ask_error.emit(src_file, str(e))
                        self.sync_event.wait()
                        # Evaluate user error action
                        if self.error_action == "Abort":
                            raise Exception(f"Aborted by user due to error: {e}")
                        elif self.error_action == "Skip":
                            # Break loop to skip
                            break
                        elif self.error_action == "SkipAll":
                            self.skip_all_errors = True
                            # Break loop to skip
                            break

            # Iterate list to perform actual copying
            for rel in self.relative_list:
                # Check for cancellation
                if self._is_cancelled:
                    raise Exception("Backup cancelled by user.")
                src = os.path.join(self.root_path, rel)
                dest = os.path.join(record_path, rel)
                try:
                    # Check if source is a directory
                    if rel.endswith('/') or os.path.isdir(src):
                        shutil.copytree(src, dest, copy_function=safe_copy, dirs_exist_ok=True)
                    else:
                        safe_copy(src, dest)
                except Exception as e:
                    # Check if user explicitly aborted
                    if "Aborted by user" in str(e):
                        raise Exception("Backup cancelled by user.")
                    # Handle exceptions unless skip all is enabled
                    if not self.skip_all_errors:
                        self.sync_event.clear()
                        self.ask_error.emit(src, str(e))
                        self.sync_event.wait()
                        # Evaluate error action
                        if self.error_action == "Abort":
                            raise Exception(f"Aborted by user due to error: {e}")
                        elif self.error_action == "SkipAll":
                            self.skip_all_errors = True

            # Final check for cancellation before saving metadata
            if self._is_cancelled:
                raise Exception("Backup cancelled by user.")

            self.progress.emit(100, "Saving metadata...")
            
            record_data = {
                "GeneralInfo": [
                    {"Name": self.record_name},
                    {"Desc": self.record_desc},
                    {"FolderName": folder_name},
                    {"StoragePath": self.storage_path},
                    {"Path2Record": os.path.join("${StoragePath}", folder_name)},
                    {"RootPath": self.root_path},
                    {"RelativePathList": self.relative_list}
                ]
            }

            yml_file = os.path.join(record_path, "RecordStructure.yml")
            with open(yml_file, 'w', encoding='utf-8') as f:
                yaml.dump(record_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

            self.finished.emit(True, f"Record '{self.record_name}' has been successfully archived!")
        except Exception as e:
            # Check if directory cleanup is needed on cancel
            if self._is_cancelled and os.path.exists(record_path):
                try:
                    shutil.rmtree(record_path)
                except Exception:
                    pass
            self.finished.emit(False, str(e))


# ---------------- DELETE WORKER THREAD ----------------
class DeleteWorker(QThread):
    finished = Signal(bool, str)

    """
    /*
     * Initializes the deletion worker thread.
     */
    """
    def __init__(self, folder_path):
        super().__init__()
        self.folder_path = folder_path

    """
    /*
     * Executes the physical folder deletion.
     */
    """
    def run(self):
        try:
            shutil.rmtree(self.folder_path)
            self.finished.emit(True, "Record deleted successfully.")
        except Exception as e:
            self.finished.emit(False, f"Could not delete record: {str(e)}")


# ---------------- NEW RECORD DIALOG ----------------
class NewRecordDialog(QDialog, Ui_NewRecord):
    """
    /*
     * Initializes the New Record Dialog window.
     */
    """
    def __init__(self, storage_path):
        super().__init__()
        self.setupUi(self)
        self.storage_path = storage_path
        self.setAcceptDrops(True) 

        # Initialize a string container for the circular log buffer
        self.status_buffer = ""

        # Detach and destroy the old QLabel immediately to prevent ghost frames
        old_label = self.NewRecord_Label_RecentlyStatus
        parent = old_label.parentWidget()
        old_label.setParent(None)
        old_label.deleteLater() 

        # Create the new QTextEdit using the native Light theme styling
        self.NewRecord_Label_RecentlyStatus = QTextEdit(parent)
        self.NewRecord_Label_RecentlyStatus.setReadOnly(True)

        # Variables to store Record configuration state in RAM
        self.record_name = "Unnamed Record"
        self.record_desc = ""
        self.root_path = ""
        self.relative_list = []  

        self.View_AllRecordsTable.clear()
        self.View_AllRecordsTable.header().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.View_AllRecordsTable.header().setSectionsMovable(True)
        
        self.View_AllRecordsTable.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.View_AllRecordsTable.customContextMenuRequested.connect(self.open_custom_context_menu)

        # Build dynamic scaling layouts
        self.setMinimumSize(801, 568)
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.Group_NewRecord)
        main_layout.addWidget(self.Group_View, 1)
        main_layout.addWidget(self.buttonBox)
        
        nr_layout = QGridLayout(self.Group_NewRecord)
        nr_layout.addWidget(self.NewRecord_UserInput, 0, 0)
        nr_layout.addWidget(self.NewRecord_YourPath_Value, 0, 1, 1, 4)
        nr_layout.addWidget(self.NewRecord_Button_Undo, 1, 0)
        nr_layout.addWidget(self.NewRecord_Button_SetName, 1, 1)
        nr_layout.addWidget(self.NewRecord_Button_SetDesc, 1, 2)
        nr_layout.addWidget(self.NewRecord_Button_SetAsRootPath, 1, 3)
        nr_layout.addWidget(self.NewRecord_Button_AddFileOrFolder, 1, 4)
        nr_layout.addWidget(self.NewRecord_Label_RecentlyStatus, 2, 0, 1, 5)

        v_layout = QVBoxLayout(self.Group_View)
        v_layout.addWidget(self.View_AllRecordsTable)

        self.NewRecord_Button_SetName.clicked.connect(self.set_record_name_from_input)
        self.NewRecord_Button_SetDesc.clicked.connect(self.set_record_desc_from_input)
        self.NewRecord_Button_SetAsRootPath.clicked.connect(self.set_root_path_logic)
        self.NewRecord_Button_AddFileOrFolder.clicked.connect(self.add_path_logic)
        self.NewRecord_Button_Undo.clicked.connect(self.undo_last_action)
        
        self.update_status_bar("Ready. Please set Name, Description, Root Path, and add data files.")

    """
    /*
     * Updates the status log view using a circular buffer.
     */
    """
    def update_status_bar(self, msg):
        # Check if buffer has existing text
        if self.status_buffer:
            self.status_buffer += "\n" + msg
        else:
            self.status_buffer = msg

        # Check if buffer size exceeds limits
        if len(self.status_buffer) > 2045:
            self.status_buffer = self.status_buffer[-2045:]

        self.NewRecord_Label_RecentlyStatus.setText(self.status_buffer)
        scrollbar = self.NewRecord_Label_RecentlyStatus.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    """
    /*
     * Refreshes the TreeWidget display based on current RAM state.
     */
    """
    def refresh_table_view(self):
        self.View_AllRecordsTable.clear()
        # Iterate over paths to build tree display
        for i, p in enumerate(self.relative_list):
            item_type = "Folder" if p.endswith("/") else "File"
            name = os.path.basename(p.strip("/"))
            item = QTreeWidgetItem([str(i + 1), name, item_type, p])
            
            full_p = os.path.join(self.root_path, p) if self.root_path else p
            root_tooltip = f"Root Path: {self.root_path}" if self.root_path else "Root Path: Not set"
            # Iterate through columns to apply tooltip
            for col in range(item.columnCount()):
                item.setToolTip(col, f"{root_tooltip}\nFull Path: {full_p}")

            self.View_AllRecordsTable.addTopLevelItem(item)

    """
    /*
     * Sets the record name using the value from the general input field.
     */
    """
    def set_record_name_from_input(self):
        text = self.NewRecord_YourPath_Value.text().strip()
        # Validate input text
        if text:
            self.record_name = text
            self.NewRecord_YourPath_Value.clear()
            self.update_status_bar(f"✅ Record name set to: '{self.record_name}'")
        else:
            self.update_status_bar("⚠ Please enter a name in the input box before clicking set name!")

    """
    /*
     * Sets the record description using the value from the general input field.
     */
    """
    def set_record_desc_from_input(self):
        text = self.NewRecord_YourPath_Value.text().strip()
        # Validate input text
        if text:
            self.record_desc = text
            self.NewRecord_YourPath_Value.clear()
            self.update_status_bar(f"✅ Description set to: '{self.record_desc}'")
        else:
            self.update_status_bar("⚠ Please enter description content in the input box first!")

    """
    /*
     * Logic to define the base directory for relative paths.
     */
    """
    def set_root_path_logic(self):
        path = self.NewRecord_YourPath_Value.text().strip().strip('"').strip("'")
        
        # Check if path is empty
        if not path:
            # Check if list is empty
            if not self.relative_list:
                self.update_status_bar("⚠ List is empty. Cannot calculate automatic root directory.")
                # Return from logic
                return
                
            abs_paths = [p for p in self.relative_list if os.path.isabs(p)]
            # Check if valid absolute paths exist
            if not abs_paths:
                self.update_status_bar("⚠ All current paths are already relative. Please enter a specific RootPath.")
                # Return from logic
                return
                
            try:
                common_root = os.path.commonpath(abs_paths).replace("\\", "/")
                self.root_path = common_root
                
                new_list = []
                # Re-evaluate all entries
                for p in self.relative_list:
                    # Check if path needs converting
                    if os.path.isabs(p):
                        rel = os.path.relpath(p, self.root_path).replace("\\", "/")
                        # Preserve folder slash
                        if p.endswith('/') or os.path.isdir(p):
                            rel += '/'
                        new_list.append(rel)
                    else:
                        new_list.append(p)
                self.relative_list = new_list
                self.refresh_table_view()
                self.update_status_bar(f"✅ Automatically found and set common RootPath: {self.root_path}")
            except Exception as e:
                self.update_status_bar(f"❌ Failed to calculate common RootPath: {str(e)}")
            # Return from logic
            return

        # Check if valid directory
        if not os.path.isdir(path):
            self.update_status_bar("❌ RootPath is invalid or directory does not exist.")
            # Return from logic
            return

        self.root_path = os.path.abspath(path).replace("\\", "/")
        self.update_status_bar(f"✅ RootPath set: {self.root_path}")
        self.NewRecord_YourPath_Value.clear()

    """
    /*
     * Adds a file or folder path to the backup list.
     */
    """
    def add_path_logic(self):
        filepath = self.NewRecord_YourPath_Value.text().strip().strip('"').strip("'")
        # Check if empty
        if not filepath:
            self.update_status_bar("⚠ The path input field is currently empty.")
            # Return from empty
            return

        is_absolute = os.path.isabs(filepath)
        full_path = filepath

        # Evaluate absolute state
        if is_absolute:
            # Check root path existence
            if not self.root_path:
                self.root_path = os.path.dirname(full_path).replace("\\", "/")
                self.update_status_bar(f"✅ Auto-set RootPath based on file: {self.root_path}")
            
            try:
                common_root = os.path.commonpath([self.root_path, filepath]).replace("\\", "/")
                # Determine if root path shifted
                if os.path.normpath(common_root) != os.path.normpath(self.root_path):
                    reply = QMessageBox.question(
                        self, 'Update common RootPath?', 
                        f"Path is outside current root directory.\nCommon folder found: {common_root}\nDo you want to update RootPath for all entries?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes
                    )
                    # Proceed with update if yes
                    if reply == QMessageBox.StandardButton.Yes:
                        new_rel_list = []
                        # Process old list paths
                        for old_rel in self.relative_list:
                            old_abs = os.path.join(self.root_path, old_rel)
                            new_rel = os.path.relpath(old_abs, common_root).replace("\\", "/")
                            # Keep folder slash
                            if old_rel.endswith('/'): 
                                new_rel += '/'
                            new_rel_list.append(new_rel)
                        self.relative_list = new_rel_list
                        self.root_path = common_root
                    else:
                        self.update_status_bar("⛔ Cancelled adding file outside RootPath.")
                        # Return to abort
                        return
                rel_path = os.path.relpath(full_path, self.root_path).replace("\\", "/")
            except ValueError:
                self.update_status_bar("❌ File is on a different drive partition. Cannot merge Root Path.")
                # Return to abort
                return
        else:
            # Check if root path missing
            if not self.root_path:
                self.update_status_bar("⚠ Please configure RootPath before entering relative paths!")
                # Return to abort
                return
            rel_path = filepath
            full_path = os.path.join(self.root_path, rel_path)

        # Validate existence
        if os.path.exists(full_path):
            standard_rel = rel_path.replace("\\", "/") 
            # Fix folder slash
            if os.path.isdir(full_path) and not standard_rel.endswith('/'):
                standard_rel += '/'

            # Deduplicate entries
            if standard_rel not in self.relative_list:
                self.relative_list.append(standard_rel)
                self.refresh_table_view()
                self.NewRecord_YourPath_Value.clear()
                self.update_status_bar(f"✅ Successfully added: {standard_rel}")
            else:
                self.update_status_bar("⚠ This path already exists in the list.")
        else:
            self.update_status_bar("❌ Failed: File or directory not found in real life.")

    """
    /*
     * Removes the last added path from the list.
     */
    """
    def undo_last_action(self):
        # Check list items
        if self.relative_list:
            removed = self.relative_list.pop()
            self.update_status_bar(f"⛔ Undone (Removed item): {removed}")
            self.refresh_table_view()
        else:
            self.update_status_bar("⚠ List is empty, nothing to undo.")
            
    """
    /*
     * Handles right-click events on the New Record table.
     */
    """
    def open_custom_context_menu(self, pos):
        item = self.View_AllRecordsTable.itemAt(pos)
        # Prevent actions on void area
        if not item:
            # Return fast
            return

        idx = self.View_AllRecordsTable.indexOfTopLevelItem(item)
        # Validate index range
        if idx < 0 or idx >= len(self.relative_list):
            # Return invalid
            return
            
        path_val = self.relative_list[idx]
        item_type = "Folder" if path_val.endswith("/") else "File"
        name = os.path.basename(path_val.strip("/"))

        menu = QMenu(self)
        act_delete = QAction(f"Delete {item_type}: {name}", self)
        act_update_root = QAction("Update root path", self)

        act_delete.triggered.connect(lambda: self.remove_item_from_list(idx))
        act_update_root.triggered.connect(self.force_recalculate_root_path)

        menu.addAction(act_delete)
        menu.addAction(act_update_root)
        menu.exec(self.View_AllRecordsTable.viewport().mapToGlobal(pos))

    """
    /*
     * Removes a specific item from the new record file list.
     */
    """
    def remove_item_from_list(self, idx):
        # Validate boundary
        if 0 <= idx < len(self.relative_list):
            removed = self.relative_list.pop(idx)
            self.update_status_bar(f"⛔ Removed item: {removed}")
            self.refresh_table_view()

    """
    /*
     * Calculates the longest shared path among all recorded files as the Root Path.
     */
    """
    def force_recalculate_root_path(self):
        # Check validity
        if not self.relative_list:
            self.update_status_bar("⚠ List is empty. Cannot update root directory.")
            # Return early
            return
            
        abs_paths = []
        # Gather all valid paths
        for p in self.relative_list:
            # Identify path context
            if os.path.isabs(p):
                abs_paths.append(p)
            elif self.root_path:
                abs_paths.append(os.path.join(self.root_path, p).replace("\\", "/"))
        
        # Check if paths gathered
        if not abs_paths:
            self.update_status_bar("⚠ No valid paths to calculate root.")
            # Return null state
            return

        try:
            common_root = os.path.commonpath(abs_paths).replace("\\", "/")
            self.root_path = common_root
            
            new_list = []
            # Relativize paths against new root
            for p in abs_paths:
                rel = os.path.relpath(p, self.root_path).replace("\\", "/")
                # Ensure dir consistency
                if p.endswith('/') or os.path.isdir(p):
                    rel += '/'
                new_list.append(rel)
                
            self.relative_list = new_list
            self.refresh_table_view()
            self.update_status_bar(f"✅ RootPath updated to longest shared path: {self.root_path}")
        except Exception as e:
            self.update_status_bar(f"❌ Failed to update RootPath: {str(e)}")

    """
    /*
     * Accepts drag events if they contain file paths.
     */
    """
    def dragEnterEvent(self, event):
        # Check drag content type
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    """
    /*
     * Handles dropped files by adding them to the record list.
     */
    """
    def dropEvent(self, event):
        urls = event.mimeData().urls()
        # Ensure urls are valid
        if urls:
            event.acceptProposedAction()
            # Iterate through dropped contents
            for url in urls:
                path = url.toLocalFile()
                # Ensure real path mapping
                if os.path.exists(path):
                    self.NewRecord_YourPath_Value.setText(path)
                    self.add_path_logic()
            self.NewRecord_YourPath_Value.clear()
        else:
            super().dropEvent(event)

    """
    /*
     * Executes the actual backup process.
     */
    """
    def accept(self):
        # Safety lock empty entries
        if not self.relative_list:
            QMessageBox.warning(self, "Data Error", "File list is empty. Cannot proceed with backup.")
            # Abort process
            return
        # Safety lock empty root path
        if not self.root_path:
            QMessageBox.warning(self, "Config Error", "Please verify a valid RootPath before finishing.")
            # Abort process
            return

        self.progress_dialog = QProgressDialog("Calculating files...", "Cancel", 0, 100, self)
        self.progress_dialog.setWindowTitle("Backup Progress")
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setAutoClose(False)
        self.progress_dialog.setAutoReset(False)
        self.progress_dialog.setValue(0)
        self.progress_dialog.setMinimumDuration(0) 
        
        # Enable select capability on progress dialogue
        for label in self.progress_dialog.findChildren(QLabel):
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        
        self.worker = BackupWorker(
            self.root_path, self.storage_path, self.relative_list, 
            self.record_name, self.record_desc
        )
        self.worker.progress.connect(self.update_progress)
        self.worker.ask_error.connect(self.handle_backup_error)
        self.worker.finished.connect(self.backup_finished)
        self.progress_dialog.canceled.connect(self.worker.cancel)
        
        self.worker.start()
        self.progress_dialog.exec()
        
    """
    /*
     * Prompts the user with error resolution strategies during backup.
     */
    """
    def handle_backup_error(self, filepath, error_msg):
        msg = QMessageBox(self)
        msg.setWindowTitle("Copy Error")
        msg.setText(f"Failed to copy:\n{filepath}\n\nError: {error_msg}")
        msg.setStandardButtons(
            QMessageBox.StandardButton.Retry | 
            QMessageBox.StandardButton.Ignore | 
            QMessageBox.StandardButton.Abort
        )
        skip_all_button = msg.addButton("Skip All", QMessageBox.ButtonRole.ActionRole)
        msg.setDefaultButton(QMessageBox.StandardButton.Retry)
        msg.exec()

        clicked_button = msg.clickedButton()
        # Verify user interaction outcome
        if clicked_button == skip_all_button:
            self.worker.set_error_action("SkipAll")
        else:
            standard_button = msg.standardButton(clicked_button)
            # Route specific standard outcomes
            if standard_button == QMessageBox.StandardButton.Ignore:
                self.worker.set_error_action("Skip")
            elif standard_button == QMessageBox.StandardButton.Abort:
                self.worker.set_error_action("Abort")
            else: 
                self.worker.set_error_action("Retry")

    """
    /*
     * Updates UI progress percentage tracker.
     */
    """
    def update_progress(self, percent, msg):
        self.progress_dialog.setValue(percent)
        self.progress_dialog.setLabelText(msg)

    """
    /*
     * Handles completion of backup tasks.
     */
    """
    def backup_finished(self, success, msg):
        self.progress_dialog.close()
        # Verify success criteria
        if success:
            QMessageBox.information(self, "Success", msg)
            super().accept()
        else:
            # Check for silent cancel
            if msg == "Backup cancelled by user.":
                QMessageBox.warning(self, "Cancelled", msg)
            else:
                QMessageBox.critical(self, "Critical Error", f"Error during file packaging: {msg}")


# ---------------- MAIN PROGRAM ----------------
class StasherApp(QMainWindow, Ui_StasherMain):
    """
    /*
     * Initializes the core Stasher App Window context.
     */
    """
    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.config = load_config()
        self.storage_path = self.config.get("PATH_STORAGE", DEFAULT_STORAGE)

        self.records = []
        self.hidden_folders = set()  
        
        # List initialization for Multi-select tracking
        self.selected_records_ui = []
        self.selected_records_data = []

        self.init_interface_bindings()
        self.scan_storage_to_ram()

    """
    /*
     * Initializes UI elements, read-only fields, and signal-slot connections.
     */
    """
    def init_interface_bindings(self):
        # Configure scaling and layout for main window
        self.setMinimumSize(802, 667)
        main_layout = QVBoxLayout(self.centralwidget)
        main_layout.addWidget(self.Group_Summary)
        main_layout.addWidget(self.Group_Edit)
        main_layout.addWidget(self.Group_View, 1)

        sum_layout = QGridLayout(self.Group_Summary)
        sum_layout.addWidget(self.Summary_NumberOfRecords, 0, 0)
        sum_layout.addWidget(self.Summary_NumberOfRecords_Value, 0, 1)
        sum_layout.addWidget(self.Summary_Path2AppConfig, 1, 0)
        sum_layout.addWidget(self.Summary_Path2AppConfig_Value, 1, 1)
        sum_layout.addWidget(self.Summary_Path2AppFolder, 2, 0)
        sum_layout.addWidget(self.Summary_Path2AppFolder_Value, 2, 1)

        edit_layout = QGridLayout(self.Group_Edit)
        edit_layout.addWidget(self.Edit_Button_ListAllRecord, 0, 0)
        edit_layout.addWidget(self.Edit_Button_NewRecord, 0, 1)
        edit_layout.addWidget(self.Edit_Button_SearchByName, 0, 2)
        edit_layout.addWidget(self.Edit_Button_SearchByNameDesc, 0, 3)
        edit_layout.addWidget(self.Edit_Button_RefreshRecords, 0, 4)
        edit_layout.addWidget(self.Edit_GeneralUserInput, 1, 0, 1, 5)

        view_layout = QVBoxLayout(self.Group_View)
        view_layout.addWidget(self.View_AllRecordsTable)
        paste_layout = QHBoxLayout()
        paste_layout.addWidget(self.View_Path2PatchFolder_Value)
        paste_layout.addWidget(self.View_Path2PatchFolder_Button)
        view_layout.addLayout(paste_layout)

        self.Summary_Path2AppConfig_Value.setText(os.path.abspath(CONFIG_FILE))
        self.Summary_Path2AppConfig_Value.setReadOnly(True)
        self.Summary_Path2AppFolder_Value.setText(self.storage_path)
        self.Summary_Path2AppFolder_Value.setReadOnly(True)

        self.View_AllRecordsTable.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.View_AllRecordsTable.customContextMenuRequested.connect(self.open_custom_context_menu)
        
        
        # Enhance Table resizing configurations
        self.View_AllRecordsTable.header().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.View_AllRecordsTable.header().setSectionsMovable(True)

        self.Edit_Button_ListAllRecord.clicked.connect(self.reset_and_show_all)
        self.Edit_Button_RefreshRecords.clicked.connect(self.force_refresh_all_records)
        self.Edit_Button_NewRecord.clicked.connect(self.trigger_new_record_dialog)
        self.Edit_Button_SearchByName.clicked.connect(lambda: self.execute_ram_search(priority="name"))
        self.Edit_Button_SearchByNameDesc.clicked.connect(lambda: self.execute_ram_search(priority="desc"))
        self.View_Path2PatchFolder_Button.clicked.connect(self.execute_paste_patch_logic)

        self.Edit_GeneralUserInput.textChanged.connect(self.handle_empty_search_input)

    """
    /*
     * Helper to flatten the 'GeneralInfo' list from the YAML structure into a dictionary.
     */
    """
    def extract_yaml_info(self, data):
        info = {}
        # Iterate mapping structure
        for d in data.get("GeneralInfo", []):
            info.update(d)
        # Return merged metadata
        return info

    """
    /*
     * Scans the storage directory once and caches all record metadata into RAM.
     */
    """
    def scan_storage_to_ram(self):
        self.records.clear()
        # Verify valid core directory
        if not os.path.exists(self.storage_path):
            os.makedirs(self.storage_path)

        # Loop active local archives
        for folder in os.listdir(self.storage_path):
            folder_path = os.path.join(self.storage_path, folder)
            yml_path = os.path.join(folder_path, "RecordStructure.yml")

            # Validate entry constraints
            if os.path.isdir(folder_path) and os.path.exists(yml_path):
                try:
                    with open(yml_path, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                        info = self.extract_yaml_info(data)
                        info["_folder"] = folder_path
                        info["_yml"] = yml_path
                        info["_raw_data"] = data
                        self.records.append(info)
                except Exception as e:
                    print(f"Error parsing YAML file {yml_path}: {e}")

        self.Summary_NumberOfRecords_Value.setText(str(len(self.records)))
        self.render_records_to_tree_view(self.records)

    """
    /*
     * Populates the TreeWidget with cached record data.
     */
    """
    def render_records_to_tree_view(self, data_list):
        self.View_AllRecordsTable.clear()

        # Generate table row representations
        for idx, rec in enumerate(data_list):
            # Mask hidden attributes
            if rec["_folder"] in self.hidden_folders:
                # Continue next iteration
                continue

            # root_item = QTreeWidgetItem([
            #     str(idx + 1),
            #     rec.get("Name", "Unknown Name"),
            #     rec.get("RootPath", "N/A"),
            #     str(len(rec.get("RelativePathList", []))),
            #     rec.get("Desc", "")
            # ])
            
            root_item = QTreeWidgetItem([
                str(idx + 1),
                rec.get("Name", "Unknown Name"),
                rec.get("RootPath", "N/A"),
                str(len(rec.get("RelativePathList", []))),
                rec.get("Desc", "")
            ])

            update_time = rec.get("UpdateRecordTime", "<2026/01/01-00:00:00>")

            # Iterate through columns to inject the timestamp tooltip
            for col in range(root_item.columnCount()):
                root_item.setToolTip(col, f"UpdateRecordTime: {update_time}")

            root_item.setData(0, Qt.ItemDataRole.UserRole, rec)

            # Traverse to append children sub-elements
            for p in rec.get("RelativePathList", []):
                icon = "📁" if p.endswith("/") else "📄"
                child_item = QTreeWidgetItem(["", "", "", f"{icon} {p}", ""])
                root_item.addChild(child_item)

            self.View_AllRecordsTable.addTopLevelItem(root_item)
            
            # Apply tracking for multi-select memory persistence
            for selected_rec in self.selected_records_data:
                # Validate selected memory footprint
                if selected_rec["_folder"] == rec["_folder"]:
                    self.apply_row_light_mode_color(root_item, highlight=True)

    """
    /*
     * Explicitly assigns colors to Tree items supporting Windows Light Mode.
     */
    """
    def apply_row_light_mode_color(self, item, highlight=True):
        # Test truthiness parameter
        if highlight:
            # Propagate style modification over columns
            for col in range(item.columnCount()):
                item.setBackground(col, QColor(51, 153, 255))
                item.setForeground(col, QColor(255, 255, 255))
        else:
            # Propagate normal style modification
            for col in range(item.columnCount()):
                item.setBackground(col, Qt.GlobalColor.transparent)
                item.setForeground(col, QColor(0, 0, 0))

    """
    /*
     * Clears search filter and shows all cached records.
     */
    """
    def reset_and_show_all(self):
        self.Edit_GeneralUserInput.clear()
        self.render_records_to_tree_view(self.records)

    """
    /*
     * Full re-scan of the storage folder from disk into RAM.
     */
    """
    def force_refresh_all_records(self):
        self.hidden_folders.clear()
        self.selected_records_ui.clear()
        self.selected_records_data.clear()
        self.View_Path2PatchFolder_Value.clear()
        self.scan_storage_to_ram()
        QMessageBox.information(self, "Refresh Successful", "Storage re-scanned and synchronized to RAM!")

    """
    /*
     * Auto-resets the table view when search input becomes empty.
     */
    """
    def handle_empty_search_input(self):
        # Validate entry string evaluation
        if not self.Edit_GeneralUserInput.text().strip():
            self.render_records_to_tree_view(self.records)

    """
    /*
     * Performs a weighted search algorithm across cached records in RAM.
     */
    """
    def execute_ram_search(self, priority="name"):
        query = self.Edit_GeneralUserInput.text().strip().lower()
        # Fallback operation if void constraint detected
        if not query:
            self.render_records_to_tree_view(self.records)
            # Break process execution
            return

        scored_list = []
        # Score computation cycle
        for rec in self.records:
            name = rec.get("Name", "").lower()
            desc = rec.get("Desc", "").lower()
            
            score = 0
            # Test query property alignment
            if priority == "name":
                # Augment specific scores based on criteria
                if query in name: score += 20
                if query in desc: score += 2
            else:  
                # Augment specific scores conversely
                if query in desc: score += 20
                if query in name: score += 2
                
            # Filter matches beyond zero threshold
            if score > 0:
                scored_list.append((score, rec))
                
        scored_list.sort(key=lambda x: x[0], reverse=True)
        sorted_records = [item[1] for item in scored_list]
        
        self.render_records_to_tree_view(sorted_records)

    """
    /*
     * Opens the dialog to create and archive a new backup record.
     */
    """
    def trigger_new_record_dialog(self):
        dialog = NewRecordDialog(self.storage_path)
        # Execute secondary configuration procedure
        if dialog.exec():
            self.scan_storage_to_ram()

    """
    /*
     * Prompts the user with a dialog to handle a missing file during the update process.
     */
    """
    def prompt_missing_file_dialog(self, filepath, parent_widget=None):
        parent = parent_widget if parent_widget else self

        msg = QMessageBox(self)
        msg.setWindowTitle("Missing File/Folder")
        msg.setText(f"The following item was not found in RootPath:\n{filepath}\n\nSelect an action to proceed:")
        
        btn_remove = msg.addButton("Remove file/folder", QMessageBox.ButtonRole.DestructiveRole)
        btn_skip = msg.addButton("Skip update for this file", QMessageBox.ButtonRole.ActionRole)
        btn_stop = msg.addButton("Stop update", QMessageBox.ButtonRole.AcceptRole)
        btn_cancel = msg.addButton("Cancel update", QMessageBox.ButtonRole.RejectRole)
        
        msg.exec()
        clicked = msg.clickedButton()
        
        # Check which action the user selected
        if clicked == btn_remove:
            # Return the remove action
            return "Remove"
        elif clicked == btn_skip:
            # Return the skip action
            return "Skip"
        elif clicked == btn_stop:
            # Return the stop action
            return "Stop"
        else:
            # Return the cancel action as a default fallback
            return "Cancel"

    """
    /*
     * Updates the selected record by rescanning and copying the latest files from the RootPath.
     */
    """
    # def menu_update_record_logic(self, rec_data):
    #     name = rec_data.get("Name", "Unknown Name")
    #     reply = QMessageBox.warning(
    #         self, 'Confirm Update', 
    #         f"WARNING: This action will overwrite the current archived files for '{name}' with the latest files from the RootPath.\nDo you want to proceed?",
    #         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
    #     )
        
    #     # Verify if the user confirmed the overwrite warning
    #     if reply != QMessageBox.StandardButton.Yes:
    #         # Return early to abort the update operation
    #         return
            
    #     root_path = rec_data.get("RootPath", "")
    #     # Validate that the root path exists
    #     if not root_path or not os.path.exists(root_path):
    #         QMessageBox.critical(self, "Error", "RootPath is missing or does not exist!")
    #         # Return early if validation fails
    #         return
            
    #     record_folder = rec_data["_folder"]
    #     rel_list = rec_data.get("RelativePathList", [])
    #     new_rel_list = []
        
    #     progress = QProgressDialog("Updating files...", "Cancel", 0, len(rel_list), self)
    #     progress.setWindowTitle("Update Record")
    #     progress.setWindowModality(Qt.WindowModality.WindowModal)
        
    #     stop_update = False
        
    #     # Iterate over all tracked relative paths
    #     for i, rel in enumerate(rel_list):
    #         # Check if the user previously requested to stop further updates
    #         if stop_update:
    #             new_rel_list.append(rel)
    #             # Continue bypassing remaining files
    #             continue
                
    #         # Check if the overall progress dialog was cancelled
    #         if progress.wasCanceled():
    #             QMessageBox.warning(self, "Cancelled", "Update cancelled by user. Partial updates may have occurred.")
    #             # Return immediately to halt the process
    #             return
                
    #         progress.setValue(i)
    #         progress.setLabelText(f"Updating: {rel}")
    #         QApplication.processEvents()
            
    #         src = os.path.join(root_path, rel)
    #         dest = os.path.join(record_folder, rel)
            
    #         # Verify if the source file is missing from the disk
    #         if not os.path.exists(src):
    #             ans = self.prompt_missing_file_dialog(src)
                
    #             # Evaluate the user's decision for the missing file
    #             if ans == "Remove":
    #                 # Check if the target destination exists in the archive
    #                 if os.path.exists(dest):
    #                     # Determine if the destination is a directory
    #                     if os.path.isdir(dest):
    #                         shutil.rmtree(dest)
    #                     else:
    #                         os.remove(dest)
    #                 # Continue iteration without adding to the new list
    #                 continue
    #             elif ans == "Skip":
    #                 new_rel_list.append(rel)
    #                 # Continue to the next item
    #                 continue
    #             elif ans == "Stop":
    #                 new_rel_list.append(rel)
    #                 stop_update = True
    #                 # Continue to the next item
    #                 continue
    #             else:
    #                 QMessageBox.warning(self, "Cancelled", "Update cancelled by user. Operation aborted.")
    #                 # Return to fully abort the update logic
    #                 return
    #         else:
    #             try:
    #                 # Evaluate if the source is a directory for appropriate copying
    #                 if os.path.isdir(src):
    #                     # Verify destination existence to clear old directory tree
    #                     if os.path.exists(dest):
    #                         shutil.rmtree(dest)
    #                     shutil.copytree(src, dest, dirs_exist_ok=True)
    #                 else:
    #                     os.makedirs(os.path.dirname(dest), exist_ok=True)
    #                     shutil.copy2(src, dest)
    #                 new_rel_list.append(rel)
    #             except Exception as e:
    #                 QMessageBox.warning(self, "Copy Error", f"Failed to copy {src}:\n{e}")
    #                 new_rel_list.append(rel)
                    
    #     progress.setValue(len(rel_list))
        
    #     yml_path = rec_data["_yml"]
    #     try:
    #         with open(yml_path, "r", encoding="utf-8") as f:
    #             raw_data = yaml.safe_load(f)
                
    #         current_time = datetime.now().strftime("%Y/%m/%d-%H:%M:%S")
            
    #         # Iterate through the GeneralInfo mapping in YAML
    #         for item in raw_data.get("GeneralInfo", []):
    #             # Check for list key to replace values
    #             if "RelativePathList" in item:
    #                 item["RelativePathList"] = new_rel_list
    #             # Check for timestamp key to update
    #             if "UpdateRecordTime" in item:
    #                 item["UpdateRecordTime"] = current_time
                    
    #         # Check if UpdateRecordTime is completely missing from the old structure
    #         if not any("UpdateRecordTime" in d for d in raw_data.get("GeneralInfo", [])):
    #             raw_data["GeneralInfo"].append({"UpdateRecordTime": current_time})
                
    #         with open(yml_path, "w", encoding="utf-8") as f:
    #             yaml.dump(raw_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
                
    #         QMessageBox.information(self, "Success", "Record has been successfully updated!")
    #         self.scan_storage_to_ram()
            
    #     except Exception as e:
    #         QMessageBox.critical(self, "YAML Error", f"Failed to save updated record metadata:\n{e}")

    def menu_update_record_logic(self, rec_data):
        name = rec_data.get("Name", "Unknown Name")
        reply = QMessageBox.warning(
            self, 'Confirm Update', 
            f"WARNING: This action will overwrite the current archived files for '{name}' with the latest files from the RootPath.\nDo you want to proceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        
        # Verify if the user confirmed the overwrite warning
        if reply != QMessageBox.StandardButton.Yes:
            # Return early to abort the update operation
            return
            
        root_path = rec_data.get("RootPath", "")
        # Validate that the root path exists
        if not root_path or not os.path.exists(root_path):
            QMessageBox.critical(self, "Error", "RootPath is missing or does not exist!")
            # Return early if validation fails
            return
            
        record_folder = rec_data["_folder"]
        rel_list = rec_data.get("RelativePathList", [])
        new_rel_list = []
        
        # Initialize tracking lists for the final report dialog
        updated_files = []
        skipped_files = []
        removed_files = []
        
        progress = QProgressDialog("Updating files...", "Cancel", 0, len(rel_list), self)
        progress.setWindowTitle("Update Record")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        
        stop_update = False
        
        # Iterate over all tracked relative paths
        # for i, rel in enumerate(rel_list):
        #     # Check if the user previously requested to stop further updates
        #     if stop_update:
        #         new_rel_list.append(rel)
        #         skipped_files.append(rel)
        #         # Continue bypassing remaining files
        #         continue
                
        #     # Check if the overall progress dialog was cancelled
        #     if progress.wasCanceled():
        #         QMessageBox.warning(self, "Cancelled", "Update cancelled by user. Partial updates may have occurred.")
        #         # Return immediately to halt the process
        #         return
                
        #     progress.setValue(i)
        #     progress.setLabelText(f"Updating: {rel}")
        #     QApplication.processEvents()
            
        #     src = os.path.join(root_path, rel)
        #     dest = os.path.join(record_folder, rel)
            
        #     # Verify if the source file is missing from the disk
        #     if not os.path.exists(src):
        #         ans = self.prompt_missing_file_dialog(src)
                
        #         # Evaluate the user's decision for the missing file
        #         if ans == "Remove":
        #             # Check if the target destination exists in the archive
        #             if os.path.exists(dest):
        #                 # Determine if the destination is a directory
        #                 if os.path.isdir(dest):
        #                     shutil.rmtree(dest)
        #                 else:
        #                     os.remove(dest)
        #             removed_files.append(rel)
        #             # Continue iteration without adding to the new list
        #             continue
        #         elif ans == "Skip":
        #             new_rel_list.append(rel)
        #             skipped_files.append(rel)
        #             # Continue to the next item
        #             continue
        #         elif ans == "Stop":
        #             new_rel_list.append(rel)
        #             skipped_files.append(rel)
        #             stop_update = True
        #             # Continue to the next item
        #             continue
        #         else:
        #             QMessageBox.warning(self, "Cancelled", "Update cancelled by user. Operation aborted.")
        #             # Return to fully abort the update logic
        #             return
        #     else:
        #         try:
        #             # Evaluate if the source is a directory for appropriate copying
        #             if os.path.isdir(src):
        #                 # Verify destination existence to clear old directory tree
        #                 if os.path.exists(dest):
        #                     shutil.rmtree(dest)
        #                 shutil.copytree(src, dest, dirs_exist_ok=True)
        #             else:
        #                 os.makedirs(os.path.dirname(dest), exist_ok=True)
        #                 shutil.copy2(src, dest)
                    
        #             new_rel_list.append(rel)
        #             updated_files.append(rel)
        #         except Exception as e:
        #             QMessageBox.warning(self, "Copy Error", f"Failed to copy {src}:\n{e}")
        #             new_rel_list.append(rel)
        #             skipped_files.append(rel)

        # Iterate over all tracked relative paths
        for i, rel in enumerate(rel_list):
            # Check if the user previously requested to stop further updates
            if stop_update:
                new_rel_list.append(rel)
                skipped_files.append(rel)
                # Continue bypassing remaining files
                continue
                
            # Check if the overall progress dialog was cancelled
            if progress.wasCanceled():
                QMessageBox.warning(progress, "Cancelled", "Update cancelled by user. Partial updates may have occurred.")
                # Return immediately to halt the process
                return
                
            progress.setValue(i)
            progress.setLabelText(f"Updating: {rel}")
            QApplication.processEvents()
            
            src = os.path.join(root_path, rel)
            dest = os.path.join(record_folder, rel)
            
            # Verify if the source file is missing from the disk
            if not os.path.exists(src):
                # Pass 'progress' as parent to avoid UI deadlock
                ans = self.prompt_missing_file_dialog(src, parent_widget=progress)
                
                # Evaluate the user's decision for the missing file
                if ans == "Remove":
                    # Check if the target destination exists in the archive
                    if os.path.exists(dest):
                        # Determine if the destination is a directory
                        if os.path.isdir(dest):
                            shutil.rmtree(dest)
                        else:
                            os.remove(dest)
                    removed_files.append(rel)
                    # Continue iteration without adding to the new list
                    continue
                elif ans == "Skip":
                    new_rel_list.append(rel)
                    skipped_files.append(rel)
                    # Continue to the next item
                    continue
                elif ans == "Stop":
                    new_rel_list.append(rel)
                    skipped_files.append(rel)
                    stop_update = True
                    # Continue to the next item
                    continue
                else:
                    QMessageBox.warning(progress, "Cancelled", "Update cancelled by user. Operation aborted.")
                    # Return to fully abort the update logic
                    return
            else:
                try:
                    # Evaluate if the source is a directory for appropriate copying
                    if os.path.isdir(src):
                        # Verify destination existence to clear old directory tree
                        if os.path.exists(dest):
                            shutil.rmtree(dest)
                        shutil.copytree(src, dest, dirs_exist_ok=True)
                    else:
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        shutil.copy2(src, dest)
                    
                    new_rel_list.append(rel)
                    updated_files.append(rel)
                except Exception as e:
                    # Pass 'progress' as parent for copy error popup
                    QMessageBox.warning(progress, "Copy Error", f"Failed to copy {src}:\n{e}")
                    new_rel_list.append(rel)
                    skipped_files.append(rel)

        progress.setValue(len(rel_list))
        
        yml_path = rec_data["_yml"]
        try:
            with open(yml_path, "r", encoding="utf-8") as f:
                raw_data = yaml.safe_load(f)
                
            current_time = datetime.now().strftime("%Y/%m/%d-%H:%M:%S")
            
            # Iterate through the GeneralInfo mapping in YAML
            for item in raw_data.get("GeneralInfo", []):
                # Check for list key to replace values
                if "RelativePathList" in item:
                    item["RelativePathList"] = new_rel_list
                # Check for timestamp key to update
                if "UpdateRecordTime" in item:
                    item["UpdateRecordTime"] = current_time
                    
            # Check if UpdateRecordTime is completely missing from the old structure
            if not any("UpdateRecordTime" in d for d in raw_data.get("GeneralInfo", [])):
                raw_data["GeneralInfo"].append({"UpdateRecordTime": current_time})
                
            with open(yml_path, "w", encoding="utf-8") as f:
                yaml.dump(raw_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
                
            # Compile the comprehensive result message for the user
            result_msg = f"Record '{name}' update completed!\n\n"
            result_msg += f"✅ Updated: {len(updated_files)} item(s)\n"
            result_msg += f"⏭ Skipped: {len(skipped_files)} item(s)\n"
            result_msg += f"🗑 Removed: {len(removed_files)} item(s)\n"
            
            # Append detailed updated files if any exist
            if updated_files:
                result_msg += "\n[Updated Files]\n" + "\n".join(updated_files[:5])
                # Check if file count exceeds display limit
                if len(updated_files) > 5: 
                    result_msg += f"\n... and {len(updated_files) - 5} more."
                    
            # Append detailed removed files if any exist
            if removed_files:
                result_msg += "\n\n[Removed Files]\n" + "\n".join(removed_files[:5])
                # Check if file count exceeds display limit
                if len(removed_files) > 5: 
                    result_msg += f"\n... and {len(removed_files) - 5} more."
                
            QMessageBox.information(self, "Update Results", result_msg)
            self.scan_storage_to_ram()
            
        except Exception as e:
            QMessageBox.critical(self, "YAML Error", f"Failed to save updated record metadata:\n{e}")

    # ---------------- CONTEXT MENU ----------------
    """
    /*
     * Handles right-click events on the records table.
     */
    """
    def open_custom_context_menu(self, pos):
        item = self.View_AllRecordsTable.itemAt(pos)
        # Detect void click behavior
        if not item: 
            # Return operation termination
            return
        
        root_item = item if item.parent() is None else item.parent()
        rec_data = root_item.data(0, Qt.ItemDataRole.UserRole)
        # Detect void raw properties
        if not rec_data: 
            # Return operation termination
            return

        menu = QMenu(self)
        
        act_select = QAction("Select this record", self)
        act_deselect = QAction("De-select this record", self)
        act_edit = QAction("Edit record", self)
        act_update = QAction("Update this record", self)
        act_delete = QAction("Delete record", self)
        act_hide = QAction("Remove record from table", self)

        act_select.triggered.connect(lambda: self.menu_select_record_logic(root_item, rec_data))
        act_deselect.triggered.connect(lambda: self.menu_deselect_record_logic(root_item))
        act_edit.triggered.connect(lambda: self.menu_edit_yaml_sync_logic(rec_data))
        act_update.triggered.connect(lambda: self.menu_update_record_logic(rec_data))
        act_delete.triggered.connect(lambda: self.menu_delete_record_from_disk(rec_data))
        act_hide.triggered.connect(lambda: self.menu_hide_record_temporary(rec_data))

        menu.addAction(act_select)
        menu.addAction(act_deselect)
        menu.addSeparator()
        menu.addAction(act_edit)
        menu.addAction(act_update)
        menu.addSeparator()
        menu.addAction(act_delete)
        menu.addAction(act_hide)

        menu.exec(self.View_AllRecordsTable.viewport().mapToGlobal(pos))

    """
    /*
     * Highlights a record, moves it to top, enables multi-select tracking.
     */
    """
    def menu_select_record_logic(self, tree_item, rec_data):
        # Evaluate item redundancy tracking mapping
        if tree_item not in self.selected_records_ui:
            self.selected_records_ui.append(tree_item)
            self.selected_records_data.append(rec_data)
            self.apply_row_light_mode_color(tree_item, highlight=True)
            
            # parent = self.View_AllRecordsTable.invisibleRootItem()
            # index = parent.indexOfChild(tree_item)
            # # Guarantee item movement sequence logic
            # if index > 0:
            #     taken_item = parent.takeChild(index)
            #     parent.insertChild(0, taken_item)
            
            self.View_Path2PatchFolder_Value.setText(rec_data.get("RootPath", ""))

    """
    /*
     * Clears the active selection state and removes from multi-select.
     */
    """
    def menu_deselect_record_logic(self, tree_item):
        self.apply_row_light_mode_color(tree_item, highlight=False)
        # Assure correct list item indexing sequence
        if tree_item in self.selected_records_ui:
            idx = self.selected_records_ui.index(tree_item)
            self.selected_records_ui.pop(idx)
            self.selected_records_data.pop(idx)
            
            # Conditionally override path configuration input
            if not self.selected_records_data:
                self.View_Path2PatchFolder_Value.clear()
            else:
                self.View_Path2PatchFolder_Value.setText(self.selected_records_data[-1].get("RootPath", ""))

    """
    /*
     * Hides the record from the current table view (RAM only).
     */
    """
    def menu_hide_record_temporary(self, rec_data):
        self.hidden_folders.add(rec_data["_folder"])
        self.render_records_to_tree_view(self.records)

    """
    /*
     * Irreversibly deletes the record folder and its metadata from the storage drive.
     */
    """
    def menu_delete_record_from_disk(self, rec_data):
        name = rec_data.get("Name", "Unknown Name")
        reply = QMessageBox.question(
            self, 'Confirm Record Deletion', 
            f"This action cannot be undone!\nAre you sure you want to PERMANENTLY DELETE record: '{name}' from disk?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        
        # Branch validation parameter path logic
        if reply == QMessageBox.StandardButton.Yes:
            self.delete_progress_dialog = QProgressDialog(f"Deleting record '{name}'...", None, 0, 0, self)
            self.delete_progress_dialog.setWindowTitle("Deletion in Progress")
            self.delete_progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            self.delete_progress_dialog.setCancelButton(None) 
            
            # Loop interface label modification configuration
            for label in self.delete_progress_dialog.findChildren(QLabel):
                label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

            self.delete_worker = DeleteWorker(rec_data["_folder"])
            self.delete_worker.finished.connect(lambda success, msg: self.delete_finished(success, msg, name))
            self.delete_worker.start()

            self.delete_progress_dialog.exec()

    """
    /*
     * Handles the completion of the delete worker thread.
     */
    """
    def delete_finished(self, success, msg, record_name):
        self.delete_progress_dialog.close()
        # Verify success path routing execution
        if success:
            self.scan_storage_to_ram()
            QMessageBox.information(self, "Success", f"Record '{record_name}' has been completely removed!")
        else:
            QMessageBox.critical(self, "Delete Error", msg)
            self.scan_storage_to_ram()

    """
    /*
     * Smart Sync mode: Opens YAML for manual editing, then diffs the file list.
     */
    """
    def menu_edit_yaml_sync_logic(self, rec_data):
        yml_path = rec_data["_yml"]
        
        # Test execution OS environment routing
        if sys.platform.startswith('win'):
            os.startfile(yml_path)
        elif sys.platform.startswith('darwin'):
            subprocess.call(('open', yml_path))
        else:
            subprocess.call(('xdg-open', yml_path))
            
        QMessageBox.information(
            self, "Sync Mode", 
            "The YAML file has been opened.\nPlease edit, Save (Ctrl+S), CLOSE THE EDITOR, and then click OK here to proceed with synchronization."
        )
        
        try:
            with open(yml_path, "r", encoding="utf-8") as f:
                new_data = yaml.safe_load(f)
            new_info = self.extract_yaml_info(new_data)
            
            old_files = set(rec_data.get("RelativePathList", []))
            new_files = set(new_info.get("RelativePathList", []))
            
            added_files = new_files - old_files
            removed_files = old_files - new_files
            
            record_folder = rec_data["_folder"]
            original_root = new_info.get("RootPath", "")
            sync_log = []
            
            # Loop file validation deletion
            for rf in removed_files:
                target = os.path.join(record_folder, rf)
                # Ensure physical representation configuration
                if os.path.exists(target):
                    # Validate object logic layout parameter
                    if os.path.isdir(target): 
                        shutil.rmtree(target)
                    else: 
                        os.remove(target)
                    sync_log.append(f"🗑 Deleted from archive: {rf}")
                    
            # Loop file configuration propagation
            for af in added_files:
                src = os.path.join(original_root, af)
                dest = os.path.join(record_folder, af)
                # Verify local file presence
                if os.path.exists(src):
                    # Verify file system hierarchy properties
                    if af.endswith('/') or os.path.isdir(src):
                        shutil.copytree(src, dirs_exist_ok=True)
                    else:
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        shutil.copy2(src, dest)
                    sync_log.append(f"📥 Added new file to archive: {af}")
                else:
                    sync_log.append(f"❌ Failed: Source not found for: {af}")

            # Notify user execution status route
            if sync_log:
                QMessageBox.information(self, "YAML Sync Results", "\n".join(sync_log))
            
            self.scan_storage_to_ram()
        except Exception as e:
            QMessageBox.critical(self, "Sync Error", f"An error occurred during structure sync: {str(e)}")

    # ---------------- DATA RESTORATION (PASTE / PATCH) ----------------
    """
    /*
     * Restores sequentially multiple selected records to a specified destination.
     */
    """
    def execute_paste_patch_logic(self):
        # Abort action parameter constraints
        if not self.selected_records_data:
            QMessageBox.warning(self, "No Record Selected", "Please right-click and 'Select this record' before pasting.")
            # Break operational branch
            return

        user_paste_path = self.View_Path2PatchFolder_Value.text().strip().strip('"').strip("'")
        
        skip_all_errors = False
        overwrite_all = False
        restored_count = 0
        total_files = 0

        # Calculate sizing layout requirement logic
        for rec in self.selected_records_data:
            # Check secondary loop structure iteration
            for rel in rec.get("RelativePathList", []):
                src = os.path.join(rec["_folder"], rel)
                # Discriminate system type element path
                if os.path.isdir(src):
                    # Perform node traversal configuration
                    for dirpath, _, filenames in os.walk(src):
                        total_files += len(filenames)
                elif os.path.exists(src):
                    total_files += 1
                
        # Protect division properties
        if total_files == 0:
            total_files = 1

        progress_dialog = QProgressDialog("Restoring files...", "Cancel", 0, total_files, self)
        progress_dialog.setWindowTitle("Paste Progress")
        progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog.setMinimumDuration(0)
        progress_dialog.setValue(0)

        # Alter visual attributes operation layout
        for label in progress_dialog.findChildren(QLabel):
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        processed_count = 0

        # Main configuration mapping iterator phase
        for rec in self.selected_records_data:
            current_paste_path = user_paste_path
            # Verify explicit operational paths map
            if not current_paste_path:
                current_paste_path = rec.get("RootPath", "")
                # Double guard void location sequence path
                if not current_paste_path:
                    # Proceed loop skip directive instruction
                    continue
                    
            # Confirm destination directory state layout
            if not os.path.exists(current_paste_path):
                os.makedirs(current_paste_path, exist_ok=True)

            record_folder = rec["_folder"]
            # Initiate secondary processing payload iter loop
            for rel in rec.get("RelativePathList", []):
                src = os.path.join(record_folder, rel)
                dest = os.path.join(current_paste_path, rel)

                # Skip invalid source property path evaluation
                if not os.path.exists(src):
                    # Advance iteration loop process command
                    continue

                # Confirm directory logic evaluation branch instruction
                if os.path.isdir(src):
                    # Start node payload evaluation command
                    for dirpath, _, filenames in os.walk(src):
                        # Proceed processing element iteration map
                        for fname in filenames:
                            # Verify dialog abort mechanism path property
                            if progress_dialog.wasCanceled():
                                QMessageBox.warning(self, "Cancelled", "Paste operation cancelled by user.")
                                # Break explicit loop function route
                                return

                            s_file = os.path.join(dirpath, fname)
                            rel_to_src = os.path.relpath(s_file, src)
                            d_file = os.path.join(dest, rel_to_src)
                            
                            progress_dialog.setLabelText(f"Restoring: {fname}")
                            QApplication.processEvents()

                            # Manage replacement scenario confirmation path instruction
                            if os.path.exists(d_file) and not overwrite_all:
                                ans = self.prompt_overwrite_confirmation_dialog(d_file)
                                # Define conditional replacement properties state layout
                                if ans == QMessageBox.StandardButton.YesToAll: 
                                    overwrite_all = True
                                elif ans == QMessageBox.StandardButton.Cancel: 
                                    progress_dialog.close()
                                    # Terminate method branch flow route
                                    return
                                elif ans == QMessageBox.StandardButton.No: 
                                    processed_count += 1
                                    progress_dialog.setValue(processed_count)
                                    # Continue node execution command instruction
                                    continue
                                    
                            # Initiate dynamic action execution retry logic map
                            while True:
                                try:
                                    os.makedirs(os.path.dirname(d_file), exist_ok=True)
                                    shutil.copy2(s_file, d_file)
                                    restored_count += 1
                                    # Interrupt iteration safely layout parameter
                                    break
                                except Exception as e:
                                    # Verify explicit ignore directive state properties
                                    if skip_all_errors:
                                        # Force loop logic exit parameter map
                                        break
                                    ans = self.prompt_copy_error_dialog(s_file, str(e))
                                    # Test discrete conditional fallback execution route
                                    if ans == "Skip":
                                        # Bypass execution layout node instruction
                                        break
                                    elif ans == "SkipAll":
                                        skip_all_errors = True
                                        # Break internal evaluation state mapping
                                        break
                                    elif ans == "Abort":
                                        progress_dialog.close()
                                        QMessageBox.warning(self, "Aborted", "Paste operation aborted due to error.")
                                        # Halt thread return command path property
                                        return
                            processed_count += 1
                            progress_dialog.setValue(processed_count)
                else:
                    # Detect cancellation property state loop map
                    if progress_dialog.wasCanceled():
                        QMessageBox.warning(self, "Cancelled", "Paste operation cancelled by user.")
                        # Abort operation function branch route instruction
                        return

                    progress_dialog.setLabelText(f"Restoring: {os.path.basename(src)}")
                    QApplication.processEvents()

                    # Confirm object conflict path map parameters
                    if os.path.exists(dest) and not overwrite_all:
                        ans = self.prompt_overwrite_confirmation_dialog(dest)
                        # Route evaluation mapping configuration node
                        if ans == QMessageBox.StandardButton.YesToAll: 
                            overwrite_all = True
                        elif ans == QMessageBox.StandardButton.Cancel: 
                            progress_dialog.close()
                            # Release payload execution return instruction parameter
                            return
                        elif ans == QMessageBox.StandardButton.No: 
                            processed_count += 1
                            progress_dialog.setValue(processed_count)
                            # Shift operational iteration step constraint command
                            continue

                    # Safe handling logic layout retry properties map
                    while True:
                        try:
                            os.makedirs(os.path.dirname(dest), exist_ok=True)
                            shutil.copy2(src, dest)
                            restored_count += 1
                            # Break cycle path parameter loop constraint
                            break
                        except Exception as e:
                            # Implement exception bypass layout route instruction
                            if skip_all_errors:
                                # Stop cycle logic execution mapping state
                                break
                            ans = self.prompt_copy_error_dialog(src, str(e))
                            # Follow fallback node constraints operation layout
                            if ans == "Skip":
                                # Abort evaluation sequence loop path mapping
                                break
                            elif ans == "SkipAll":
                                skip_all_errors = True
                                # Stop exception sequence propagation parameter route
                                break
                            elif ans == "Abort":
                                progress_dialog.close()
                                QMessageBox.warning(self, "Aborted", "Paste operation aborted due to error.")
                                # Leave functional map execution layer property constraint
                                return
                                
                    processed_count += 1
                    progress_dialog.setValue(processed_count)
        
        progress_dialog.close()
        
        QMessageBox.information(
            self, "Restore Successful", 
            f"Paste operation finished.\nSuccessfully restored {restored_count} components into:\n{user_paste_path}"
        )

    """
    /*
     * Displays a dialog asking user how to handle existing files.
     */
    """
    def prompt_overwrite_confirmation_dialog(self, filepath):
        msg = QMessageBox(self)
        msg.setWindowTitle("File Already Exists")
        msg.setText(f"Duplicate file structure detected at target:\n{filepath}\n\nDo you want to overwrite this data?")
        msg.setStandardButtons(
            QMessageBox.StandardButton.Yes | 
            QMessageBox.StandardButton.No | 
            QMessageBox.StandardButton.YesToAll | 
            QMessageBox.StandardButton.Cancel
        )
        msg.setDefaultButton(QMessageBox.StandardButton.Yes)
        # Finalize message prompt operation sequence logic
        return msg.exec()

    """
    /*
     * Presents error dialog allowing retry, ignore or abort sequences.
     */
    """
    def prompt_copy_error_dialog(self, filepath, error_msg):
        msg = QMessageBox(self)
        msg.setWindowTitle("Copy Error")
        msg.setText(f"Failed to copy:\n{filepath}\n\nError: {error_msg}")
        msg.setStandardButtons(
            QMessageBox.StandardButton.Retry | 
            QMessageBox.StandardButton.Ignore | 
            QMessageBox.StandardButton.Abort
        )
        skip_all_button = msg.addButton("Skip All", QMessageBox.ButtonRole.ActionRole)
        msg.setDefaultButton(QMessageBox.StandardButton.Retry)
        msg.exec()

        clicked_button = msg.clickedButton()
        # Verify node bypass confirmation layout sequence constraint map
        if clicked_button == skip_all_button:
            # Return sequence logic path string parameter evaluation
            return "SkipAll"

        standard_button = msg.standardButton(clicked_button)
        # Evaluate standard node action confirmation path map route
        if standard_button == QMessageBox.StandardButton.Ignore:
            # Yield functional map string parameter constraint command
            return "Skip"
        elif standard_button == QMessageBox.StandardButton.Abort:
            # Send abort route sequence operation parameter logic string
            return "Abort"
        
        # Fallback operation path cycle layout node string constraint
        return "Retry"

# Evaluate root execution script sequence property path
if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Configure interface style constraint evaluation map parameter
    app.setStyle("Fusion") 
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.black)
    palette.setColor(QPalette.ColorRole.Base, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(240, 240, 240))
    palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.black)
    palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.black)
    palette.setColor(QPalette.ColorRole.Button, QColor(240, 240, 240))
    palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.black)
    palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
    palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)
    app.setPalette(palette)
    
    window = StasherApp()
    window.show()
    sys.exit(app.exec())