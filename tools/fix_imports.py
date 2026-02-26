import sys

# ARCHIVED — Feb 26, 2026
# This tool was used during the mass migration of core modules to utils/.
# It is now legacy and should not be used as it may break current sub-package structure.
print("ERROR: tools/fix_imports.py is ARCHIVED. Use manual imports or a modern refactoring tool.")
sys.exit(1)

import os
import re
from pathlib import Path

# Paths
KAIACORD_ROOT = Path(__file__).parent.parent
UTILS_DIR = KAIACORD_ROOT / "utils"
TESTS_DIR = KAIACORD_ROOT / "tools" / "tests"

def build_module_map():
    module_map = {}
    
    for root, dirs, files in os.walk(UTILS_DIR):
        if "__pycache__" in root:
            continue
            
        for file in files:
            if file.endswith(".py") and file != "__init__.py":
                module_name = file[:-3]
                
                # Get relative path from utils directory
                rel_path = os.path.relpath(os.path.join(root, file), UTILS_DIR)
                
                # Convert path to module dotted notation (e.g. core.kaia_rag)
                dotted_path = rel_path[:-3].replace(os.sep, '.')
                
                module_map[module_name] = f"utils.{dotted_path}"
                
    return module_map

def fix_imports():
    module_map = build_module_map()
    print(f"Built mapping for {len(module_map)} modules.")
    
    files_modified = 0
    
    for root, dirs, files in os.walk(TESTS_DIR):
        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    
                original = content
                
                # Pattern 1: from utils.X import Y -> from mapped.X import Y
                content = re.sub(
                    r'from utils\.([a-zA-Z0-9_]+) import',
                    lambda m: f"from {module_map.get(m.group(1), 'utils.' + m.group(1))} import",
                    content
                )
                
                # Pattern 2: import utils.X -> import mapped.X
                content = re.sub(
                    r'import utils\.([a-zA-Z0-9_]+)(\s|$)',
                    lambda m: f"import {module_map.get(m.group(1), 'utils.' + m.group(1))}{m.group(2)}",
                    content
                )
                
                # Pattern 3: from utils import X -> from mapped.X import ... (this is tricky, so we just rewrite it as import or adjust)
                # If someone did `from utils import yaml_config`, map it to `from utils.infrastructure.system import yaml_config`
                def handle_from_utils(m):
                    mod = m.group(1)
                    if mod in module_map:
                        full_mapped = module_map[mod]
                        parent_module = full_mapped.rsplit('.', 1)[0]
                        return f"from {parent_module} import {mod}"
                    return m.group(0)
                    
                content = re.sub(
                    r'from utils import ([a-zA-Z0-9_]+)',
                    handle_from_utils,
                    content
                )
                
                # Update references in code: utils.X.method() -> module_map[X].method()
                # We skip this for now as most tests use `from X import Y`, but we'll catch basic `utils.X`
                for mod_name, full_path in module_map.items():
                    # Only if it's safe (starts with boundary, ends with dot)
                    content = re.sub(rf'\butils\.{mod_name}\b', full_path, content)
                
                if original != content:
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(content)
                    files_modified += 1
                    print(f"Modified: {file_path}")
                    
    print(f"Finished. Modified {files_modified} test files.")

if __name__ == "__main__":
    fix_imports()
