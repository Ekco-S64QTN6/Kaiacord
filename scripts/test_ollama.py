import asyncio
from ollama import Client
import time

async def test_llm():
    client = Client(host='http://localhost:11434')
    start_time = time.time()
    print("Sending test request...")
    response = await asyncio.to_thread(
        client.chat,
        model='gemma3:12b',
        messages=[{"role": "user", "content": "Say hello world in 10 words."}],
        options={'num_ctx': 4096}
    )
    duration = time.time() - start_time
    print(f"Response: {response['message']['content']}")
    print(f"Time taken: {duration:.2f}s")

if __name__ == "__main__":
    asyncio.run(test_llm())
