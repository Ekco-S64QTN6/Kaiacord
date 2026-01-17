import asyncio
import os
import torch
from kaia_image import generate_image
from dotenv import load_dotenv

load_dotenv()

async def main():
    print("Starting generation test...")
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        print("Cleared CUDA cache.")
    try:
        # Simple prompt
        path = await generate_image("a cyberpunk cat in a neon city")
        print(f"Success! Image saved to: {path}")
        
        # Verify file exists
        if os.path.exists(path):
            print(f"File exists. Size: {os.path.getsize(path)} bytes")
            # Cleanup
            os.remove(path)
            print("Cleanup successful.")
        else:
            print("Error: File was not created.")
            
    except Exception as e:
        print(f"Generation failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
