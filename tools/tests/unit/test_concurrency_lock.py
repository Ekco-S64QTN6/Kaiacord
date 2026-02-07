import asyncio
import pytest
from unittest.mock import AsyncMock, patch

class MockOllamaClient:
    def __init__(self):
        self.call_count = 0
        self.concurrent_calls = 0
        self.max_concurrent_calls = 0
        self.lock = asyncio.Lock()

    async def chat(self, *args, **kwargs):
        async with self.lock:
            self.concurrent_calls += 1
            self.max_concurrent_calls = max(self.max_concurrent_calls, self.concurrent_calls)
        
        # Simulate LLM work
        await asyncio.sleep(0.1)
        
        async with self.lock:
            self.concurrent_calls -= 1
            self.call_count += 1
        
        return {'message': {'content': 'mock response'}}

@pytest.mark.asyncio
async def test_ollama_semaphore_serialization():
    # Setup
    mock_client = MockOllamaClient()
    semaphore = asyncio.Semaphore(1)
    
    async def call_with_semaphore():
        async with semaphore:
            return await mock_client.chat()

    # Trigger multiple concurrent calls
    tasks = [call_with_semaphore() for _ in range(5)]
    await asyncio.gather(*tasks)

    # Assertions
    assert mock_client.call_count == 5
    assert mock_client.max_concurrent_calls == 1, f"Expected 1 concurrent call, got {mock_client.max_concurrent_calls}"
    print(f"\n✅ Concurrency test passed: max_concurrent_calls={mock_client.max_concurrent_calls}")

if __name__ == "__main__":
    asyncio.run(test_ollama_semaphore_serialization())
