import os
import sys
import json
import yaml
import shutil
import subprocess
import threading
import re
import posixpath
from datetime import datetime
import paramiko

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QMenu,
    QTreeWidgetItem, QMessageBox, QDialog, QHeaderView,
    QTextEdit, QProgressDialog, QLabel,
    QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QPushButton, QCheckBox,
    QTableWidget, QTableWidgetItem, QFileDialog, QWidget
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QAction, QPalette, QIcon

# Import UI classes compiled from the respective .ui files
from stasher_ui import Ui_StasherMain
from stasher_newrecord_ui import Ui_NewRecord

CONFIG_FILE = "stasher_config.json"
SSH_CONFIG_JSON = "stasher_ssh_config.json"
SSH_CONFIG_FILE = ".ssh_config"
DEFAULT_STORAGE = r"C:\Users\phu.nguyen-thanh\Documents\UserData"

NO_WINDOW_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

def get_app_icon():
    base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    for name in ("stasher.ico", "stasher.png"):
        p = os.path.join(base_dir, name)
        if os.path.exists(p):
            return QIcon(p)
    return QIcon()


"""
/*
 * SSH Configuration helpers:
 * - Dedicated JSON storage: stasher_ssh_config.json (Read/Write)
 * - OpenSSH config: .ssh_config and ~/.ssh/config (READ-ONLY)
 */
"""
def get_ssh_json_path():
    if os.path.exists(SSH_CONFIG_JSON):
        return os.path.abspath(SSH_CONFIG_JSON)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    app_cfg = os.path.join(base_dir, SSH_CONFIG_JSON)
    if os.path.exists(app_cfg):
        return app_cfg
    return app_cfg

def load_ssh_json():
    path = get_ssh_json_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_ssh_config(ip, username, password):
    """
    Saves SSH connection credentials ONLY to stasher_ssh_config.json.
    Never writes to .ssh_config or ~/.ssh/config.
    """
    cfg = load_ssh_json()
    cfg["ip"] = ip
    cfg["username"] = username
    cfg["password"] = password
    if "hosts" not in cfg or not isinstance(cfg["hosts"], dict):
        cfg["hosts"] = {}
    cfg["hosts"][ip] = {
        "username": username,
        "password": password,
        "updated_at": datetime.now().strftime("%y/%m/%d %H:%M:%S")
    }
    path = get_ssh_json_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving {SSH_CONFIG_JSON}: {e}")
        return False

def delete_ssh_host(ip):
    """
    Deletes an SSH host from stasher_ssh_config.json.
    Never modifies .ssh_config or ~/.ssh/config.
    """
    cfg = load_ssh_json()
    deleted = False
    if "hosts" in cfg and isinstance(cfg["hosts"], dict) and ip in cfg["hosts"]:
        del cfg["hosts"][ip]
        deleted = True
    if cfg.get("ip") == ip:
        cfg["ip"] = ""
        cfg["username"] = ""
        cfg["password"] = ""
        deleted = True
    if deleted:
        path = get_ssh_json_path()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=4)
            return True
        except Exception as e:
            print(f"Error updating {SSH_CONFIG_JSON}: {e}")
            return False
    return False

def get_all_known_ssh_hosts():
    """
    Returns a combined list of SSH hosts from stasher_ssh_config.json and OpenSSH configs (.ssh_config / ~/.ssh/config).
    """
    hosts_list = []
    seen = set()

    # 1. From stasher_ssh_config.json
    cfg = load_ssh_json()
    if cfg:
        hosts = cfg.get("hosts", {})
        if isinstance(hosts, dict):
            for ip, data in hosts.items():
                if ip and ip not in seen:
                    seen.add(ip)
                    hosts_list.append({
                        "ip": ip,
                        "username": data.get("username", "") or "N/A",
                        "password": data.get("password", "") or "",
                        "updated_at": data.get("updated_at", "") or datetime.now().strftime("%y/%m/%d %H:%M:%S"),
                        "source": "json"
                    })

    # 2. From OpenSSH configs (.ssh_config and ~/.ssh/config) - READ-ONLY
    candidate_files = []
    local_ssh = get_ssh_config_path()
    if os.path.exists(local_ssh):
        candidate_files.append(local_ssh)
    user_ssh = os.path.expanduser("~/.ssh/config")
    if os.path.exists(user_ssh) and user_ssh not in candidate_files:
        candidate_files.append(user_ssh)

    for cfg_file in candidate_files:
        try:
            ssh_conf = paramiko.SSHConfig()
            with open(cfg_file, "r", encoding="utf-8") as f:
                ssh_conf.parse(f)
            for entry in getattr(ssh_conf, "_config", []):
                names = entry.get("host", [])
                for name in names:
                    if name and name != "*" and not name.startswith("*") and name not in seen:
                        seen.add(name)
                        cfg_data = entry.get("config", {})
                        mtime = datetime.fromtimestamp(os.path.getmtime(cfg_file)).strftime("%y/%m/%d %H:%M:%S")
                        hosts_list.append({
                            "ip": name,
                            "username": cfg_data.get("user", "") or "N/A",
                            "password": "",
                            "updated_at": mtime,
                            "source": "openssh"
                        })
        except Exception:
            pass

    return hosts_list

def get_ssh_config_path():
    """
    Returns path to .ssh_config (READ-ONLY).
    """
    if os.path.exists(SSH_CONFIG_FILE):
        return os.path.abspath(SSH_CONFIG_FILE)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, SSH_CONFIG_FILE)

def lookup_openssh_config(host):
    """
    READ-ONLY lookup of host alias or configuration in OpenSSH formatted files (.ssh_config or ~/.ssh/config).
    Never writes to .ssh_config.
    """
    candidate_files = []
    local_ssh = get_ssh_config_path()
    if os.path.exists(local_ssh):
        candidate_files.append(local_ssh)
    user_ssh = os.path.expanduser("~/.ssh/config")
    if os.path.exists(user_ssh) and user_ssh not in candidate_files:
        candidate_files.append(user_ssh)

    for cfg_file in candidate_files:
        try:
            ssh_conf = paramiko.SSHConfig()
            with open(cfg_file, "r", encoding="utf-8") as f:
                ssh_conf.parse(f)
            matched = ssh_conf.lookup(host)
            if matched and (matched.get("hostname") or matched.get("user") or matched.get("proxycommand")):
                ident = matched.get("identityfile")
                key_file = ident[0] if isinstance(ident, list) and ident else ident
                proxy_cmd = matched.get("proxycommand")
                if proxy_cmd:
                    proxy_cmd = proxy_cmd.replace("%h", host).replace("%p", str(matched.get("port", 22)))
                return {
                    "ip": matched.get("hostname", host),
                    "username": matched.get("user", ""),
                    "password": "",
                    "port": int(matched.get("port", 22)),
                    "key_filename": key_file,
                    "proxycommand": proxy_cmd
                }
        except Exception:
            pass
    return None

def get_ssh_connection(ip=None, username=None):
    """
    Retrieves SSH connection info.
    Priority:
    1. Dedicated stasher_ssh_config.json (stores saved user/passwords)
    2. Read-only .ssh_config and ~/.ssh/config (OpenSSH host aliases, proxycommands, keys)
    """
    cfg = load_ssh_json()

    if ip:
        if cfg:
            hosts = cfg.get("hosts", {})
            if ip in hosts:
                h = hosts[ip]
                return {
                    "ip": ip,
                    "username": username or h.get("username", ""),
                    "password": h.get("password", "")
                }
            if cfg.get("ip") == ip:
                return {
                    "ip": ip,
                    "username": username or cfg.get("username", ""),
                    "password": cfg.get("password", "")
                }

        # Check Read-only OpenSSH config (.ssh_config / ~/.ssh/config) for host alias
        openssh_info = lookup_openssh_config(ip)
        if openssh_info:
            if username:
                openssh_info["username"] = username
            return openssh_info
        return None

    if cfg:
        if cfg.get("ip") and cfg.get("username"):
            return {
                "ip": cfg.get("ip"),
                "username": username or cfg.get("username", ""),
                "password": cfg.get("password", "")
            }

        hosts = cfg.get("hosts", {})
        if hosts:
            first_ip = next(iter(hosts))
            h = hosts[first_ip]
            return {
                "ip": first_ip,
                "username": username or h.get("username", ""),
                "password": h.get("password", "")
            }

    return None

def parse_destination_type(path_str):
    if not path_str:
        return {"is_ssh": False, "ip": None, "username": None, "remote_path": "", "is_unix": False}

    cleaned = path_str.strip().strip('"').strip("'")

    # 1. Full SSH path check: [user@]host:remote_path
    ssh_match = re.match(r'^(?:(?P<user>[^@:\s]+)@)?(?P<host>[^@:\s]+):(?P<remote_path>.*)$', cleaned)
    if ssh_match:
        user = ssh_match.group("user")
        host = ssh_match.group("host")
        remote_path = ssh_match.group("remote_path")
        if not (user is None and len(host) == 1 and host.isalpha()):
            return {
                "is_ssh": True,
                "ip": host,
                "username": user,
                "remote_path": remote_path,
                "is_unix": False
            }

    # 2. Unix path check: starts with '/' or '~'
    if cleaned.startswith("/") or cleaned.startswith("~"):
        return {
            "is_ssh": True,
            "ip": None,
            "username": None,
            "remote_path": cleaned,
            "is_unix": True
        }

    # 3. Local Windows path check:
    if os.path.exists(cleaned):
        return {"is_ssh": False, "ip": None, "username": None, "remote_path": "", "is_unix": False}

    drive, _ = os.path.splitdrive(cleaned)
    if drive and os.path.exists(drive + "\\"):
        return {"is_ssh": False, "ip": None, "username": None, "remote_path": "", "is_unix": False}

    # 4. SUMMARY rule: Path not found -> treat as remote Unix destination
    return {
        "is_ssh": True,
        "ip": None,
        "username": None,
        "remote_path": cleaned,
        "is_unix": True
    }


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


# ---------------- SSH TEST WORKER (PREVENTS UI FREEZING) ----------------
class SSHTestWorker(QThread):
    finished = Signal(bool, str)

    def __init__(self, ip, username, password):
        super().__init__()
        self.ip = ip
        self.username = username
        self.password = password
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        ssh_target = f"{self.username}@{self.ip}" if self.username else self.ip
        try:
            if not self.password:
                res = subprocess.run(
                    ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", ssh_target, "echo ready"],
                    capture_output=True, text=True, timeout=7,
                    creationflags=NO_WINDOW_FLAGS
                )
                if res.returncode == 0:
                    self.finished.emit(True, "")
                else:
                    err = res.stderr.strip() or f"Process exited with code {res.returncode}"
                    self.finished.emit(False, err)
            else:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                port = 22
                ip_addr = self.ip
                if ":" in ip_addr and not ip_addr.startswith("["):
                    try:
                        parts = ip_addr.split(":")
                        ip_addr = parts[0]
                        port = int(parts[1])
                    except Exception:
                        pass
                client.connect(
                    hostname=ip_addr,
                    port=port,
                    username=self.username if self.username else None,
                    password=self.password if self.password else None,
                    timeout=6,
                    allow_agent=True,
                    look_for_keys=True
                )
                client.close()
                self.finished.emit(True, "")
        except Exception as e:
            self.finished.emit(False, str(e))


# ---------------- RESTORE WORKER (PREVENTS UI FREEZING) ----------------
class RestoreWorker(QThread):
    progress = Signal(int, str)
    ask_overwrite = Signal(str)
    ask_error = Signal(str, str)
    finished = Signal(bool, str)

    def __init__(self, selected_records_data, is_ssh=False, ssh_conn=None, target_remote_path="", user_paste_path=""):
        super().__init__()
        self.selected_records_data = selected_records_data
        self.is_ssh = is_ssh
        self.ssh_conn = ssh_conn or {}
        self.target_remote_path = target_remote_path
        self.user_paste_path = user_paste_path

        self._is_cancelled = False
        self.sync_event = threading.Event()
        self.user_action = None
        self.skip_all_errors = False
        self.overwrite_all = False

    def cancel(self):
        self._is_cancelled = True
        self.sync_event.set()

    def set_user_action(self, action):
        self.user_action = action
        self.sync_event.set()

    def run(self):
        try:
            if self.is_ssh:
                self._run_ssh_restore()
            else:
                self._run_local_restore()
        except Exception as e:
            self.finished.emit(False, str(e))

    def _run_local_restore(self):
        total_files = 0
        for rec in self.selected_records_data:
            for rel in rec.get("RelativePathList", []):
                src = os.path.join(rec["_folder"], rel)
                if os.path.isdir(src):
                    for _, _, filenames in os.walk(src):
                        total_files += len(filenames)
                elif os.path.exists(src):
                    total_files += 1

        if total_files == 0:
            total_files = 1

        processed_count = 0
        restored_count = 0

        for rec in self.selected_records_data:
            if self._is_cancelled:
                self.finished.emit(False, "Cancelled by user.")
                return

            current_paste_path = self.user_paste_path or rec.get("RootPath", "")
            if not current_paste_path:
                continue

            os.makedirs(current_paste_path, exist_ok=True)
            record_folder = rec["_folder"]

            for rel in rec.get("RelativePathList", []):
                if self._is_cancelled:
                    self.finished.emit(False, "Cancelled by user.")
                    return

                src = os.path.join(record_folder, rel)
                if not os.path.exists(src):
                    continue

                rel_norm = rel.replace("/", os.sep).replace("\\", os.sep).strip(os.sep)
                paste_norm = current_paste_path.rstrip("/\\")
                if paste_norm.endswith(os.sep + rel_norm) or paste_norm == rel_norm:
                    dest = paste_norm
                elif os.path.basename(paste_norm) == os.path.basename(rel_norm) and len(rec.get("RelativePathList", [])) == 1:
                    dest = paste_norm
                else:
                    dest = os.path.join(current_paste_path, rel)

                if os.path.isdir(src):
                    for dirpath, _, filenames in os.walk(src):
                        for fname in filenames:
                            if self._is_cancelled:
                                self.finished.emit(False, "Cancelled by user.")
                                return

                            s_file = os.path.join(dirpath, fname)
                            rel_to_src = os.path.relpath(s_file, src)
                            d_file = os.path.join(dest, rel_to_src)

                            percent = int((processed_count / total_files) * 100)
                            self.progress.emit(min(percent, 99), f"Restoring: {fname}")

                            if os.path.exists(d_file) and not self.overwrite_all:
                                self.sync_event.clear()
                                self.ask_overwrite.emit(d_file)
                                self.sync_event.wait()
                                if self._is_cancelled or self.user_action == "Cancel":
                                    self.finished.emit(False, "Cancelled by user.")
                                    return
                                elif self.user_action == "YesToAll":
                                    self.overwrite_all = True
                                elif self.user_action == "No":
                                    processed_count += 1
                                    continue

                            while True:
                                if self._is_cancelled:
                                    self.finished.emit(False, "Cancelled by user.")
                                    return
                                try:
                                    os.makedirs(os.path.dirname(d_file), exist_ok=True)
                                    shutil.copy2(s_file, d_file)
                                    restored_count += 1
                                    processed_count += 1
                                    break
                                except Exception as e:
                                    if self.skip_all_errors:
                                        processed_count += 1
                                        break
                                    self.sync_event.clear()
                                    self.ask_error.emit(d_file, str(e))
                                    self.sync_event.wait()
                                    if self.user_action == "Retry":
                                        continue
                                    elif self.user_action == "Skip":
                                        processed_count += 1
                                        break
                                    elif self.user_action == "SkipAll":
                                        self.skip_all_errors = True
                                        processed_count += 1
                                        break
                                    elif self.user_action == "Abort" or self._is_cancelled:
                                        self.finished.emit(False, "Aborted by user.")
                                        return
                else:
                    if self._is_cancelled:
                        self.finished.emit(False, "Cancelled by user.")
                        return

                    fname = os.path.basename(src)
                    percent = int((processed_count / total_files) * 100)
                    self.progress.emit(min(percent, 99), f"Restoring: {fname}")

                    if os.path.exists(dest) and not self.overwrite_all:
                        self.sync_event.clear()
                        self.ask_overwrite.emit(dest)
                        self.sync_event.wait()
                        if self._is_cancelled or self.user_action == "Cancel":
                            self.finished.emit(False, "Cancelled by user.")
                            return
                        elif self.user_action == "YesToAll":
                            self.overwrite_all = True
                        elif self.user_action == "No":
                            processed_count += 1
                            continue

                    while True:
                        if self._is_cancelled:
                            self.finished.emit(False, "Cancelled by user.")
                            return
                        try:
                            os.makedirs(os.path.dirname(dest), exist_ok=True)
                            shutil.copy2(src, dest)
                            restored_count += 1
                            processed_count += 1
                            break
                        except Exception as e:
                            if self.skip_all_errors:
                                processed_count += 1
                                break
                            self.sync_event.clear()
                            self.ask_error.emit(dest, str(e))
                            self.sync_event.wait()
                            if self.user_action == "Retry":
                                continue
                            elif self.user_action == "Skip":
                                processed_count += 1
                                break
                            elif self.user_action == "SkipAll":
                                self.skip_all_errors = True
                                processed_count += 1
                                break
                            elif self.user_action == "Abort" or self._is_cancelled:
                                self.finished.emit(False, "Aborted by user.")
                                return

        self.progress.emit(100, "Done")
        self.finished.emit(
            True,
            f"Paste operation finished locally.\nSuccessfully restored {restored_count} components into:\n{self.user_paste_path or 'original paths'}"
        )

    def _run_ssh_restore(self):
        ip = self.ssh_conn.get("ip")
        username = self.ssh_conn.get("username", "")
        password = self.ssh_conn.get("password", "")
        port = self.ssh_conn.get("port")
        key_filename = self.ssh_conn.get("key_filename")
        ssh_target = f"{username}@{ip}" if username else ip

        total_files = 0
        for rec in self.selected_records_data:
            for rel in rec.get("RelativePathList", []):
                src = os.path.join(rec["_folder"], rel)
                if os.path.isdir(src):
                    for _, _, filenames in os.walk(src):
                        total_files += len(filenames)
                elif os.path.exists(src):
                    total_files += 1
        if total_files == 0:
            total_files = 1

        processed_count = 0
        restored_count = 0

        # If no password provided (e.g. coder.coffee-opera, SSH keys, OpenSSH config):
        if not password:
            self.progress.emit(5, f"Connecting via OpenSSH to {ssh_target}...")
            check_res = subprocess.run(
                ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", ssh_target, "echo ready"],
                capture_output=True, text=True,
                creationflags=NO_WINDOW_FLAGS
            )
            if check_res.returncode == 0:
                self._run_scp_restore(ssh_target, total_files)
                return

        # Paramiko SFTP connection
        self.progress.emit(5, f"Connecting to {ssh_target}...")
        conn_port = port if port else 22
        host_to_connect = ip
        if ":" in ip and not ip.startswith("["):
            try:
                parts = ip.split(":")
                host_to_connect = parts[0]
                conn_port = int(parts[1])
            except Exception:
                pass

        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            ssh_client.connect(
                hostname=host_to_connect,
                port=conn_port,
                username=username if username else None,
                password=password if password else None,
                key_filename=key_filename if key_filename else None,
                timeout=12,
                allow_agent=True,
                look_for_keys=True
            )
            sftp = ssh_client.open_sftp()
        except Exception as e:
            self.finished.emit(False, f"SSH Connection Failed: {str(e)}")
            return

        def sftp_makedirs(remote_directory):
            parts = []
            p = remote_directory.replace("\\", "/")
            while p and p not in ("/", "."):
                parts.append(p)
                parent, _ = posixpath.split(p)
                if parent == p:
                    break
                p = parent
            parts.reverse()
            for directory in parts:
                try:
                    sftp.stat(directory)
                except (IOError, FileNotFoundError):
                    try:
                        sftp.mkdir(directory)
                    except (IOError, FileNotFoundError):
                        pass

        def sftp_exists(remote_path):
            try:
                sftp.stat(remote_path.replace("\\", "/"))
                return True
            except (IOError, FileNotFoundError):
                return False

        resolved_default_path = self.target_remote_path.replace("\\", "/") if self.target_remote_path else ""
        if resolved_default_path and (resolved_default_path.startswith("~") or resolved_default_path == "~"):
            try:
                remote_home = sftp.normalize(".")
                if resolved_default_path == "~":
                    resolved_default_path = remote_home
                else:
                    resolved_default_path = posixpath.join(remote_home, resolved_default_path[2:])
            except Exception:
                pass

        for rec in self.selected_records_data:
            if self._is_cancelled:
                sftp.close()
                ssh_client.close()
                self.finished.emit(False, "Cancelled by user.")
                return

            current_remote_base = resolved_default_path
            if not current_remote_base:
                rec_root = rec.get("RootPath", "").replace("\\", "/")
                if rec_root.startswith("~") or rec_root == "~":
                    try:
                        remote_home = sftp.normalize(".")
                        rec_root = remote_home if rec_root == "~" else posixpath.join(remote_home, rec_root[2:])
                    except Exception:
                        pass
                current_remote_base = rec_root
                if not current_remote_base:
                    continue

            record_folder = rec["_folder"]

            for rel in rec.get("RelativePathList", []):
                if self._is_cancelled:
                    sftp.close()
                    ssh_client.close()
                    self.finished.emit(False, "Cancelled by user.")
                    return

                src = os.path.join(record_folder, rel)
                if not os.path.exists(src):
                    continue

                rel_posix = rel.replace("\\", "/").strip("/")
                remote_base_norm = current_remote_base.replace("\\", "/").rstrip("/")

                if remote_base_norm.endswith("/" + rel_posix) or remote_base_norm == rel_posix:
                    dest_remote = remote_base_norm
                elif posixpath.basename(remote_base_norm) == posixpath.basename(rel_posix) and len(rec.get("RelativePathList", [])) == 1:
                    dest_remote = remote_base_norm
                else:
                    dest_remote = posixpath.join(remote_base_norm, rel_posix)

                if os.path.isdir(src):
                    for dirpath, _, filenames in os.walk(src):
                        for fname in filenames:
                            if self._is_cancelled:
                                sftp.close()
                                ssh_client.close()
                                self.finished.emit(False, "Cancelled by user.")
                                return

                            s_file = os.path.join(dirpath, fname)
                            rel_to_src = os.path.relpath(s_file, src).replace("\\", "/").lstrip("/")
                            d_remote_file = posixpath.join(dest_remote, rel_to_src)

                            percent = int((processed_count / total_files) * 100)
                            self.progress.emit(min(percent, 99), f"Restoring to {ip}: {fname}")

                            if sftp_exists(d_remote_file) and not self.overwrite_all:
                                self.sync_event.clear()
                                self.ask_overwrite.emit(f"{username}@{ip}:{d_remote_file}")
                                self.sync_event.wait()
                                if self._is_cancelled or self.user_action == "Cancel":
                                    sftp.close()
                                    ssh_client.close()
                                    self.finished.emit(False, "Cancelled by user.")
                                    return
                                elif self.user_action == "YesToAll":
                                    self.overwrite_all = True
                                elif self.user_action == "No":
                                    processed_count += 1
                                    continue

                            while True:
                                if self._is_cancelled:
                                    sftp.close()
                                    ssh_client.close()
                                    self.finished.emit(False, "Cancelled by user.")
                                    return
                                try:
                                    sftp_makedirs(posixpath.dirname(d_remote_file))
                                    sftp.put(s_file, d_remote_file)
                                    restored_count += 1
                                    processed_count += 1
                                    break
                                except Exception as e:
                                    if self.skip_all_errors:
                                        processed_count += 1
                                        break
                                    self.sync_event.clear()
                                    self.ask_error.emit(f"{username}@{ip}:{d_remote_file}", str(e))
                                    self.sync_event.wait()
                                    if self.user_action == "Retry":
                                        continue
                                    elif self.user_action == "Skip":
                                        processed_count += 1
                                        break
                                    elif self.user_action == "SkipAll":
                                        self.skip_all_errors = True
                                        processed_count += 1
                                        break
                                    elif self.user_action == "Abort" or self._is_cancelled:
                                        sftp.close()
                                        ssh_client.close()
                                        self.finished.emit(False, "Aborted by user.")
                                        return
                else:
                    if self._is_cancelled:
                        sftp.close()
                        ssh_client.close()
                        self.finished.emit(False, "Cancelled by user.")
                        return

                    fname = os.path.basename(src)
                    percent = int((processed_count / total_files) * 100)
                    self.progress.emit(min(percent, 99), f"Restoring to {ip}: {fname}")

                    if sftp_exists(dest_remote) and not self.overwrite_all:
                        self.sync_event.clear()
                        self.ask_overwrite.emit(f"{username}@{ip}:{dest_remote}")
                        self.sync_event.wait()
                        if self._is_cancelled or self.user_action == "Cancel":
                            sftp.close()
                            ssh_client.close()
                            self.finished.emit(False, "Cancelled by user.")
                            return
                        elif self.user_action == "YesToAll":
                            self.overwrite_all = True
                        elif self.user_action == "No":
                            processed_count += 1
                            continue

                    while True:
                        if self._is_cancelled:
                            sftp.close()
                            ssh_client.close()
                            self.finished.emit(False, "Cancelled by user.")
                            return
                        try:
                            sftp_makedirs(posixpath.dirname(dest_remote))
                            sftp.put(src, dest_remote)
                            restored_count += 1
                            processed_count += 1
                            break
                        except Exception as e:
                            if self.skip_all_errors:
                                processed_count += 1
                                break
                            self.sync_event.clear()
                            self.ask_error.emit(f"{username}@{ip}:{dest_remote}", str(e))
                            self.sync_event.wait()
                            if self.user_action == "Retry":
                                continue
                            elif self.user_action == "Skip":
                                processed_count += 1
                                break
                            elif self.user_action == "SkipAll":
                                self.skip_all_errors = True
                                processed_count += 1
                                break
                            elif self.user_action == "Abort" or self._is_cancelled:
                                sftp.close()
                                ssh_client.close()
                                self.finished.emit(False, "Aborted by user.")
                                return

        sftp.close()
        ssh_client.close()
        self.progress.emit(100, "Done")
        target_display = f"{username}@{ip}:{resolved_default_path}" if resolved_default_path else f"{username}@{ip}"
        self.finished.emit(
            True,
            f"Paste operation finished via SSH.\nSuccessfully restored {restored_count} components into:\n{target_display}"
        )

    def _run_scp_restore(self, ssh_target, total_files):
        processed_count = 0
        restored_count = 0
        remote_base = self.target_remote_path.replace("\\", "/") if self.target_remote_path else ""

        for rec in self.selected_records_data:
            if self._is_cancelled:
                self.finished.emit(False, "Cancelled by user.")
                return

            current_remote_base = remote_base or rec.get("RootPath", "").replace("\\", "/")
            if not current_remote_base:
                continue

            record_folder = rec["_folder"]

            for rel in rec.get("RelativePathList", []):
                if self._is_cancelled:
                    self.finished.emit(False, "Cancelled by user.")
                    return

                src = os.path.join(record_folder, rel)
                if not os.path.exists(src):
                    continue

                rel_posix = rel.replace("\\", "/").strip("/")
                remote_base_norm = current_remote_base.replace("\\", "/").rstrip("/")

                if remote_base_norm.endswith("/" + rel_posix) or remote_base_norm == rel_posix:
                    dest_remote = remote_base_norm
                elif posixpath.basename(remote_base_norm) == posixpath.basename(rel_posix) and len(rec.get("RelativePathList", [])) == 1:
                    dest_remote = remote_base_norm
                else:
                    dest_remote = posixpath.join(remote_base_norm, rel_posix)

                fname = os.path.basename(src)
                percent = int((processed_count / total_files) * 100)
                self.progress.emit(min(percent, 99), f"Restoring to {ssh_target}: {fname}")

                parent_remote = posixpath.dirname(dest_remote)
                if parent_remote and parent_remote != ".":
                    subprocess.run(
                        ["ssh", ssh_target, f"mkdir -p '{parent_remote}'"],
                        capture_output=True,
                        creationflags=NO_WINDOW_FLAGS
                    )

                scp_cmd = ["scp", "-r", src, f"{ssh_target}:{dest_remote}"]
                res = subprocess.run(
                    scp_cmd,
                    capture_output=True, text=True,
                    creationflags=NO_WINDOW_FLAGS
                )
                if res.returncode == 0:
                    restored_count += 1
                    processed_count += 1
                else:
                    if self.skip_all_errors:
                        processed_count += 1
                        continue
                    self.sync_event.clear()
                    self.ask_error.emit(f"{src} -> {ssh_target}:{dest_remote}", res.stderr)
                    self.sync_event.wait()
                    if self.user_action == "Skip":
                        processed_count += 1
                    elif self.user_action == "SkipAll":
                        self.skip_all_errors = True
                        processed_count += 1
                    elif self.user_action == "Abort" or self._is_cancelled:
                        self.finished.emit(False, "Paste operation aborted.")
                        return

        self.progress.emit(100, "Done")
        target_display = f"{ssh_target}:{remote_base}" if remote_base else ssh_target
        self.finished.emit(
            True,
            f"Paste operation finished via OpenSSH.\nSuccessfully restored {restored_count} components into:\n{target_display}"
        )


# ---------------- SSH CONNECTION DIALOG ----------------
class SSHConnectionDialog(QDialog):
    """
    /*
     * SSH Connection Setup Dialog (.1.)
     */
    """
    def __init__(self, parent=None, default_ip="", default_username="", default_password="", save_default=True):
        super().__init__(parent)
        self.setWindowTitle("SSH Connection")
        self.setWindowIcon(get_app_icon())
        self.setModal(True)
        self.resize(380, 200)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        form_layout = QGridLayout()
        form_layout.setSpacing(10)
        form_layout.setColumnStretch(1, 1)

        lbl_ip = QLabel("IP / Host")
        self.input_ip = QLineEdit()
        self.input_ip.setPlaceholderText("IP address or host (e.g. coder.coffee-opera)")
        self.input_ip.setText(default_ip)

        lbl_user = QLabel("Username")
        self.input_user = QLineEdit()
        self.input_user.setPlaceholderText("Username (optional)")
        self.input_user.setText(default_username)

        lbl_pass = QLabel("Password")
        self.input_pass = QLineEdit()
        self.input_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_pass.setPlaceholderText("Password (optional if using SSH key/agent)")
        self.input_pass.setText(default_password)

        form_layout.addWidget(lbl_ip, 0, 0)
        form_layout.addWidget(self.input_ip, 0, 1)
        form_layout.addWidget(lbl_user, 1, 0)
        form_layout.addWidget(self.input_user, 1, 1)
        form_layout.addWidget(lbl_pass, 2, 0)
        form_layout.addWidget(self.input_pass, 2, 1)

        layout.addLayout(form_layout)

        self.chk_save = QCheckBox("Save connection info.")
        self.chk_save.setChecked(save_default)
        layout.addWidget(self.chk_save)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("CANCEL")
        self.btn_ok = QPushButton("OKE")
        self.btn_ok.setDefault(True)

        self.btn_cancel.setMinimumWidth(80)
        self.btn_ok.setMinimumWidth(80)

        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_ok)
        layout.addLayout(btn_layout)

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self.handle_ok)

    def handle_ok(self):
        ip = self.input_ip.text().strip()
        user = self.input_user.text().strip()
        pwd = self.input_pass.text()

        if not ip:
            QMessageBox.warning(self, "Input Required", "Please enter an IP address or Host.")
            self.input_ip.setFocus()
            return

        if self.chk_save.isChecked():
            save_ssh_config(ip, user, pwd)

        self.accept()

    def get_connection_info(self):
        return {
            "ip": self.input_ip.text().strip(),
            "username": self.input_user.text().strip(),
            "password": self.input_pass.text(),
            "save": self.chk_save.isChecked()
        }


# ---------------- PASSWORD CELL WIDGET ----------------
class PasswordCellWidget(QWidget):
    def __init__(self, password="", parent=None):
        super().__init__(parent)
        self.password = password or ""
        self.is_hidden = True

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        self.label = QLabel()
        self.btn_toggle = QPushButton("Show")
        self.btn_toggle.setFixedWidth(60)
        self.btn_toggle.setStyleSheet("padding: 2px 4px; font-size: 11px;")

        if not self.password:
            self.label.setText("N/A")
            self.btn_toggle.setEnabled(False)
            self.btn_toggle.setText("N/A")
        else:
            self.label.setText("••••••••")
            self.btn_toggle.clicked.connect(self.toggle_visibility)

        layout.addWidget(self.label, 1)
        layout.addWidget(self.btn_toggle)

    def toggle_visibility(self):
        if self.is_hidden:
            self.label.setText(self.password)
            self.btn_toggle.setText("Hide")
            self.is_hidden = False
        else:
            self.label.setText("••••••••")
            self.btn_toggle.setText("Show")
            self.is_hidden = True


# ---------------- SSH HOST MANAGER DIALOG ----------------
class SSHHostManagerDialog(QDialog):
    """
    /*
     * SSH Host Manager Dialog (File > Open SSH config)
     */
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SSH Host List")
        self.setWindowIcon(get_app_icon())
        self.resize(750, 420)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)

        title_lbl = QLabel("SSH host list")
        title_font = title_lbl.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 2)
        title_lbl.setFont(title_font)
        layout.addWidget(title_lbl)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["No.", "IP/Name", "Username", "Password", "Updated date"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)

        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        self.table.doubleClicked.connect(self.handle_edit)

        layout.addWidget(self.table)

        # Action Buttons Layout
        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("+ Add Host")
        self.btn_edit = QPushButton("Edit")
        self.btn_delete = QPushButton("Delete")
        self.btn_test = QPushButton("Test")
        self.btn_close = QPushButton("Close")

        self.btn_add.clicked.connect(self.handle_add)
        self.btn_edit.clicked.connect(self.handle_edit)
        self.btn_delete.clicked.connect(self.handle_delete)
        self.btn_test.clicked.connect(self.handle_test)
        self.btn_close.clicked.connect(self.accept)

        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_edit)
        btn_layout.addWidget(self.btn_delete)
        btn_layout.addWidget(self.btn_test)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_close)
        layout.addLayout(btn_layout)

        self.hosts_data = []
        self.populate_table()

    def populate_table(self):
        self.hosts_data = get_all_known_ssh_hosts()
        self.table.setRowCount(len(self.hosts_data))

        for row, h in enumerate(self.hosts_data):
            # Column 0: No.
            item_no = QTableWidgetItem(str(row + 1))
            item_no.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, item_no)

            # Column 1: IP/Name
            item_ip = QTableWidgetItem(h.get("ip", ""))
            self.table.setItem(row, 1, item_ip)

            # Column 2: Username
            item_user = QTableWidgetItem(h.get("username", "") or "N/A")
            item_user.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 2, item_user)

            # Column 3: Password with Show/Hide button
            pwd = h.get("password", "")
            cell_widget = PasswordCellWidget(pwd)
            self.table.setCellWidget(row, 3, cell_widget)

            # Column 4: Updated date
            item_date = QTableWidgetItem(h.get("updated_at", "") or "N/A")
            item_date.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 4, item_date)

    def get_selected_host(self):
        row = self.table.currentRow()
        if 0 <= row < len(self.hosts_data):
            return self.hosts_data[row]
        return None

    def show_context_menu(self, pos):
        menu = QMenu(self)
        act_edit = menu.addAction("Edit")
        act_delete = menu.addAction("Delete")
        act_test = menu.addAction("Test connection")
        menu.addSeparator()
        act_add = menu.addAction("+ Add Host")

        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if action == act_edit:
            self.handle_edit()
        elif action == act_delete:
            self.handle_delete()
        elif action == act_test:
            self.handle_test()
        elif action == act_add:
            self.handle_add()

    def handle_add(self):
        dlg = SSHConnectionDialog(self, default_ip="", default_username="", default_password="", save_default=True)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.populate_table()

    def handle_edit(self):
        host = self.get_selected_host()
        if not host:
            QMessageBox.warning(self, "No Host Selected", "Please select an SSH host to edit.")
            return

        dlg = SSHConnectionDialog(
            self,
            default_ip=host.get("ip", ""),
            default_username=host.get("username", "") if host.get("username") != "N/A" else "",
            default_password=host.get("password", ""),
            save_default=True
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.populate_table()

    def handle_delete(self):
        host = self.get_selected_host()
        if not host:
            QMessageBox.warning(self, "No Host Selected", "Please select an SSH host to delete.")
            return

        ip = host.get("ip")
        if host.get("source") == "openssh":
            QMessageBox.information(
                self,
                "Read-only Host",
                f"Host '{ip}' is loaded from OpenSSH config (.ssh_config or ~/.ssh/config) in read-only mode.\nTo remove it, modify your system SSH config file."
            )
            return

        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete host '{ip}' from stasher_ssh_config.json?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            delete_ssh_host(ip)
            self.populate_table()

    def handle_test(self):
        host = self.get_selected_host()
        if not host:
            QMessageBox.warning(self, "No Host Selected", "Please select an SSH host to test.")
            return

        ip = host.get("ip")
        username = host.get("username")
        if username == "N/A":
            username = ""
        password = host.get("password", "")

        ssh_target = f"{username}@{ip}" if username else ip

        self.test_progress = QProgressDialog(f"Testing connection to {ssh_target}...", "Cancel", 0, 0, self)
        self.test_progress.setWindowTitle("Testing SSH Connection")
        self.test_progress.setWindowModality(Qt.WindowModality.WindowModal)
        self.test_progress.setMinimumDuration(0)
        self.test_progress.setValue(0)

        self.test_worker = SSHTestWorker(ip, username, password)
        self.test_worker.finished.connect(lambda ok, err: self.on_test_finished(ssh_target, ok, err))
        self.test_progress.canceled.connect(self.test_worker.cancel)
        self.test_worker.start()
        self.test_progress.show()

    def on_test_finished(self, ssh_target, is_alive, error_msg):
        if hasattr(self, 'test_progress') and self.test_progress:
            self.test_progress.close()
        if is_alive:
            QMessageBox.information(self, "SSH Connection Test", f"Success! Host '{ssh_target}' is reachable and active.")
        else:
            QMessageBox.warning(self, "SSH Connection Test", f"Failed to connect to '{ssh_target}':\n{error_msg}")


# ---------------- CHANGE CONFIG PATH DIALOG ----------------
class ChangeConfigPathDialog(QDialog):
    """
    /*
     * Dialog to change config file path (.4.)
     */
    """
    def __init__(self, current_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Change config path")
        self.setWindowIcon(get_app_icon())
        self.resize(500, 140)
        self.setModal(True)
        self.new_path = None

        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        form_layout = QHBoxLayout()
        lbl = QLabel("Path")
        lbl.setMinimumWidth(40)
        self.input_path = QLineEdit()
        self.input_path.setText(os.path.abspath(current_path))
        self.btn_browse = QPushButton("...")
        self.btn_browse.setFixedWidth(35)
        self.btn_browse.clicked.connect(self.handle_browse)

        form_layout.addWidget(lbl)
        form_layout.addWidget(self.input_path, 1)
        form_layout.addWidget(self.btn_browse)
        layout.addLayout(form_layout)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_close = QPushButton("Close")
        self.btn_done = QPushButton("Done")
        self.btn_done.setDefault(True)

        self.btn_close.clicked.connect(self.reject)
        self.btn_done.clicked.connect(self.handle_done)

        btn_layout.addWidget(self.btn_close)
        btn_layout.addWidget(self.btn_done)
        layout.addLayout(btn_layout)

    def handle_browse(self):
        cur = self.input_path.text().strip()
        dir_hint = os.path.dirname(cur) if os.path.exists(os.path.dirname(cur)) else ""
        selected, _ = QFileDialog.getOpenFileName(self, "Select Config File", dir_hint, "JSON Files (*.json);;All Files (*)")
        if selected:
            self.input_path.setText(os.path.abspath(selected))

    def handle_done(self):
        path = self.input_path.text().strip().strip('"').strip("'")
        if not path:
            QMessageBox.warning(self, "Input Required", "Please enter a valid config path.")
            return
        if not os.path.exists(path):
            reply = QMessageBox.question(
                self,
                "File Not Found",
                f"File '{path}' does not exist.\nDo you want to create a new config at this path?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            try:
                os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
                default_data = {"PATH_STORAGE": DEFAULT_STORAGE}
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(default_data, f, indent=4)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to create config file:\n{str(e)}")
                return

        self.new_path = os.path.abspath(path)
        self.accept()


# ---------------- CHANGE APP FOLDER DIALOG ----------------
class ChangeAppFolderDialog(QDialog):
    """
    /*
     * Dialog to change app storage folder path (.5.)
     */
    """
    def __init__(self, current_folder, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Change app folder path")
        self.setWindowIcon(get_app_icon())
        self.resize(500, 140)
        self.setModal(True)
        self.new_folder = None

        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        form_layout = QHBoxLayout()
        lbl = QLabel("Path")
        lbl.setMinimumWidth(40)
        self.input_path = QLineEdit()
        self.input_path.setText(os.path.abspath(current_folder))
        self.btn_browse = QPushButton("...")
        self.btn_browse.setFixedWidth(35)
        self.btn_browse.clicked.connect(self.handle_browse)

        form_layout.addWidget(lbl)
        form_layout.addWidget(self.input_path, 1)
        form_layout.addWidget(self.btn_browse)
        layout.addLayout(form_layout)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_close = QPushButton("Close")
        self.btn_done = QPushButton("Done")
        self.btn_done.setDefault(True)

        self.btn_close.clicked.connect(self.reject)
        self.btn_done.clicked.connect(self.handle_done)

        btn_layout.addWidget(self.btn_close)
        btn_layout.addWidget(self.btn_done)
        layout.addLayout(btn_layout)

    def handle_browse(self):
        cur = self.input_path.text().strip()
        dir_hint = cur if os.path.isdir(cur) else os.path.dirname(cur)
        selected = QFileDialog.getExistingDirectory(self, "Select App Storage Folder", dir_hint)
        if selected:
            self.input_path.setText(os.path.abspath(selected))

    def handle_done(self):
        path = self.input_path.text().strip().strip('"').strip("'")
        if not path:
            QMessageBox.warning(self, "Input Required", "Please enter a valid folder path.")
            return
        if not os.path.exists(path):
            reply = QMessageBox.question(
                self,
                "Folder Not Found",
                f"Folder '{path}' does not exist.\nDo you want to create it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            try:
                os.makedirs(path, exist_ok=True)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to create folder:\n{str(e)}")
                return

        self.new_folder = os.path.abspath(path)
        self.accept()


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
        self.setWindowIcon(get_app_icon())
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

        # Set Window Icon if available
        app_icon = get_app_icon()
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)

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
        self.View_Button_SSHConfig = QPushButton("SSH")
        self.View_Button_SSHConfig.setToolTip("Configure SSH Connection")
        self.View_Button_SSHConfig.clicked.connect(self.trigger_ssh_setup_dialog)
        paste_layout.addWidget(self.View_Button_SSHConfig)
        view_layout.addLayout(paste_layout)

        self.View_Path2PatchFolder_Value.setPlaceholderText(
            "Paste destination: local path, fus@<IP>:<path>, or <unix_path>"
        )

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

        # Setup File Menu (.1. - .5.)
        self.menuFile.clear()
        self.actionOpen_SSH_config = self.menuFile.addAction("Open SSH config")
        self.actionOpen_SSH_config.triggered.connect(self.open_ssh_host_manager)

        self.actionOpen_config = self.menuFile.addAction("Open config")
        self.actionOpen_config.triggered.connect(self.open_system_config_file)

        self.actionChange_config_path = self.menuFile.addAction("Change config path")
        self.actionChange_config_path.triggered.connect(self.open_change_config_path_dialog)

        self.actionChange_app_folder = self.menuFile.addAction("Change app folder")
        self.actionChange_app_folder.triggered.connect(self.open_change_app_folder_dialog)

        self.menuFile.addSeparator()

        self.actionClose = self.menuFile.addAction("Close")
        self.actionClose.triggered.connect(self.close)

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
        try:
            # Verify valid core directory
            if not os.path.exists(self.storage_path):
                os.makedirs(self.storage_path, exist_ok=True)

            # Loop active local archives
            if os.path.exists(self.storage_path):
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
        except Exception as e:
            print(f"Warning: Could not access storage path '{self.storage_path}': {e}")

        self.Summary_NumberOfRecords_Value.setText(str(len(self.records)))
        self.render_records_to_tree_view(self.records)

    """
    /*
     * Populates the TreeWidget with cached record data.
     */
    """
    def render_records_to_tree_view(self, data_list):
        self.View_AllRecordsTable.setUpdatesEnabled(False)
        try:
            self.View_AllRecordsTable.clear()
            items_to_add = []

            for idx, rec in enumerate(data_list):
                if rec["_folder"] in self.hidden_folders:
                    continue

                root_item = QTreeWidgetItem([
                    str(idx + 1),
                    rec.get("Name", "Unknown Name"),
                    rec.get("RootPath", "N/A"),
                    str(len(rec.get("RelativePathList", []))),
                    rec.get("Desc", "")
                ])

                update_time = rec.get("UpdateRecordTime", "<2026/01/01-00:00:00>")
                for col in range(root_item.columnCount()):
                    root_item.setToolTip(col, f"UpdateRecordTime: {update_time}")

                root_item.setData(0, Qt.ItemDataRole.UserRole, rec)

                for p in rec.get("RelativePathList", []):
                    icon = "📁" if p.endswith("/") else "📄"
                    child_item = QTreeWidgetItem(["", "", "", f"{icon} {p}", ""])
                    root_item.addChild(child_item)

                for selected_rec in self.selected_records_data:
                    if selected_rec["_folder"] == rec["_folder"]:
                        self.apply_row_light_mode_color(root_item, highlight=True)

                items_to_add.append(root_item)

            self.View_AllRecordsTable.addTopLevelItems(items_to_add)
        finally:
            self.View_AllRecordsTable.setUpdatesEnabled(True)

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
    def open_ssh_host_manager(self):
        """
        Opens internal SSH host manager dialog (.1.)
        """
        dlg = SSHHostManagerDialog(self)
        dlg.exec()

    def open_system_config_file(self):
        """
        Opens stasher_config.json via default system application (.2.)
        """
        config_path = os.path.abspath(CONFIG_FILE)
        if not os.path.exists(config_path):
            load_config()
        try:
            if sys.platform.startswith('win'):
                os.startfile(config_path)
            elif sys.platform.startswith('darwin'):
                subprocess.run(['open', config_path])
            else:
                subprocess.run(['xdg-open', config_path])
        except Exception as e:
            QMessageBox.warning(self, "Open Config Error", f"Could not open config file:\n{str(e)}")

    def open_change_config_path_dialog(self):
        """
        Opens dialog to change config file path (.4.)
        """
        global CONFIG_FILE
        dlg = ChangeConfigPathDialog(CONFIG_FILE, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.new_path:
            CONFIG_FILE = dlg.new_path
            self.Summary_Path2AppConfig_Value.setText(os.path.abspath(CONFIG_FILE))
            cfg = load_config()
            new_storage = cfg.get("PATH_STORAGE", DEFAULT_STORAGE)
            if new_storage != self.storage_path:
                self.storage_path = new_storage
                self.Summary_Path2AppFolder_Value.setText(self.storage_path)
                self.scan_storage_to_ram()
            QMessageBox.information(self, "Config Path Updated", f"Config path changed to:\n{CONFIG_FILE}")

    def open_change_app_folder_dialog(self):
        """
        Opens dialog to change app storage folder (.5.)
        """
        dlg = ChangeAppFolderDialog(self.storage_path, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.new_folder:
            self.storage_path = dlg.new_folder
            self.Summary_Path2AppFolder_Value.setText(self.storage_path)
            cfg = load_config()
            cfg["PATH_STORAGE"] = self.storage_path
            try:
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, indent=4)
            except Exception as e:
                print(f"Error saving updated storage path to {CONFIG_FILE}: {e}")
            self.scan_storage_to_ram()
            QMessageBox.information(self, "App Folder Updated", f"App storage folder changed to:\n{self.storage_path}")

    def trigger_ssh_setup_dialog(self):
        """
        Explicitly triggers the SSH Connection popup (.1.)
        """
        cfg = load_ssh_json()
        dlg = SSHConnectionDialog(
            self,
            default_ip=cfg.get("ip", ""),
            default_username=cfg.get("username", ""),
            default_password=cfg.get("password", ""),
            save_default=True
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            info = dlg.get_connection_info()
            QMessageBox.information(
                self, "SSH Connection Configured",
                f"SSH connection saved for {info['username'] or 'default'}@{info['ip']} in {SSH_CONFIG_JSON}."
            )

    """
    /*
     * Restores sequentially multiple selected records to a specified destination (Local or SSH).
     */
    """
    def execute_paste_patch_logic(self):
        # Abort action parameter constraints
        if not self.selected_records_data:
            QMessageBox.warning(self, "No Record Selected", "Please right-click and 'Select this record' before pasting.")
            return

        user_paste_path = self.View_Path2PatchFolder_Value.text().strip().strip('"').strip("'")
        dest_to_check = user_paste_path
        if not dest_to_check:
            first_root = self.selected_records_data[0].get("RootPath", "") if self.selected_records_data else ""
            dest_to_check = first_root

        target_info = parse_destination_type(dest_to_check)
        if target_info["is_ssh"]:
            conn = get_ssh_connection(ip=target_info["ip"], username=target_info["username"])
            if not conn or not conn.get("ip"):
                # SSH host not found in config (.6.) -> open SSH connection dialog
                dlg = SSHConnectionDialog(
                    self,
                    default_ip=target_info["ip"] or "",
                    default_username=target_info["username"] or "",
                    default_password="",
                    save_default=True
                )
                if dlg.exec() != QDialog.DialogCode.Accepted:
                    return
                conn = dlg.get_connection_info()

            self.execute_ssh_paste(
                ip=conn["ip"],
                username=conn.get("username", "") or target_info["username"] or "",
                password=conn.get("password", ""),
                default_remote_path=target_info["remote_path"],
                port=conn.get("port"),
                key_filename=conn.get("key_filename")
            )
            return
        else:
            if dest_to_check and not os.path.exists(dest_to_check):
                # Destination path not found locally (.6.) -> open SSH Connection Dialog
                dlg = SSHConnectionDialog(
                    self,
                    default_ip="",
                    default_username="",
                    default_password="",
                    save_default=True
                )
                if dlg.exec() == QDialog.DialogCode.Accepted:
                    conn = dlg.get_connection_info()
                    self.execute_ssh_paste(
                        ip=conn["ip"],
                        username=conn.get("username", ""),
                        password=conn.get("password", ""),
                        default_remote_path=dest_to_check,
                        port=conn.get("port"),
                        key_filename=conn.get("key_filename")
                    )
                    return
                # If user cancelled SSH setup, ask if they want to create the local folder
                reply = QMessageBox.question(
                    self,
                    "Destination Not Found",
                    f"Local path does not exist:\n{dest_to_check}\n\nDo you want to create this local directory and paste here?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return

            self.execute_local_paste(dest_to_check)
            return

    """
    /*
     * Asynchronous restoration routine (Local and SSH) to prevent UI freezing.
     */
    """
    def start_restore_worker(self, is_ssh, ssh_conn=None, target_remote_path="", user_paste_path=""):
        self.paste_progress_dialog = QProgressDialog("Preparing paste operation...", "Cancel", 0, 100, self)
        self.paste_progress_dialog.setWindowTitle("Paste Progress")
        self.paste_progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.paste_progress_dialog.setMinimumDuration(0)
        self.paste_progress_dialog.setValue(0)

        for label in self.paste_progress_dialog.findChildren(QLabel):
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self.restore_worker = RestoreWorker(
            selected_records_data=self.selected_records_data,
            is_ssh=is_ssh,
            ssh_conn=ssh_conn,
            target_remote_path=target_remote_path,
            user_paste_path=user_paste_path
        )
        self.restore_worker.progress.connect(self.on_restore_progress)
        self.restore_worker.ask_overwrite.connect(self.on_restore_ask_overwrite)
        self.restore_worker.ask_error.connect(self.on_restore_ask_error)
        self.restore_worker.finished.connect(self.on_restore_finished)
        self.paste_progress_dialog.canceled.connect(self.restore_worker.cancel)

        self.restore_worker.start()
        self.paste_progress_dialog.show()

    def on_restore_progress(self, percent, msg):
        if hasattr(self, "paste_progress_dialog") and self.paste_progress_dialog:
            self.paste_progress_dialog.setValue(percent)
            self.paste_progress_dialog.setLabelText(msg)

    def on_restore_ask_overwrite(self, filepath):
        ans = self.prompt_overwrite_confirmation_dialog(filepath)
        if ans == QMessageBox.StandardButton.YesToAll:
            self.restore_worker.set_user_action("YesToAll")
        elif ans == QMessageBox.StandardButton.Yes:
            self.restore_worker.set_user_action("Yes")
        elif ans == QMessageBox.StandardButton.No:
            self.restore_worker.set_user_action("No")
        else:
            self.restore_worker.set_user_action("Cancel")

    def on_restore_ask_error(self, filepath, error_msg):
        ans = self.prompt_copy_error_dialog(filepath, error_msg)
        if ans == "SkipAll":
            self.restore_worker.set_user_action("SkipAll")
        elif ans == "Ignore":
            self.restore_worker.set_user_action("Skip")
        elif ans == "Abort":
            self.restore_worker.set_user_action("Abort")
        else:
            self.restore_worker.set_user_action("Retry")

    def on_restore_finished(self, success, message):
        if hasattr(self, "paste_progress_dialog") and self.paste_progress_dialog:
            self.paste_progress_dialog.close()

        if success:
            QMessageBox.information(self, "Restore Successful", message)
        else:
            if "Cancelled by user" in message:
                QMessageBox.warning(self, "Cancelled", "Paste operation cancelled by user.")
            elif "SSH Connection Failed" in message:
                reply = QMessageBox.question(
                    self,
                    "SSH Connection Failed",
                    f"{message}\n\nWould you like to configure/update the SSH connection?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self.trigger_ssh_setup_dialog()
            else:
                QMessageBox.warning(self, "Paste Completed with Warnings", message)

    def execute_local_paste(self, user_paste_path):
        self.start_restore_worker(is_ssh=False, user_paste_path=user_paste_path)

    def execute_ssh_paste(self, ip, username, password, default_remote_path, port=None, key_filename=None):
        conn = {
            "ip": ip,
            "username": username,
            "password": password,
            "port": port,
            "key_filename": key_filename
        }
        self.start_restore_worker(is_ssh=True, ssh_conn=conn, target_remote_path=default_remote_path)

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
    # Hide black console window on Windows and set explicit AppUserModelID
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ngxx-fus.stasher.app.1")
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd != 0:
                ctypes.windll.user32.ShowWindow(hwnd, 0)  # 0 = SW_HIDE
        except Exception:
            pass

    app = QApplication(sys.argv)
    
    app_icon = get_app_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)
    
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
