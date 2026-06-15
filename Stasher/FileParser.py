import os
import sys
import shutil
import json
import yaml
from datetime import datetime

# --- CONFIGURATION INITIALIZATION ---
CONFIG_FILE = "stasher_config.json"
DEFAULT_STORAGE = r"C:\Users\phu.nguyen-thanh\Documents\UserData"

def load_config():
    if not os.path.exists(CONFIG_FILE):
        default_config = {"PATH_STORAGE": DEFAULT_STORAGE}
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=4)
        return default_config
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

class FileStasher:
    def __init__(self):
        config = load_config()
        self.storage_path = config.get("PATH_STORAGE", DEFAULT_STORAGE)
        
        if not os.path.exists(self.storage_path):
            os.makedirs(self.storage_path)
            
        self.records = []
        self.selected_record = None
        self.scan_storage()

    def scan_storage(self):
        """Scans the storage directory to load all records."""
        self.records = []
        for item in os.listdir(self.storage_path):
            folder_path = os.path.join(self.storage_path, item)
            yml_path = os.path.join(folder_path, "RecordStructure.yml")
            
            if os.path.isdir(folder_path) and os.path.exists(yml_path):
                try:
                    with open(yml_path, 'r', encoding='utf-8') as f:
                        data = yaml.safe_load(f)
                        self.records.append(data)
                except Exception as e:
                    print(f"[!] Error loading {yml_path}: {e}")

    def get_info(self, record, key):
        """Helper to extract a specific field from the GeneralInfo YAML array."""
        for item in record.get('GeneralInfo', []):
            if key in item:
                return item[key]
        return None

    def print_summary(self):
        print("\n" + "="*50)
        print(f"Storage path: {self.storage_path}")
        print(f"Number of record(s): {len(self.records)}")

    def new_record(self):
        print("\n--- New record ---")
        name = input("    Name: ").strip()
        
        print("    Desc: (Type your description. Press Enter on an empty line to save)")
        desc_lines = []
        while True:
            line = input("      > ")
            if line == "":
                break
            desc_lines.append(line)
        desc = "\n".join(desc_lines)
        
        # PATCHED: Strip quotes from Windows "Copy as path"
        root_path = input("\n    RootPath: ").strip(" \"'")
        if not os.path.isdir(root_path):
            print("    [!] Invalid RootPath or directory does not exist. Aborting.")
            return
        
        # Standardize RootPath
        root_path = os.path.abspath(root_path).replace("\\", "/")

        print("\n    FileList: (Enter relative or absolute paths. Type 'u' to undo. Press Enter on empty line to save)")
        relative_list = []
        while True:
            # PATCHED: Strip quotes from Windows "Copy as path"
            filepath = input("      Path > ").strip(" \"'")
            if filepath == "":
                break
            
            if filepath.lower() in ['u', 'undo']:
                if relative_list:
                    removed = relative_list.pop()
                    print(f"        [-] Removed: {removed}")
                else:
                    print("        [!] List is already empty.")
                continue
            
            # --- PATCH: Absolute Path & Common Root Resolution ---
            is_absolute = os.path.isabs(filepath)
            full_path = filepath

            if is_absolute:
                try:
                    common_root = os.path.commonpath([root_path, filepath]).replace("\\", "/")
                    
                    # If the absolute path is outside the current RootPath
                    if os.path.normpath(common_root) != os.path.normpath(root_path):
                        print(f"        [!] Absolute path detected outside current root.")
                        print(f"        [?] Discovered common root: {common_root}")
                        ans = input("        [?] Update RootPath for all recorded paths? (y/N): ")
                        
                        if ans.lower() == 'y':
                            # Rewrite all previously recorded relative paths to match the new RootPath
                            new_rel_list = []
                            for old_rel in relative_list:
                                old_abs = os.path.join(root_path, old_rel)
                                new_rel = os.path.relpath(old_abs, common_root).replace("\\", "/")
                                if old_rel.endswith('/'): new_rel += '/'
                                new_rel_list.append(new_rel)
                            relative_list = new_rel_list
                            root_path = common_root
                            print(f"        [+] RootPath updated. All paths recalculated relative to: {root_path}")
                        else:
                            print("        [-] Ignored. Please enter a valid path.")
                            continue
                    
                    # Convert to relative path based on the (potentially updated) root_path
                    rel_path = os.path.relpath(full_path, root_path).replace("\\", "/")
                except ValueError:
                    print("        [!] Path is on a different drive. Cannot find common root. Try again.")
                    continue
            else:
                rel_path = filepath
                full_path = os.path.join(root_path, rel_path)

            # --- Validation & Appending ---
            if os.path.exists(full_path):
                standard_rel = rel_path.replace("\\", "/") 
                
                # If it's a directory, append a trailing slash
                if os.path.isdir(full_path) and not standard_rel.endswith('/'):
                    standard_rel += '/'

                if standard_rel not in relative_list:
                    relative_list.append(standard_rel)
                    target_type = "folder" if standard_rel.endswith('/') else "file"
                    print(f"        [+] Added {target_type}: {standard_rel}")
                else:
                    print("        [!] Path already in list.")
            else:
                print("        [!] Path not found. Please try again.")

        if not relative_list:
            print("[!] No files added. Aborting record creation.")
            return

        folder_name = f"Record_{datetime.now().strftime('%Y_%B_%d_%H%M%S')}"
        record_path = os.path.join(self.storage_path, folder_name)
        os.makedirs(record_path)

        for rel in relative_list:
            src = os.path.join(root_path, rel)
            dest = os.path.join(record_path, rel)
            
            if rel.endswith('/') or os.path.isdir(src):
                shutil.copytree(src, dest, dirs_exist_ok=True)
            else:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copy2(src, dest)

        record_data = {
            "GeneralInfo": [
                {"Name": name},
                {"Desc": desc},
                {"FolderName": folder_name},
                {"StoragePath": self.storage_path},
                {"Path2Record": os.path.join("${StoragePath}", folder_name)},
                {"RootPath": root_path},
                {"RelativePathList": relative_list}
            ]
        }

        with open(os.path.join(record_path, "RecordStructure.yml"), 'w', encoding='utf-8') as f:
            yaml.dump(record_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        
        self.records.append(record_data)
        print(f"\n[SUCCESS] Record '{name}' stashed successfully!")

    def list_records(self):
        print("\n--- Record List ---")
        if not self.records:
            print("  No records found.")
            return
            
        print(f"{'ID':<5} | {'NAME':<30} | {'FOLDER'}")
        print("-" * 65)
        for idx, rec in enumerate(self.records):
            name = self.get_info(rec, 'Name') or "Unknown"
            folder = self.get_info(rec, 'FolderName') or "Unknown"
            name = name[:27] + "..." if len(name) > 30 else name
            print(f"[{idx:<3}] | {name:<30} | {folder}")

    def search_records(self, by="name"):
        query = input(f"Enter {by} to search: ").lower()
        print("\n--- Search Results ---")
        found = False
        for idx, rec in enumerate(self.records):
            target = self.get_info(rec, 'Name') if by == "name" else self.get_info(rec, 'Desc')
            if target and query in target.lower():
                print(f"  [{idx}] {self.get_info(rec, 'Name')}")
                found = True
        if not found:
            print("  [!] No matching records found.")

    def select_record(self):
        self.list_records()
        if not self.records:
            return
            
        try:
            sel = input("\nEnter record ID to select (or 'q' to cancel): ").strip()
            if sel.lower() == 'q':
                return
            sel_idx = int(sel)
            if 0 <= sel_idx < len(self.records):
                self.selected_record = self.records[sel_idx]
            else:
                print("[!] Invalid ID.")
        except ValueError:
            print("[!] Please enter a valid number.")

    def delete_record(self):
        folder_name = self.get_info(self.selected_record, 'FolderName')
        path = os.path.join(self.storage_path, folder_name)
        name = self.get_info(self.selected_record, 'Name')
        
        confirm = input(f"Are you sure you want to DELETE '{name}'? (y/N): ")
        if confirm.lower() == 'y':
            try:
                shutil.rmtree(path)
                self.records.remove(self.selected_record)
                self.selected_record = None
                print("[SUCCESS] Record deleted.")
            except Exception as e:
                print(f"[ERROR] Could not delete record: {e}")

    def paste_record(self):
        name = self.get_info(self.selected_record, 'Name')
        desc = self.get_info(self.selected_record, 'Desc')
        root_path = self.get_info(self.selected_record, 'RootPath')
        folder_name = self.get_info(self.selected_record, 'FolderName')
        record_path = os.path.join(self.storage_path, folder_name)
        rel_list = self.get_info(self.selected_record, 'RelativePathList')

        print("\n--- Paste Record ---")
        print(f"    Name: {name}")
        print(f"    Desc: {desc}")
        print(f"    Original Root: {root_path}")
        
        # PATCHED: Strip quotes here as well just in case
        paste_path = input(f"\n    PastePath (Press Enter to use Original Root): ").strip(" \"'")
        if not paste_path:
            paste_path = root_path
            
        if not os.path.exists(paste_path):
            create = input(f"    [?] Directory '{paste_path}' does not exist. Create it? (y/N): ")
            if create.lower() == 'y':
                os.makedirs(paste_path)
            else:
                print("[!] Paste operation cancelled.")
                return

        print(f"\nRestoring files to {paste_path} ...")
        
        overwrite_all = False 

        for rel in rel_list:
            src = os.path.join(record_path, rel)
            dest = os.path.join(paste_path, rel)
            
            if not os.path.exists(src):
                print(f"  [!] Missing in stash: {rel}")
                continue

            if os.path.isdir(src):
                for dirpath, _, filenames in os.walk(src):
                    for fname in filenames:
                        s_file = os.path.join(dirpath, fname)
                        rel_to_src = os.path.relpath(s_file, src)
                        d_file = os.path.join(dest, rel_to_src)
                        
                        if os.path.exists(d_file) and not overwrite_all:
                            ans = input(f"  [?] File '{d_file}' exists. Overwrite? (y/N/A): ")
                            if ans.lower() == 'a':
                                overwrite_all = True
                            elif ans.lower() != 'y':
                                print(f"  [-] Skipped: {d_file}")
                                continue
                                
                        os.makedirs(os.path.dirname(d_file), exist_ok=True)
                        shutil.copy2(s_file, d_file)
                print(f"  [+] Restored Folder: {rel}")
            else:
                if os.path.exists(dest) and not overwrite_all:
                    ans = input(f"  [?] File '{dest}' exists. Overwrite? (y/N/A): ")
                    if ans.lower() == 'a':
                        overwrite_all = True
                    elif ans.lower() != 'y':
                        print(f"  [-] Skipped: {rel}")
                        continue

                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copy2(src, dest)
                print(f"  [+] Restored File: {rel}")
            
        print("[SUCCESS] Paste operation complete.")

    def run(self):
        while True:
            self.print_summary()
            
            if self.selected_record:
                print("Selected record:")
                print(f"    Name: {self.get_info(self.selected_record, 'Name')}")
                print(f"    Desc: {self.get_info(self.selected_record, 'Desc')}")
                print(f"    Root: {self.get_info(self.selected_record, 'RootPath')}")
                
                print("\nOption:")
                print("    d:  Deselect")
                print("    D:  Delete")
                print("    p:  Paste record into folder")
                print("    q:  Exit")
                
                choice = input("\nSelect option: ").strip()
                if choice == 'd':
                    self.selected_record = None
                elif choice == 'D':
                    self.delete_record()
                elif choice == 'p':
                    self.paste_record()
                elif choice == 'q':
                    sys.exit(0)
                else:
                    print("[!] Invalid option.")
                    
            else:
                print("Option:")
                print("    q:  Exit")
                print("    sn: Search by name")
                print("    sd: Search by description")
                print("    l:  List all records")
                print("    ss: Select record")
                print("    n:  New record")
                
                choice = input("\nSelect option: ").strip()
                if choice == 'q':
                    sys.exit(0)
                elif choice == 'sn':
                    self.search_records(by="name")
                elif choice == 'sd':
                    self.search_records(by="desc")
                elif choice == 'l':
                    self.list_records()
                elif choice == 'ss':
                    self.select_record()
                elif choice == 'n':
                    self.new_record()
                else:
                    print("[!] Invalid option.")

if __name__ == "__main__":
    app = FileStasher()
    app.run()