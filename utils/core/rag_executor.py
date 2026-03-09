import asyncio
import concurrent.futures
import inspect

# Two separate semaphores keep indexing and retrieval independent.
#
# indexing_semaphore — held for the entire duration of write-heavy ops
#   (refresh_knowledge_base, add_memory, log_user_interaction).
#   Capped at 2 to avoid simultaneous embedding storms during boot.
#
# retrieval_semaphore — used ONLY for read-only retrieve() calls from
#   message processing.  Higher cap, and crucially NEVER acquired by
#   background indexing, so a long refresh can never starve user messages.
indexing_semaphore = asyncio.Semaphore(2)
retrieval_semaphore = asyncio.Semaphore(4)


# RAG Executor Helper
rag_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix='rag_worker')

async def run_rag(fn, *args, **kwargs):
    """
    Run write-heavy RAG operations (indexing, memory writes).
    Uses indexing_semaphore — may block if 2 indexing ops are already in flight.
    """
    async with indexing_semaphore:
        if inspect.iscoroutinefunction(fn):
            return await fn(*args, **kwargs)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(rag_executor, lambda: fn(*args, **kwargs))

async def run_rag_retrieval(fn, *args, **kwargs):
    """
    Run read-only RAG retrieval operations.
    Uses retrieval_semaphore — never blocked by background indexing.
    """
    async with retrieval_semaphore:
        if inspect.iscoroutinefunction(fn):
            return await fn(*args, **kwargs)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(rag_executor, lambda: fn(*args, **kwargs))

def shutdown_rag_executor():
    """Shutdown the thread pool executor gracefully."""
    rag_executor.shutdown(wait=True)
