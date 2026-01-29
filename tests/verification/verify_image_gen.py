import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from utils.kaia_image import generate_image, unload_image_model
from utils.kaia_logger import log_info, log_success, log_error

async def verify_image_gen():
    log_info("Verifying image generation pipeline...")
    
    output_path = "/tmp/test_gen.png"
    prompt = "a small red square"
    
    try:
        log_info(f"Attempting to generate image with prompt: {prompt}")
        # Note: This might take a while if it needs to download/load the model
        # But it should use the CPU offloading fix internally
        success, result = await generate_image(prompt, output_path)
        
        if success:
            log_success(f"Image generation successful! Saved to: {result}")
            return True
        else:
            log_error(f"Image generation failed: {result}")
            return False
    except Exception as e:
        log_error(f"Error during image gen verification: {e}")
        return False
    finally:
        await unload_image_model()
        if os.path.exists(output_path):
            os.remove(output_path)

if __name__ == "__main__":
    # We use a timeout because Flux can be slow
    try:
        success = asyncio.run(asyncio.wait_for(verify_image_gen(), timeout=300))
        sys.exit(0 if success else 1)
    except asyncio.TimeoutError:
        log_error("Image generation timed out.")
        sys.exit(1)
