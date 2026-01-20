import sys
import os
import torch
import gc

# Add the current directory to sys.path to import our modules
sys.path.append(os.path.abspath("."))

from kaia_image import unload_image_model, _pipe

def test_unload():
    print("Testing unload_image_model...")
    
    # Mock a pipeline object
    class MockPipe:
        def to(self, device):
            print(f"MockPipe: Moving to {device}")
    
    import kaia_image
    kaia_image._pipe = MockPipe()
    
    print(f"Before unload: kaia_image._pipe is {kaia_image._pipe}")
    unload_image_model()
    print(f"After unload: kaia_image._pipe is {kaia_image._pipe}")
    
    if kaia_image._pipe is None:
        print("✓ Success: Pipeline was cleared.")
    else:
        print("✗ Failure: Pipeline was not cleared.")
        sys.exit(1)

if __name__ == "__main__":
    test_unload()
