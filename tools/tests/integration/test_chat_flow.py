import asyncio
import os
import sys
import pytest
import ollama
import time

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

# Set PyTorch CUDA allocator to use expandable segments to reduce fragmentation
os.environ["PYTORCH_ALLOC_CONF"] = "expandable_segments:True,max_split_size_mb:512"

# Legacy import - generate_image implementation is currently missing from utils
# from utils.kaia_image import generate_image
async def generate_image(prompt):
    print(f"MOCK: Generating image for: {prompt}")
    return "mock_image.png"


@pytest.mark.asyncio
async def test_gpu():

    MODEL = "qwen3.5:9b"
    print(f"\n--- Testing GPU usage for model: {MODEL} ---")
    client = ollama.AsyncClient()
    
    start_time = time.time()
    try:
        print("Sending request with num_gpu=99...")
        response = await client.chat(
            model=MODEL,
            messages=[{'role': 'user', 'content': 'Why is the sky blue? Answer in 1 sentence.'}],
            options={
                "num_gpu": 99,
                "num_thread": 8,
                "num_predict": 100
            }
        )
        end_time = time.time()
        
        content = response['message']['content']
        print(f"Response: {content}")
        print(f"Time: {end_time - start_time:.2f}s")
        
        # Check metrics if available
        if 'eval_count' in response and 'eval_duration' in response:
            tokens = response['eval_count']
            duration_ns = response['eval_duration']
            duration_s = duration_ns / 1e9
            tps = tokens / duration_s if duration_s > 0 else 0
            print(f"Speed: {tps:.2f} tokens/sec")
            
            if tps < 5:
                print("WARNING: Speed is very low (< 5 tps). Likely using CPU.")
            else:
                print("✓ Speed looks good. Likely using GPU.")
        else:
            print("Metrics not available in response.")
            
    except Exception as e:
        print(f"Error: {e}")

@pytest.mark.asyncio
async def test_image_generation():

    print("\n--- Testing Image Generation ---")
    prompt = "a futuristic cyberpunk city with neon lights and rain"
    print(f"Prompt: {prompt}")
    try:
        image_path = await generate_image(prompt)
        print(f"✓ Success! Image saved to: {image_path}")
        if os.path.exists(image_path):
            size = os.path.getsize(image_path)
            print(f"File size: {size} bytes")
            # Cleanup
            os.remove(image_path)
            print("Cleaned up temp file.")
    except Exception as e:
        print(f"Error: {e}")

@pytest.mark.asyncio
async def test_ollama_limit():

    print("\n--- Testing Ollama Context Limit ---")
    client = ollama.AsyncClient()
    try:
        response = await client.chat(
            model="qwen3.5:9b",
            messages=[{"role": "user", "content": "Tell me a very long story about a dragon."}],
            options={"num_predict": 512} # Reduced for test speed
        )
        content = response['message']['content']
        print(f"Response length: {len(content)} characters")
        if len(content) > 100:
            print("✓ Success: Generated response.")
        else:
            print("! Warning: Response was short.")
    except Exception as e:
        print(f"Error: {e}")

async def main():
    print("=== Running System Capability Tests ===")
    await test_gpu()
    await test_ollama_limit()
    # Uncomment to test image generation (heavy)
    # await test_image_generation()
    print("\n=== All System Tests Completed ===")

if __name__ == "__main__":
    asyncio.run(main())
