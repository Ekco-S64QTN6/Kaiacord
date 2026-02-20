import sys
import os
from datetime import datetime

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.infrastructure.logging.unified_logging import logger, log_ollama_interaction

def test_logging():
    print("Testing unified logging...")
    logger.log("Test message for kaiacord.log", "INFO")
    logger.log("Success message", "SUCCESS")
    logger.log("Warning message", "WARNING")
    logger.log("Error message", "ERROR")
    
    print("Testing ollama interaction logging...")
    log_ollama_interaction("Test prompt", "Test response")
    
    # Check if files exist
    if os.path.exists("logs/kaiacord.log"):
        print("✅ logs/kaiacord.log created")
        with open("logs/kaiacord.log", "r") as f:
            print(f"   Content: {f.read().strip()}")
    else:
        print("❌ logs/kaiacord.log NOT created")
        
    if os.path.exists("logs/ollama_client.log"):
        print("✅ logs/ollama_client.log created")
        with open("logs/ollama_client.log", "r") as f:
            print(f"   Content: {f.read().strip()}")
    else:
        print("❌ logs/ollama_client.log NOT created")

if __name__ == "__main__":
    test_logging()
