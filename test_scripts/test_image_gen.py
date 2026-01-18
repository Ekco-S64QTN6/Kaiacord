import asyncio
import os

# Set PyTorch CUDA allocator to use expandable segments to reduce fragmentation
os.environ["PYTORCH_ALLOC_CONF"] = "expandable_segments:True,max_split_size_mb:512"

from kaia_image import generate_image

async def main():
    prompt = "a futuristic cyberpunk city with neon lights and rain"
    print(f"Testing image generation with prompt: {prompt}")
    try:
        image_path = await generate_image(prompt)
        print(f"Success! Image saved to: {image_path}")
        if os.path.exists(image_path):
            # We'll keep it for a moment to verify, then delete
            print("Verifying file exists...")
            size = os.path.getsize(image_path)
            print(f"File size: {size} bytes")
            # os.remove(image_path)
            # print("Cleaned up.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
