import os
import yaml

def get_stasher_version():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    yml_path = os.path.join(base_dir, "stasher_version.yml")
    with open(yml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    v = data.get("stasher", {})
    return f"{v.get('release', 1)}.{v.get('major_update', 0)}.{v.get('minor_update', 0)}"

if __name__ == "__main__":
    print(get_stasher_version())
