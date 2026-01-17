import asyncio
import os
import torch
from kaia_image import generate_image
from dotenv import load_dotenv

load_dotenv()

# Set allocator config to reduce fragmentation
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

async def main():
    print("Starting OOM verification...")
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        print(f"Initial Memory: {torch.cuda.memory_allocated()/1024**3:.2f} GB allocated, {torch.cuda.memory_reserved()/1024**3:.2f} GB reserved")
    
    try:
        path = await generate_image("a cyberpunk cat")
        print(f"Success! Image saved to: {path}")
        
        if torch.cuda.is_available():
            print(f"Final Memory: {torch.cuda.memory_allocated()/1024**3:.2f} GB allocated, {torch.cuda.memory_reserved()/1024**3:.2f} GB reserved")
            
        if os.path.exists(path):
            os.remove(path)
            
    except Exception as e:
        print(f"Generation failed: {e}")
        if torch.cuda.is_available():
            print(f"Memory at failure: {torch.cuda.memory_allocated()/1024**3:.2f} GB allocated, {torch.cuda.memory_reserved()/1024**3:.2f} GB reserved")

if __name__ == "__main__":
    asyncio.run(main())
