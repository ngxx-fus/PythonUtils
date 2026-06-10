import os
import shutil
import yaml
import xml.etree.ElementTree as ET
from datetime import datetime

# ==============================================================================
# Define Global Paths & Variables
# ==============================================================================
FOLDER_PATH_PEAK = "/mnt/c/Users/phu.nguyen-thanh/Documents/WorkSpace/GitCloned/.peaks_original"

FOLDER_PATH_QUACKQUACK_DEBUG_INPUT = "/mnt/c/Users/phu.nguyen-thanh/Documents/WorkSpace/GitCloned/segger_rtt_quackquack_debug.h"
FOLDER_PATH_QUACKQUACK_DEBUG_OUTPUT = f"{FOLDER_PATH_PEAK}/test_files/src/segger_rtt_quackquack_debug.h"

XML_PATH_COMMON = f"{FOLDER_PATH_PEAK}/test_files/shared/common.xml"
YML_PATH_TOOLS_CFG = f"{FOLDER_PATH_PEAK}/test_files/shared/tools_cfg.yml"

# Configuration rule files
REPLACE_YML_TXT = "replace.yml.txt"
COMMENT_XML_TXT = "comment.xml.txt"

def log_info(message):
    """
    /*
     * @brief Logs an info message to the console with a timestamp.
     * @param message The message to log.
     * @return None
     */
    """
    print(f"[INFO] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {message}")
    
    # Return control to caller
    return

def log_error(message):
    """
    /*
     * @brief Logs an error message to the console with a timestamp.
     * @param message The message to log.
     * @return None
     */
    """
    print(f"[ERROR] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {message}")
    
    # Return control to caller
    return

def copy_debug_header(src_path, dest_path):
    """
    /*
     * @brief Copies the quackquack debug header to the destination.
     * @param src_path Source file path.
     * @param dest_path Destination file path.
     * @return None
     */
    """
    # Check if the source file exists in the file system
    if not os.path.exists(src_path):
        log_error(f"Source file not found: {src_path}")
        # Exit function early due to missing source file
        return
        
    dest_dir = os.path.dirname(dest_path)
    
    # Check if the destination directory exists
    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir)
        
    shutil.copy2(src_path, dest_path)
    log_info(f"File copied successfully to {dest_path}")
    
    # Return control to caller
    return

def patch_yaml_config(target_yml_path, rules_txt_path):
    """
    /*
     * @brief Updates the target YAML file based on key-value pairs provided in the rules file.
     * @param target_yml_path The target YAML file to be modified.
     * @param rules_txt_path The text file containing replacement rules in YAML format.
     * @return None
     */
    """
    # Check if both target YAML and rules files exist
    if not os.path.exists(target_yml_path) or not os.path.exists(rules_txt_path):
        log_error(f"Missing files. Target: {target_yml_path}, Rules: {rules_txt_path}")
        # Exit function early due to missing configuration files
        return
        
    # Try block to safely parse and manipulate YAML files
    try:
        # Open and load the replacement rules
        with open(rules_txt_path, 'r') as f:
            replacements = yaml.safe_load(f)
            
        # Open and load the target YAML configuration
        with open(target_yml_path, 'r') as f:
            target_data = yaml.safe_load(f)
            
        # Iterate over all rules provided in the replacement dictionary
        for key, value in replacements.items():
            # Check if the replacement key exists in the target YAML structure
            if key in target_data:
                target_data[key] = value
                
        # Open target file in write mode to dump the updated configuration
        with open(target_yml_path, 'w') as f:
            yaml.dump(target_data, f, default_flow_style=False, sort_keys=False)
            
        log_info(f"Successfully patched {target_yml_path}")
        
    # Catch any exceptions raised during YAML processing
    except Exception as e:
        log_error(f"Failed to process YAML: {e}")
        
    # Return control to caller
    return

def patch_xml_config(target_xml_path, tags_txt_path):
    """
    /*
     * @brief Reads a list of tags and comments out all elements inside those tags in the target XML.
     * @param target_xml_path The XML file to modify.
     * @param tags_txt_path The text file containing target tag names.
     * @return None
     */
    """
    # Check if both target XML and tag rules files exist
    if not os.path.exists(target_xml_path) or not os.path.exists(tags_txt_path):
        log_error(f"Missing files. Target: {target_xml_path}, Rules: {tags_txt_path}")
        # Exit function early due to missing configuration files
        return
        
    # Try block to safely parse and manipulate XML structure
    try:
        # Open the rules file to read target tags
        with open(tags_txt_path, 'r') as f:
            tags_to_comment = [line.strip() for line in f if line.strip()]
            
        tree = ET.parse(target_xml_path)
        root = tree.getroot()
        
        # Iterate over each target tag name fetched from the rules file
        for tag in tags_to_comment:
            # Search for matching elements within the entire XML tree
            for elem in root.iter(tag):
                children = list(elem)
                
                # Check if the matched element has any child nodes to comment out
                if children:
                    comment_text = "\n"
                    
                    # Iterate over all child elements to serialize them and remove from DOM
                    for child in children:
                        comment_text += ET.tostring(child, encoding='unicode')
                        elem.remove(child)
                        
                    comment_text += "    "
                    elem.append(ET.Comment(comment_text))
                    
        # Write the modified XML tree back to the original file
        tree.write(target_xml_path, encoding='utf-8', xml_declaration=True)
        log_info(f"Successfully patched {target_xml_path}")
        
    # Catch any exceptions raised during XML processing
    except Exception as e:
        log_error(f"Failed to process XML: {e}")
        
    # Return control to caller
    return

def main():
    """
    /*
     * @brief The main execution flow orchestrating the copy and patch processes.
     * @return None
     */
    """
    log_info("Starting the setup and patch process...")
    
    log_info("Step 1: Copying segger_rtt_quackquack_debug.h...")
    copy_debug_header(FOLDER_PATH_QUACKQUACK_DEBUG_INPUT, FOLDER_PATH_QUACKQUACK_DEBUG_OUTPUT)
    
    log_info("Step 2: Patching XML file...")
    patch_xml_config(XML_PATH_COMMON, COMMENT_XML_TXT)
    
    log_info("Step 3: Patching YAML config file...")
    patch_yaml_config(YML_PATH_TOOLS_CFG, REPLACE_YML_TXT)
    
    log_info("All operations completed!")
    
    # Return control to system
    return

# Check if the script is being executed directly
if __name__ == "__main__":
    main()
