import re
import os

files_to_fix = [
    "utils/infrastructure/gpu/gpu_manager.py",
    "utils/infrastructure/gpu/clear_gpu_memory.py",
    "utils/infrastructure/gpu/nuclear_unload.py"
]

for file in files_to_fix:
    path = os.path.join("/home/ekco/github/Kaiacord", file)
    if not os.path.exists(path):
        continue
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Simple regex to replace print( with log_info(
    # Note: this assumes no nested prints or multiline tricky business, which fits the simple prints found.
    new_content = re.sub(r'\bprint\(', 'log_info(', content)
    
    # If file was modified, ensure import exists
    if new_content != content:
        if "from utils.infrastructure.logging.kaia_logger import" not in new_content:
            new_content = "from utils.infrastructure.logging.kaia_logger import log_info, log_error\n" + new_content
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"Fixed {file}")

