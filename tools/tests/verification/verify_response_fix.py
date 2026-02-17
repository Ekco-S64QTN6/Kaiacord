
import sys
import os
sys.path.append('/home/ekco/github/Kaiacord')

from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager
from utils.infrastructure.system.yaml_config import config

def test_gpu_options():
    manager = OllamaGPUManager()
    options = manager.get_gpu_options(for_chat=True)
    print(f"Config max_response_tokens: {config.max_response_tokens}")
    print(f"Actual num_predict in options: {options.get('num_predict')}")
    
    if options.get('num_predict') == config.max_response_tokens:
        print("SUCCESS: Fix verified.")
    else:
        print("FAILURE: Fix not working correctly.")

if __name__ == "__main__":
    test_gpu_options()
