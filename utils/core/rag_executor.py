import asyncio
import concurrent.futures
import contextvars
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

def _in_context(fn, args, kwargs):
    """The call, carrying the caller's context variables (the channel) into the worker thread."""
    ctx = contextvars.copy_context()
    return lambda: ctx.run(fn, *args, **kwargs)


async def _await_executor_and_drain(future):
    """Keep ownership of a synchronous worker until it has actually stopped.

    Cancelling a task awaiting run_in_executor() otherwise cancels only the
    asyncio wrapper, not a callable already running in a thread. Shield the
    worker future, retain the caller's semaphore while it drains, and then
    propagate cancellation. Retrieve any worker exception during that drain.
    """
    cancelled = False
    while not future.done():
        try:
            await asyncio.shield(future)
        except asyncio.CancelledError:
            cancelled = True
        except Exception:
            if not cancelled:
                raise
            break

    if cancelled:
        try:
            future.result()
        except BaseException:
            # Cancellation remains the caller-visible result; retrieving the
            # worker outcome prevents an unobserved-future exception.
            pass
        raise asyncio.CancelledError

    return future.result()


async def run_in_default_executor_and_drain(fn, *args, **kwargs):
    """Run a sync worker in asyncio's default pool without detaching it.

    Cancelling an asyncio.to_thread() awaiter does not stop a running thread.
    Keep the owner coroutine alive until that worker has actually finished so
    task-registry shutdown cannot mistake a live writer for drained work.
    """
    worker = asyncio.create_task(asyncio.to_thread(fn, *args, **kwargs))
    return await _await_executor_and_drain(worker)


async def run_rag(fn, *args, **kwargs):
    """
    Run write-heavy RAG operations (indexing, memory writes).
    Uses indexing_semaphore — may block if 2 indexing ops are already in flight.
    """
    async with indexing_semaphore:
        if inspect.iscoroutinefunction(fn):
            return await fn(*args, **kwargs)
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(rag_executor, _in_context(fn, args, kwargs))
        return await _await_executor_and_drain(future)

async def run_rag_retrieval(fn, *args, **kwargs):
    """
    Run read-only RAG retrieval operations.
    Uses retrieval_semaphore — never blocked by background indexing.
    """
    async with retrieval_semaphore:
        if inspect.iscoroutinefunction(fn):
            return await fn(*args, **kwargs)
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(rag_executor, _in_context(fn, args, kwargs))
        return await _await_executor_and_drain(future)

def shutdown_rag_executor():
    """Shutdown the thread pool executor gracefully."""
    rag_executor.shutdown(wait=True)

async def shutdown_rag_executor_async():
    """Drain and close the RAG pool without blocking the event loop."""
    await asyncio.to_thread(shutdown_rag_executor,)


