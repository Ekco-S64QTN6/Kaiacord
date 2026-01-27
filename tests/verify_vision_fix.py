import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(os.getcwd())

from utils.kaia_vision import analyze_image, VISION_MODEL
from utils.kaia_logger import log_info, log_success, log_error

async def verify_fix():
    log_info(f"Verifying vision fix for model: {VISION_MODEL}")
    
    # Create a dummy image for testing if none exists
    dummy_image = "/tmp/test_vision.png"
    if not os.path.exists(dummy_image):
        # Create a tiny 1x1 pixel image
        with open(dummy_image, "wb") as f:
            f.write(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82')
    
    try:
        log_info("Attempting to analyze dummy image...")
        analysis = await analyze_image(dummy_image, "What is in this image?")
        log_success(f"Vision analysis successful! Response: {analysis[:50]}...")
        return True
    except Exception as e:
        log_error(f"Vision analysis failed: {e}")
        return False
    finally:
        if os.path.exists(dummy_image):
            os.remove(dummy_image)

if __name__ == "__main__":
    success = asyncio.run(verify_fix())
    sys.exit(0 if success else 1)
