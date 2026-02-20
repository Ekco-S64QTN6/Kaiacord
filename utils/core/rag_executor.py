import asyncio
import concurrent.futures
import inspect

# Concurrency limit for embedding-heavy RAG operations
embedding_semaphore = asyncio.Semaphore(2)

# RAG Executor Helper
rag_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix='rag_worker')

async def run_rag(fn, *args, **kwargs):
    """
    Utility to run RAG functions with a shared semaphore and thread executor.
    Resolves circular dependency between Kaiacord.py and background_tasks.py.
    """
    async with embedding_semaphore:
        if inspect.iscoroutinefunction(fn):
            return await fn(*args, **kwargs)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(rag_executor, lambda: fn(*args, **kwargs))

def shutdown_rag_executor():
    """Shutdown the thread pool executor gracefully."""
    rag_executor.shutdown(wait=True)
