import asyncio
import os
import sys

# Add parent directory to path to import kaia modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kaia_image import generate_image, generation_lock

async def simulate_chat():
    await asyncio.sleep(2) # Wait for generation to start
    print("Simulating chat message during generation...")
    if generation_lock.locked():
        print("✓ SUCCESS: Generation lock is ACTIVE. Chat would be ignored.")
    else:
        print("✗ FAILURE: Generation lock is NOT active.")

async def main():
    prompt = "a small red cube"
    print(f"Starting test generation with prompt: {prompt}")
    
    # Run generation and chat simulation concurrently
    try:
        # We wrap generate_image in a task so we can check the lock
        gen_task = asyncio.create_task(generate_image(prompt))
        chat_task = asyncio.create_task(simulate_chat())
        
        image_path = await gen_task
        await chat_task
        
        print(f"Generation finished. Image saved to: {image_path}")
        if os.path.exists(image_path):
            os.remove(image_path)
            print("Cleaned up.")
            
    except Exception as e:
        print(f"Test failed with error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
