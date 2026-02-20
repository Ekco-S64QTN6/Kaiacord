import sys
import os
from datetime import datetime

sys.path.append(os.getcwd())
from utils.core.kaia_rag import KaiaRAG
from utils.infrastructure.logging.kaia_logger import log_info

def test():
    rag = KaiaRAG()
    user_id = 999
    user_name = "TestUser"
    message = "Testing the new markdown logging system."
    response = "Successfully logged in Markdown!"
    
    log_info("Testing log_user_interaction...")
    rag.log_user_interaction(user_id, user_name, message, response)
    
    # Check if .md file exists
    log_file = f"knowledge_base/user_logs/TestUser_999/interactions_{datetime.now().strftime('%Y%m%d')}.md"
    if os.path.exists(log_file):
        print(f"SUCCESS: {log_file} created.")
        with open(log_file, 'r') as f:
            print("Content:")
            print(f.read())
    else:
        print(f"FAILURE: {log_file} not found.")

if __name__ == "__main__":
    from datetime import datetime
    test()
