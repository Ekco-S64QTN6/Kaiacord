
import ast
import os
import sys

def check_file(filepath):
    print(f"Checking {filepath}...", end="")
    try:
        with open(filepath, 'r') as f:
            source = f.read()
        ast.parse(source)
        print(" ✅ Syntax OK")
        return True
    except SyntaxError as e:
        print(f" ❌ Syntax Error: {e}")
        return False
    except Exception as e:
        print(f" ❌ Error: {e}")
        return False

files_to_check = [
    "Kaiacord.py",
    "utils/core/kaia_intelligence.py",
    "utils/core/kaia_rag.py",
    "utils/core/message_processor.py",
    "utils/infrastructure/system/dashboard_manager.py",
    "utils/social/kaia_social_responder.py",
    "utils/infrastructure/circuit_breaker.py",
    "utils/infrastructure/gpu/gpu_manager.py"
]

success = True
for f in files_to_check:
    if not check_file(f):
        success = False

if success:
    print("\n🎉 All critical files pass static syntax analysis.")
    sys.exit(0)
else:
    print("\nBOOM. Syntax errors found.")
    sys.exit(1)
