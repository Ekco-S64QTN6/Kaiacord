import sys
import logging
import os
import time

# Ensure we can import from project root
sys.path.append(os.getcwd())

from utils.infrastructure.logging.unified_logging import replace_all_logging, logger

def test_log_consolidation():
    # Make sure we start fresh
    log_file = "logs/kaiacord.log"
    if os.path.exists(log_file):
        try:
            os.remove(log_file)
        except Exception:
            pass
        
    # We use __stdout__ here because replace_all_logging will hijack sys.stdout
    sys.__stdout__.write("--- STARTING LOG CONSOLIDATION TEST ---\n")
    
    # Initialize unified logging
    replace_all_logging()
    
    # 1. Test standard print
    print("TEST: This is a standard print message")
    
    # 2. Test Success print
    print("✅ TEST: This is a success message")
    
    # 3. Test multi-timestamp cleanup (legacy issue)
    print("12:00:00 | 12:00:00 | TEST: Double timestamp message")
    
    # 4. Test sys.stdout.write (NEW)
    sys.stdout.write("TEST: This is from sys.stdout.write\n")
    
    # 5. Test sys.stderr.write (NEW)
    sys.stderr.write("TEST: This is an error from sys.stderr.write\n")
    
    # 6. Test standard logging
    logging.info("TEST: This is from logging.info")
    logging.error("TEST: This is from logging.error")
    
    # 7. Test large library output (simulated)
    sys.stdout.write("Model loading Progress: [==========] 100%\n")
    
    # Give it a tiny bit of time to flush if needed
    time.sleep(0.1)
    
    # Verify file content
    if not os.path.exists(log_file):
        sys.__stdout__.write("FAIL: logs/kaiacord.log was not created!\n")
        return
        
    with open(log_file, "r") as f:
        content = f.read()
        
    sys.__stdout__.write("\n--- CAPTURED LOG CONTENT ---\n")
    sys.__stdout__.write(content)
    sys.__stdout__.write("--- END OF CAPTURED LOG ---\n")
    
    required_strings = [
        "INFO: TEST: This is a standard print message",
        "SUCCESS: TEST: This is a success message",
        "INFO: TEST: Double timestamp message",
        "INFO: TEST: This is from sys.stdout.write",
        "ERROR: TEST: This is an error from sys.stderr.write",
        "INFO: TEST: This is from logging.info",
        "ERROR: TEST: This is from logging.error",
        "INFO: Model loading Progress: [==========] 100%"
    ]
    
    all_passed = True
    for s in required_strings:
        if s not in content:
            sys.__stdout__.write(f"FAIL: Expected string '{s}' not found in log file\n")
            all_passed = False
            
    if all_passed:
        sys.__stdout__.write("\nSUCCESS: All logging sources consolidated correctly!\n")
    else:
        sys.__stdout__.write("\nFAILURE: Some logging sources were missed.\n")

if __name__ == "__main__":
    test_log_consolidation()
