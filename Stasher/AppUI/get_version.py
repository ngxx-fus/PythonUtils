import os
import sys
import yaml

def get_stasher_version_parts():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    yml_path = os.path.join(base_dir, "stasher_version.yml")
    with open(yml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    v = data.get("stasher", {})
    rel = int(v.get('release', 1))
    maj = int(v.get('major_update', 0))
    min_u = int(v.get('minor_update', 0))
    return rel, maj, min_u

def get_stasher_version():
    rel, maj, min_u = get_stasher_version_parts()
    return f"{rel}.{maj}.{min_u}"

def generate_version_info_file():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    rel, maj, min_u = get_stasher_version_parts()
    ver_str = f"{rel}.{maj}.{min_u}"
    
    content = f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({rel}, {maj}, {min_u}, 0),
    prodvers=({rel}, {maj}, {min_u}, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', 'ngxx-fus'),
        StringStruct('FileDescription', 'Stasher Utility'),
        StringStruct('FileVersion', '{ver_str}'),
        StringStruct('InternalName', 'stasher'),
        StringStruct('LegalCopyright', 'Copyright (C) 2026 ngxx-fus'),
        StringStruct('OriginalFilename', 'stasher.exe'),
        StringStruct('ProductName', 'Stasher'),
        StringStruct('ProductVersion', '{ver_str}')])
      ]), 
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    out_path = os.path.join(base_dir, "file_version_info.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Generated {out_path} (version {ver_str})")
    return out_path

if __name__ == "__main__":
    if "--generate" in sys.argv:
        generate_version_info_file()
    else:
        print(get_stasher_version())
