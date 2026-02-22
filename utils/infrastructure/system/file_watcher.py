import asyncio
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from utils.infrastructure.logging.kaia_logger import log_success, log_action, log_info, log_error, log_debug

class KnowledgeBaseWatcher(FileSystemEventHandler):
    def __init__(self, rag, loop, cache_invalidator=None, task_registry=None):
        self.rag = rag
        self.loop = loop
        self.cache_invalidator = cache_invalidator
        self.task_registry = task_registry
        self.queue = asyncio.Queue()
        self.processing_task = None
        
    def on_modified(self, event):
        if event.is_directory: return
        # Add to queue if the loop is still running
        if self.loop and not self.loop.is_closed():
            asyncio.run_coroutine_threadsafe(self.queue.put(event.src_path), self.loop)

    def stop(self):
        """Signal the watcher to stop processing."""
        if self.processing_task:
            self.processing_task.cancel()

    async def start_processing(self):
        """Dedicated task to process the file change queue."""
        from utils.infrastructure.system.shutdown_fixed import shutdown_manager
        from utils.core.rag_executor import run_rag
        log_success("Watchdog queue processor started.")
        try:
            while True:
                if self.loop.is_closed() or shutdown_manager.shutting_down:
                    break
                    
                try:
                    path = await self.queue.get()
                except RuntimeError: # Loop closed
                    break
                except asyncio.CancelledError:
                    raise

                if shutdown_manager.shutting_down:
                    break
                    
                try:
                    # Debounce: wait a bit for more changes
                    await asyncio.sleep(2)
                    # Clear any other pending changes for the same path
                    while not self.queue.empty():
                        try:
                            self.queue.get_nowait()
                            self.queue.task_done()
                        except (asyncio.QueueEmpty, RuntimeError): break
                    
                    if shutdown_manager.shutting_down:
                        break

                    log_action(f"Processing queued change: {path}")
                    # Invalidate cache for this file
                    if self.cache_invalidator:
                        self.cache_invalidator.invalidate_for_file(path)
                    await run_rag(self.rag.refresh_knowledge_base)
                    log_debug("Incremental RAG refresh complete.")
                except Exception as e:
                    log_error(f"Watchdog processing failed: {e}")
                finally:
                    try:
                        self.queue.task_done()
                    except (ValueError, RuntimeError): pass
        except asyncio.CancelledError:
            log_info("Watchdog queue processor shutting down.")

def start_watcher(rag, loop, cache_invalidator=None, task_registry=None):
    """Start the file system watcher for the knowledge base"""
    observer = Observer()
    event_handler = KnowledgeBaseWatcher(rag, loop, cache_invalidator, task_registry)
    observer.schedule(event_handler, rag.knowledge_base_dir, recursive=True)
    observer.start()
    # Start the queue processor
    event_handler.processing_task = asyncio.create_task(event_handler.start_processing())
    if task_registry:
        task_registry.register("knowledge_base_watcher", event_handler.processing_task)
    log_success(f"Knowledge base watcher started on {rag.knowledge_base_dir}")
    return observer
