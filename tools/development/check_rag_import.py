import sys
import os
sys.path.append(os.getcwd())
try:
    from utils.core import kaia_rag
    print("Import successful")
except Exception as e:
    print(f"Import failed: {e}")
    sys.exit(1)
