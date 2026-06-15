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
    QTextEdit, QProgressDialog, QLabel
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QAction

# Import UI classes compiled from the respective .ui files
from stasher_ui import Ui_StasherMain
from stasher_newrecord_ui import Ui_NewRecord

CONFIG_FILE = "stasher_config.json"
DEFAULT_STORAGE = r"C:\Users\phu.nguyen-thanh\Documents\UserData"


# ---------------- SYSTEM CONFIGURATION ----------------
def load_config():
    """Loads application configuration from a JSON file, creating defaults if missing."""
    if not os.path.exists(CONFIG_FILE):
        default = {"PATH_STORAGE": DEFAULT_STORAGE}
        with open(CONFIG_FILE, "w", encoding='utf-8') as f:
            json.dump(default, f, indent=4)
        return default

    with open(CONFIG_FILE, "r", encoding='utf-8') as f:
        try:
            return json.load(f)
        except Exception:
            return {"PATH_STORAGE": DEFAULT_STORAGE}


# ---------------- WORKER THREAD ----------------
class BackupWorker(QThread):
    progress = Signal(int, str)
    finished = Signal(bool, str)
    ask_error = Signal(str, str)

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

    def cancel(self):
        self._is_cancelled = True

    def set_error_action(self, action):
        self.error_action = action
        self.sync_event.set()

    def run(self):
        try:
            folder_name = f"Record_{datetime.now().strftime('%Y_%B_%d_%H%M%S')}"
            record_path = os.path.join(self.storage_path, folder_name)
            os.makedirs(record_path, exist_ok=True)
            
            self.progress.emit(0, "Calculating files...")
            total_files = 0
            for rel in self.relative_list:
                src = os.path.join(self.root_path, rel)
                if rel.endswith('/') or os.path.isdir(src):
                    for dirpath, _, filenames in os.walk(src):
                        total_files += len(filenames)
                else:
                    total_files += 1

            if total_files == 0:
                total_files = 1
                
            copied_files = 0

            def safe_copy(src_file, dst_file):
                while True:
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
                        break
                    except Exception as e:
                        if self.skip_all_errors:
                            break
                        self.sync_event.clear()
                        self.ask_error.emit(src_file, str(e))
                        self.sync_event.wait()
                        if self.error_action == "Abort":
                            raise Exception(f"Aborted by user due to error: {e}")
                        elif self.error_action == "Skip":
                            break
                        elif self.error_action == "SkipAll":
                            self.skip_all_errors = True
                            break

            for rel in self.relative_list:
                if self._is_cancelled:
                    raise Exception("Backup cancelled by user.")
                src = os.path.join(self.root_path, rel)
                dest = os.path.join(record_path, rel)
                try:
                    if rel.endswith('/') or os.path.isdir(src):
                        shutil.copytree(src, dest, copy_function=safe_copy, dirs_exist_ok=True)
                    else:
                        safe_copy(src, dest)
                except Exception as e:
                    if "Aborted by user" in str(e):
                        raise Exception("Backup cancelled by user.")
                    if not self.skip_all_errors:
                        self.sync_event.clear()
                        self.ask_error.emit(src, str(e))
                        self.sync_event.wait()
                        if self.error_action == "Abort":
                            raise Exception(f"Aborted by user due to error: {e}")
                        elif self.error_action == "SkipAll":
                            self.skip_all_errors = True

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
            # Clean up partial backup directory if canceled
            if self._is_cancelled and os.path.exists(record_path):
                try:
                    shutil.rmtree(record_path)
                except Exception:
                    pass
            self.finished.emit(False, str(e))


# ---------------- DELETE WORKER THREAD ----------------
class DeleteWorker(QThread):
    finished = Signal(bool, str)

    def __init__(self, folder_path):
        super().__init__()
        self.folder_path = folder_path

    def run(self):
        try:
            shutil.rmtree(self.folder_path)
            self.finished.emit(True, "Record deleted successfully.")
        except Exception as e:
            self.finished.emit(False, f"Could not delete record: {str(e)}")


# ---------------- NEW RECORD DIALOG ----------------
class NewRecordDialog(QDialog, Ui_NewRecord):
    def __init__(self, storage_path):
        super().__init__()
        self.setupUi(self)
        self.storage_path = storage_path
        self.setAcceptDrops(True) # Enable drag-and-drop

        # Initialize a string container for the circular log buffer
        self.status_buffer = ""

        # Dynamically replace QLabel with QTextEdit to enable scrolling automatically
        geo = self.NewRecord_Label_RecentlyStatus.geometry()
        parent = self.NewRecord_Label_RecentlyStatus.parentWidget()
        self.NewRecord_Label_RecentlyStatus.deleteLater() # Clean up the old label

        self.NewRecord_Label_RecentlyStatus = QTextEdit(parent)
        self.NewRecord_Label_RecentlyStatus.setGeometry(geo)
        self.NewRecord_Label_RecentlyStatus.setReadOnly(True)
        # Match the standard box frame style
        self.NewRecord_Label_RecentlyStatus.setStyleSheet(
            "QTextEdit { "
                "border: 1px solid #555555; "
                "background-color: #2b2b2b; "
                "color: #ffffff; "
                "}"
        )

        # Variables to store Record configuration state in RAM
        self.record_name = "Unnamed Record"
        self.record_desc = ""
        self.root_path = ""
        self.relative_list = []  # Stores relative paths (or temporary absolute paths if root isn't set)

        # Configure data tree table display
        self.View_AllRecordsTable.clear()
        self.View_AllRecordsTable.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        
        # Enable custom context menu for the new record tree view
        self.View_AllRecordsTable.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.View_AllRecordsTable.customContextMenuRequested.connect(self.open_custom_context_menu)

        # Bind UI control button events
        self.NewRecord_Button_SetName.clicked.connect(self.set_record_name_from_input)
        self.NewRecord_Button_SetDesc.clicked.connect(self.set_record_desc_from_input)
        self.NewRecord_Button_SetAsRootPath.clicked.connect(self.set_root_path_logic)
        self.NewRecord_Button_AddFileOrFolder.clicked.connect(self.add_path_logic)
        self.NewRecord_Button_Undo.clicked.connect(self.undo_last_action)
        
        self.update_status_bar("Ready. Please set Name, Description, Root Path, and add data files.")

    # def update_status_bar(self, msg):
    #     """Updates the status label at the bottom of the dialog."""
    #     self.NewRecord_Label_RecentlyStatus.setText(msg)

    def update_status_bar(self, msg):
        """Updates the status log view using a circular buffer capped at 2045 characters."""
        # Append new messages into a running newline history log
        if self.status_buffer:
            self.status_buffer += "\n" + msg
        else:
            self.status_buffer = msg

        # Enforce circular buffer boundary: keep only the most recent 2045 characters
        if len(self.status_buffer) > 2045:
            self.status_buffer = self.status_buffer[-2045:]

        # Since QTextEdit supports .setText(), existing features remain fully functional
        self.NewRecord_Label_RecentlyStatus.setText(self.status_buffer)

        # Auto-scroll to the absolute bottom when new text rolls in
        scrollbar = self.NewRecord_Label_RecentlyStatus.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def refresh_table_view(self):
        """Refreshes the TreeWidget display based on current RAM state."""
        self.View_AllRecordsTable.clear()
        for i, p in enumerate(self.relative_list):
            item_type = "Folder" if p.endswith("/") else "File"
            name = os.path.basename(p.strip("/"))
            item = QTreeWidgetItem([str(i + 1), name, item_type, p])
            
            # Show root path when hover (Tooltip)
            full_p = os.path.join(self.root_path, p) if self.root_path else p
            root_tooltip = f"Root Path: {self.root_path}" if self.root_path else "Root Path: Not set"
            for col in range(item.columnCount()):
                item.setToolTip(col, f"{root_tooltip}\nFull Path: {full_p}")

            self.View_AllRecordsTable.addTopLevelItem(item)

    def set_record_name_from_input(self):
        """Sets the record name using the value from the general input field."""
        text = self.NewRecord_YourPath_Value.text().strip()
        if text:
            self.record_name = text
            self.NewRecord_YourPath_Value.clear()
            self.update_status_bar(f"✅ Record name set to: '{self.record_name}'")
        else:
            self.update_status_bar("⚠ Please enter a name in the input box before clicking set name!")

    def set_record_desc_from_input(self):
        """Sets the record description using the value from the general input field."""
        text = self.NewRecord_YourPath_Value.text().strip()
        if text:
            self.record_desc = text
            self.NewRecord_YourPath_Value.clear()
            self.update_status_bar(f"✅ Description set to: '{self.record_desc}'")
        else:
            self.update_status_bar("⚠ Please enter description content in the input box first!")

    def set_root_path_logic(self):
        """
        Logic to define the base directory for relative paths.
        If input is empty, it attempts to calculate a Common Root Path from existing entries.
        """
        path = self.NewRecord_YourPath_Value.text().strip().strip('"').strip("'")
        
        # If input is empty -> Scan list to calculate Common Root
        if not path:
            if not self.relative_list:
                self.update_status_bar("⚠ List is empty. Cannot calculate automatic root directory.")
                return
                
            # Check if current list has any absolute paths to calculate from
            abs_paths = [p for p in self.relative_list if os.path.isabs(p)]
            if not abs_paths:
                self.update_status_bar("⚠ All current paths are already relative. Please enter a specific RootPath.")
                return
                
            try:
                common_root = os.path.commonpath(abs_paths).replace("\\", "/")
                self.root_path = common_root
                
                # Recalculate the entire list based on the newly found Root
                new_list = []
                for p in self.relative_list:
                    if os.path.isabs(p):
                        rel = os.path.relpath(p, self.root_path).replace("\\", "/")
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
            return

        if not os.path.isdir(path):
            self.update_status_bar("❌ RootPath is invalid or directory does not exist.")
            return

        self.root_path = os.path.abspath(path).replace("\\", "/")
        self.update_status_bar(f"✅ RootPath set: {self.root_path}")
        self.NewRecord_YourPath_Value.clear()

    def add_path_logic(self):
        """Adds a file or folder path to the backup list, handling absolute and relative conversions."""
        filepath = self.NewRecord_YourPath_Value.text().strip().strip('"').strip("'")
        if not filepath:
            self.update_status_bar("⚠ The path input field is currently empty.")
            return

        is_absolute = os.path.isabs(filepath)
        full_path = filepath

        if is_absolute:
            if not self.root_path:
                # Automatically set temporary root path using the parent folder of the first file
                self.root_path = os.path.dirname(full_path).replace("\\", "/")
                self.update_status_bar(f"✅ Auto-set RootPath based on file: {self.root_path}")
            
            try:
                common_root = os.path.commonpath([self.root_path, filepath]).replace("\\", "/")
                if os.path.normpath(common_root) != os.path.normpath(self.root_path):
                    # Prompt user to update RootPath if new file is outside current root
                    reply = QMessageBox.question(
                        self, 'Update common RootPath?', 
                        f"Path is outside current root directory.\nCommon folder found: {common_root}\nDo you want to update RootPath for all entries?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes
                    )
                    if reply == QMessageBox.StandardButton.Yes:
                        new_rel_list = []
                        for old_rel in self.relative_list:
                            old_abs = os.path.join(self.root_path, old_rel)
                            new_rel = os.path.relpath(old_abs, common_root).replace("\\", "/")
                            if old_rel.endswith('/'): 
                                new_rel += '/'
                            new_rel_list.append(new_rel)
                        self.relative_list = new_rel_list
                        self.root_path = common_root
                    else:
                        self.update_status_bar("⛔ Cancelled adding file outside RootPath.")
                        return
                rel_path = os.path.relpath(full_path, self.root_path).replace("\\", "/")
            except ValueError:
                self.update_status_bar("❌ File is on a different drive partition. Cannot merge Root Path.")
                return
        else:
            if not self.root_path:
                self.update_status_bar("⚠ Please configure RootPath before entering relative paths!")
                return
            rel_path = filepath
            full_path = os.path.join(self.root_path, rel_path)

        if os.path.exists(full_path):
            standard_rel = rel_path.replace("\\", "/") 
            if os.path.isdir(full_path) and not standard_rel.endswith('/'):
                standard_rel += '/'

            if standard_rel not in self.relative_list:
                self.relative_list.append(standard_rel)
                self.refresh_table_view()
                self.NewRecord_YourPath_Value.clear()
                self.update_status_bar(f"✅ Successfully added: {standard_rel}")
            else:
                self.update_status_bar("⚠ This path already exists in the list.")
        else:
            self.update_status_bar("❌ Failed: File or directory not found in real life.")

    def undo_last_action(self):
        """Removes the last added path from the list."""
        if self.relative_list:
            removed = self.relative_list.pop()
            self.update_status_bar(f"⛔ Undone (Removed item): {removed}")
            self.refresh_table_view()
        else:
            self.update_status_bar("⚠ List is empty, nothing to undo.")
            
    def open_custom_context_menu(self, pos):
        """Handles right-click events on the New Record table."""
        item = self.View_AllRecordsTable.itemAt(pos)
        if not item:
            return

        idx = self.View_AllRecordsTable.indexOfTopLevelItem(item)
        if idx < 0 or idx >= len(self.relative_list):
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

    def remove_item_from_list(self, idx):
        """Removes a specific item from the new record file list."""
        if 0 <= idx < len(self.relative_list):
            removed = self.relative_list.pop(idx)
            self.update_status_bar(f"⛔ Removed item: {removed}")
            self.refresh_table_view()

    def force_recalculate_root_path(self):
        """Calculates the longest shared path among all recorded files as the Root Path."""
        if not self.relative_list:
            self.update_status_bar("⚠ List is empty. Cannot update root directory.")
            return
            
        abs_paths = []
        for p in self.relative_list:
            if os.path.isabs(p):
                abs_paths.append(p)
            elif self.root_path:
                abs_paths.append(os.path.join(self.root_path, p).replace("\\", "/"))
        
        if not abs_paths:
            self.update_status_bar("⚠ No valid paths to calculate root.")
            return

        try:
            common_root = os.path.commonpath(abs_paths).replace("\\", "/")
            self.root_path = common_root
            
            new_list = []
            for p in abs_paths:
                rel = os.path.relpath(p, self.root_path).replace("\\", "/")
                if p.endswith('/') or os.path.isdir(p):
                    rel += '/'
                new_list.append(rel)
                
            self.relative_list = new_list
            self.refresh_table_view()
            self.update_status_bar(f"✅ RootPath updated to longest shared path: {self.root_path}")
        except Exception as e:
            self.update_status_bar(f"❌ Failed to update RootPath: {str(e)}")

    def dragEnterEvent(self, event):
        """Accepts drag events if they contain file paths."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event):
        """Handles dropped files by adding them to the record list."""
        urls = event.mimeData().urls()
        if urls:
            event.acceptProposedAction()
            # Process all dropped files/folders
            for url in urls:
                path = url.toLocalFile()
                if os.path.exists(path):
                    # This simulates the user typing the path and clicking "Add"
                    self.NewRecord_YourPath_Value.setText(path)
                    self.add_path_logic()
            # Clear the input box after processing all dropped items
            self.NewRecord_YourPath_Value.clear()
        else:
            super().dropEvent(event)

    def accept(self):
        """Executes the actual backup process: creating folders, copying data, and saving metadata."""
        if not self.relative_list:
            QMessageBox.warning(self, "Data Error", "File list is empty. Cannot proceed with backup.")
            return
        if not self.root_path:
            QMessageBox.warning(self, "Config Error", "Please verify a valid RootPath before finishing.")
            return

        self.progress_dialog = QProgressDialog("Calculating files...", "Cancel", 0, 100, self)
        self.progress_dialog.setWindowTitle("Backup Progress")
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setAutoClose(False)
        self.progress_dialog.setAutoReset(False)
        self.progress_dialog.setValue(0)
        self.progress_dialog.setMinimumDuration(0) # Show immediately
        
        # Make the progress log text selectable so it can be copied
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
        if clicked_button == skip_all_button:
            self.worker.set_error_action("SkipAll")
        else:
            standard_button = msg.standardButton(clicked_button)
            if standard_button == QMessageBox.StandardButton.Ignore:
                self.worker.set_error_action("Skip")
            elif standard_button == QMessageBox.StandardButton.Abort:
                self.worker.set_error_action("Abort")
            else: # Default to Retry
                self.worker.set_error_action("Retry")

    def update_progress(self, percent, msg):
        self.progress_dialog.setValue(percent)
        self.progress_dialog.setLabelText(msg)

    def backup_finished(self, success, msg):
        self.progress_dialog.close()
        if success:
            QMessageBox.information(self, "Success", msg)
            super().accept()
        else:
            if msg == "Backup cancelled by user.":
                QMessageBox.warning(self, "Cancelled", msg)
            else:
                QMessageBox.critical(self, "Critical Error", f"Error during file packaging: {msg}")


# ---------------- MAIN PROGRAM ----------------
class StasherApp(QMainWindow, Ui_StasherMain):
    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.config = load_config()
        self.storage_path = self.config.get("PATH_STORAGE", DEFAULT_STORAGE)

        # RAM Cache to store system configuration list for high-performance operations
        self.records = []
        self.hidden_folders = set()  # Temporary session-based hidden records
        self.selected_item_ui = None
        self.selected_record_data = None

        self.init_interface_bindings()
        self.scan_storage_to_ram()

    def init_interface_bindings(self):
        """Initializes UI elements, read-only fields, and signal-slot connections."""
        # Display system config paths in info boxes for easy copying
        self.Summary_Path2AppConfig_Value.setText(os.path.abspath(CONFIG_FILE))
        self.Summary_Path2AppConfig_Value.setReadOnly(True)
        self.Summary_Path2AppFolder_Value.setText(self.storage_path)
        self.Summary_Path2AppFolder_Value.setReadOnly(True)

        # Tree Widget configuration
        self.View_AllRecordsTable.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.View_AllRecordsTable.customContextMenuRequested.connect(self.open_custom_context_menu)
        self.View_AllRecordsTable.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

        # Connect feature button clicks
        self.Edit_Button_ListAllRecord.clicked.connect(self.reset_and_show_all)
        self.Edit_Button_RefreshRecords.clicked.connect(self.force_refresh_all_records)
        self.Edit_Button_NewRecord.clicked.connect(self.trigger_new_record_dialog)
        self.Edit_Button_SearchByName.clicked.connect(lambda: self.execute_ram_search(priority="name"))
        self.Edit_Button_SearchByNameDesc.clicked.connect(lambda: self.execute_ram_search(priority="desc"))
        self.View_Path2PatchFolder_Button.clicked.connect(self.execute_paste_patch_logic)

        # Automatically restore view if search input is cleared
        self.Edit_GeneralUserInput.textChanged.connect(self.handle_empty_search_input)

    def extract_yaml_info(self, data):
        """Helper to flatten the 'GeneralInfo' list from the YAML structure into a dictionary."""
        info = {}
        for d in data.get("GeneralInfo", []):
            info.update(d)
        return info

    def scan_storage_to_ram(self):
        """Scans the storage directory once and caches all record metadata into RAM for speed."""
        self.records.clear()
        if not os.path.exists(self.storage_path):
            os.makedirs(self.storage_path)

        for folder in os.listdir(self.storage_path):
            folder_path = os.path.join(self.storage_path, folder)
            yml_path = os.path.join(folder_path, "RecordStructure.yml")

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

        # Sync record count display on Summary panel
        self.Summary_NumberOfRecords_Value.setText(str(len(self.records)))
        self.render_records_to_tree_view(self.records)

    def render_records_to_tree_view(self, data_list):
        """Populates the TreeWidget with cached record data."""
        self.View_AllRecordsTable.clear()
        self.selected_item_ui = None

        for idx, rec in enumerate(data_list):
            if rec["_folder"] in self.hidden_folders:
                continue

            # Construct parent node (Record Root)
            root_item = QTreeWidgetItem([
                str(idx + 1),
                rec.get("Name", "Unknown Name"),
                rec.get("RootPath", "N/A"),
                str(len(rec.get("RelativePathList", []))),
                rec.get("Desc", "")
            ])

            # Attach raw data to UI item for quick access via context menu
            root_item.setData(0, Qt.ItemDataRole.UserRole, rec)

            # Construct child nodes (Directory Tree / Archived Files)
            for p in rec.get("RelativePathList", []):
                icon = "📁" if p.endswith("/") else "📄"
                child_item = QTreeWidgetItem(["", "", "", f"{icon} {p}", ""])
                root_item.addChild(child_item)

            self.View_AllRecordsTable.addTopLevelItem(root_item)
            
            # Restore highlight color if this item was previously selected
            if self.selected_record_data and self.selected_record_data["_folder"] == rec["_folder"]:
                self.apply_row_light_mode_color(root_item, highlight=True)

    def apply_row_light_mode_color(self, item, highlight=True):
        """Fixes Windows Light Mode background override by explicitly assigning colors to Tree items."""
        if highlight:
            for col in range(item.columnCount()):
                item.setBackground(col, QColor(51, 153, 255))
                item.setForeground(col, QColor(255, 255, 255))
        else:
            for col in range(item.columnCount()):
                item.setBackground(col, Qt.GlobalColor.transparent)
                item.setForeground(col, QColor(0, 0, 0))

    def reset_and_show_all(self):
        """Clears search filter and shows all cached records."""
        self.Edit_GeneralUserInput.clear()
        self.render_records_to_tree_view(self.records)

    def force_refresh_all_records(self):
        """Full re-scan of the storage folder from disk into RAM."""
        self.hidden_folders.clear()
        self.selected_record_data = None
        self.View_Path2PatchFolder_Value.clear()
        self.scan_storage_to_ram()
        QMessageBox.information(self, "Refresh Successful", "Storage re-scanned and synchronized to RAM!")

    def handle_empty_search_input(self):
        """Auto-resets the table view when search input becomes empty."""
        if not self.Edit_GeneralUserInput.text().strip():
            self.render_records_to_tree_view(self.records)

    def execute_ram_search(self, priority="name"):
        """Performs a weighted search algorithm across cached records in RAM."""
        query = self.Edit_GeneralUserInput.text().strip().lower()
        if not query:
            self.render_records_to_tree_view(self.records)
            return

        scored_list = []
        for rec in self.records:
            name = rec.get("Name", "").lower()
            desc = rec.get("Desc", "").lower()
            
            score = 0
            # Weighting logic for string matching priority
            if priority == "name":
                if query in name: score += 20
                if query in desc: score += 2
            else:  # Prioritize description search
                if query in desc: score += 20
                if query in name: score += 2
                
            if score > 0:
                scored_list.append((score, rec))
                
        # Sort matches from highest to lowest score
        scored_list.sort(key=lambda x: x[0], reverse=True)
        sorted_records = [item[1] for item in scored_list]
        
        self.render_records_to_tree_view(sorted_records)

    def trigger_new_record_dialog(self):
        """Opens the dialog to create and archive a new backup record."""
        dialog = NewRecordDialog(self.storage_path)
        if dialog.exec():
            self.scan_storage_to_ram()

    # ---------------- CONTEXT MENU ----------------
    def open_custom_context_menu(self, pos):
        """Handles right-click events on the records table."""
        item = self.View_AllRecordsTable.itemAt(pos)
        if not item: 
            return
        
        # Ensure children clicks still reference parent record data
        root_item = item if item.parent() is None else item.parent()
        rec_data = root_item.data(0, Qt.ItemDataRole.UserRole)
        if not rec_data: 
            return

        menu = QMenu(self)
        
        act_select = QAction("Select this record", self)
        act_deselect = QAction("De-select this record", self)
        act_edit = QAction("Edit record", self)
        act_delete = QAction("Delete record", self)
        act_hide = QAction("Remove record from table", self)

        act_select.triggered.connect(lambda: self.menu_select_record_logic(root_item, rec_data))
        act_deselect.triggered.connect(lambda: self.menu_deselect_record_logic(root_item))
        act_edit.triggered.connect(lambda: self.menu_edit_yaml_sync_logic(rec_data))
        act_delete.triggered.connect(lambda: self.menu_delete_record_from_disk(rec_data))
        act_hide.triggered.connect(lambda: self.menu_hide_record_temporary(rec_data))

        menu.addAction(act_select)
        menu.addAction(act_deselect)
        menu.addSeparator()
        menu.addAction(act_edit)
        menu.addSeparator()
        menu.addAction(act_delete)
        menu.addAction(act_hide)

        # menu.exec(self.View_AllRecordsTable.viewport().mapToGlobal(pos))
        menu.exec(self.View_AllRecordsTable.viewport().mapToGlobal(pos))

    def menu_select_record_logic(self, tree_item, rec_data):
        """Highlights a record as 'Active' for restoration (Paste) operations."""
        if self.selected_item_ui:
            self.menu_deselect_record_logic(self.selected_item_ui)
        self.selected_item_ui = tree_item
        self.selected_record_data = rec_data
        self.apply_row_light_mode_color(tree_item, highlight=True)
        
        # Auto-fill the original RootPath into the target input for reference
        self.View_Path2PatchFolder_Value.setText(rec_data.get("RootPath", ""))

    def menu_deselect_record_logic(self, tree_item):
        """Clears the active selection state."""
        self.apply_row_light_mode_color(tree_item, highlight=False)
        if self.selected_item_ui == tree_item:
            self.selected_item_ui = None
            self.selected_record_data = None
            self.View_Path2PatchFolder_Value.clear()

    def menu_hide_record_temporary(self, rec_data):
        """Hides the record from the current table view (RAM only)."""
        self.hidden_folders.add(rec_data["_folder"])
        self.render_records_to_tree_view(self.records)

    def menu_delete_record_from_disk(self, rec_data):
        """Irreversibly deletes the record folder and its metadata from the storage drive."""
        name = rec_data.get("Name", "Unknown Name")
        reply = QMessageBox.question(
            self, 'Confirm Record Deletion', 
            f"This action cannot be undone!\nAre you sure you want to PERMANENTLY DELETE record: '{name}' from disk?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.delete_progress_dialog = QProgressDialog(f"Deleting record '{name}'...", None, 0, 0, self)
            self.delete_progress_dialog.setWindowTitle("Deletion in Progress")
            self.delete_progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            self.delete_progress_dialog.setCancelButton(None) # Deletion is not safely cancellable
            
            # Make text selectable
            for label in self.delete_progress_dialog.findChildren(QLabel):
                label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

            self.delete_worker = DeleteWorker(rec_data["_folder"])
            self.delete_worker.finished.connect(lambda success, msg: self.delete_finished(success, msg, name))
            self.delete_worker.start()

            self.delete_progress_dialog.exec()

    def delete_finished(self, success, msg, record_name):
        """Handles the completion of the delete worker thread."""
        self.delete_progress_dialog.close()
        if success:
            self.scan_storage_to_ram()
            QMessageBox.information(self, "Success", f"Record '{record_name}' has been completely removed!")
        else:
            QMessageBox.critical(self, "Delete Error", msg)
            # Refresh anyway to reflect partial deletion state if any
            self.scan_storage_to_ram()

    def menu_edit_yaml_sync_logic(self, rec_data):
        """
        'Smart Sync' mode: Opens YAML for manual editing, then diffs the file list
        to automatically add or remove data within the archive folder.
        """
        yml_path = rec_data["_yml"]
        
        # Open default editor based on OS
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
        
        # Data synchronization mechanism to clean up or append files
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
            
            # 1. Clean up files removed from YAML config
            for rf in removed_files:
                target = os.path.join(record_folder, rf)
                if os.path.exists(target):
                    if os.path.isdir(target): 
                        shutil.rmtree(target)
                    else: 
                        os.remove(target)
                    sync_log.append(f"🗑 Deleted from archive: {rf}")
                    
            # 2. Copy new files added to YAML config
            for af in added_files:
                src = os.path.join(original_root, af)
                dest = os.path.join(record_folder, af)
                if os.path.exists(src):
                    if af.endswith('/') or os.path.isdir(src):
                        shutil.copytree(src, dest, dirs_exist_ok=True)
                    else:
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        shutil.copy2(src, dest)
                    sync_log.append(f"📥 Added new file to archive: {af}")
                else:
                    sync_log.append(f"❌ Failed: Source not found for: {af}")

            if sync_log:
                QMessageBox.information(self, "YAML Sync Results", "\n".join(sync_log))
            
            # Refresh RAM cache after sync
            self.scan_storage_to_ram()
        except Exception as e:
            QMessageBox.critical(self, "Sync Error", f"An error occurred during structure sync: {str(e)}")

    # ---------------- DATA RESTORATION (PASTE / PATCH) ----------------
    def execute_paste_patch_logic(self):
        """Restores (pastes) the active record's contents to a specified destination directory."""
        if not self.selected_record_data:
            QMessageBox.warning(self, "No Record Selected", "Please right-click and 'Select this record' before pasting.")
            return

        paste_path = self.View_Path2PatchFolder_Value.text().strip().strip('"').strip("'")
        root_path = self.selected_record_data.get("RootPath", "")

        # If destination is empty, default to the original RootPath
        if not paste_path:
            paste_path = root_path
            if not paste_path:
                QMessageBox.warning(self, "Path Error", "Destination is empty and record has no saved RootPath.")
                return

        if not os.path.exists(paste_path):
            reply = QMessageBox.question(
                self, "Create New Folder?", 
                f"Directory '{paste_path}' does not exist. Create it automatically?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes
            )
            if reply == QMessageBox.StandardButton.Yes:
                os.makedirs(paste_path, exist_ok=True)
            else:
                return

        record_folder = self.selected_record_data["_folder"]
        rel_list = self.selected_record_data.get("RelativePathList", [])
        
        skip_all_errors = False
        overwrite_all = False
        restored_count = 0
        
        total_files = 0
        for rel in rel_list:
            src = os.path.join(record_folder, rel)
            if os.path.isdir(src):
                for dirpath, _, filenames in os.walk(src):
                    total_files += len(filenames)
            elif os.path.exists(src):
                total_files += 1
                
        if total_files == 0:
            total_files = 1

        progress_dialog = QProgressDialog("Restoring files...", "Cancel", 0, total_files, self)
        progress_dialog.setWindowTitle("Paste Progress")
        progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog.setMinimumDuration(0)
        progress_dialog.setValue(0)

        # Make text selectable
        for label in progress_dialog.findChildren(QLabel):
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        processed_count = 0

        for rel in rel_list:
            src = os.path.join(record_folder, rel)
            dest = os.path.join(paste_path, rel)

            if not os.path.exists(src):
                continue

            if os.path.isdir(src):
                for dirpath, _, filenames in os.walk(src):
                    for fname in filenames:
                        if progress_dialog.wasCanceled():
                            QMessageBox.warning(self, "Cancelled", "Paste operation cancelled by user.")
                            return

                        s_file = os.path.join(dirpath, fname)
                        rel_to_src = os.path.relpath(s_file, src)
                        d_file = os.path.join(dest, rel_to_src)
                        
                        progress_dialog.setLabelText(f"Restoring: {fname}")
                        QApplication.processEvents()

                        if os.path.exists(d_file) and not overwrite_all:
                            ans = self.prompt_overwrite_confirmation_dialog(d_file)
                            if ans == QMessageBox.StandardButton.YesToAll: 
                                overwrite_all = True
                            elif ans == QMessageBox.StandardButton.Cancel: 
                                progress_dialog.close()
                                return
                            elif ans == QMessageBox.StandardButton.No: 
                                processed_count += 1
                                progress_dialog.setValue(processed_count)
                                continue
                                
                        while True:
                            try:
                                os.makedirs(os.path.dirname(d_file), exist_ok=True)
                                shutil.copy2(s_file, d_file)
                                restored_count += 1
                                break
                            except Exception as e:
                                if skip_all_errors: break
                                ans = self.prompt_copy_error_dialog(s_file, str(e))
                                if ans == "Skip": break
                                elif ans == "SkipAll":
                                    skip_all_errors = True
                                    break
                                elif ans == "Abort":
                                    progress_dialog.close()
                                    QMessageBox.warning(self, "Aborted", "Paste operation aborted due to error.")
                                    return
                        processed_count += 1
                        progress_dialog.setValue(processed_count)
            else:
                if progress_dialog.wasCanceled():
                    QMessageBox.warning(self, "Cancelled", "Paste operation cancelled by user.")
                    return

                progress_dialog.setLabelText(f"Restoring: {os.path.basename(src)}")
                QApplication.processEvents()

                if os.path.exists(dest) and not overwrite_all:
                    ans = self.prompt_overwrite_confirmation_dialog(dest)
                    if ans == QMessageBox.StandardButton.YesToAll: 
                        overwrite_all = True
                    elif ans == QMessageBox.StandardButton.Cancel: 
                        progress_dialog.close()
                        return
                    elif ans == QMessageBox.StandardButton.No: 
                        processed_count += 1
                        progress_dialog.setValue(processed_count)
                        continue

                while True:
                    try:
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        shutil.copy2(src, dest)
                        restored_count += 1
                        break
                    except Exception as e:
                        if skip_all_errors: break
                        ans = self.prompt_copy_error_dialog(src, str(e))
                        if ans == "Skip": break
                        elif ans == "SkipAll":
                            skip_all_errors = True
                            break
                        elif ans == "Abort":
                            progress_dialog.close()
                            QMessageBox.warning(self, "Aborted", "Paste operation aborted due to error.")
                            return
                            
                processed_count += 1
                progress_dialog.setValue(processed_count)
        
        progress_dialog.close()
        
        QMessageBox.information(
            self, "Restore Successful", 
            f"Paste operation finished.\nSuccessfully restored {restored_count} components into:\n{paste_path}"
        )

    def prompt_overwrite_confirmation_dialog(self, filepath):
        """Displays a dialog asking user how to handle existing files during restoration."""
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
        return msg.exec()

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
        if clicked_button == skip_all_button:
            return "SkipAll"

        standard_button = msg.standardButton(clicked_button)
        if standard_button == QMessageBox.StandardButton.Ignore:
            return "Skip"
        elif standard_button == QMessageBox.StandardButton.Abort:
            return "Abort"
        
        return "Retry"

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Apply Fusion theme for a consistent flat UI across all operating systems
    app.setStyle("Fusion") 
    window = StasherApp()
    window.show()
    # sys.exit(app.exec())
    sys.exit(app.exec())