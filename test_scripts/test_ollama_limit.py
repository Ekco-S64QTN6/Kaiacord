import asyncio
import ollama

async def test_ollama_limit():
    client = ollama.AsyncClient()
    print("Testing Ollama with num_predict=2048...")
    try:
        response = await client.chat(
            model="gemma3:12b",
            messages=[{"role": "user", "content": "Tell me a very long story about a dragon."}],
            options={
                "num_predict": 2048,
            }
        )
        content = response['message']['content']
        print(f"Response length: {len(content)} characters")
        print(f"Response preview: {content[:100]}...")
        if len(content) > 500:
            print("✓ Success: Generated a reasonably long response.")
        else:
            print("! Warning: Response was short, but the parameter was accepted.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_ollama_limit())
