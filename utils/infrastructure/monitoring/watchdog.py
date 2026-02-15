import asyncio
import time
import threading
import sys
import traceback
from utils.infrastructure.logging.kaia_logger import log_warning, log_debug

class LoopWatchdog:
    """
    Monitors the event loop for stalls.
    Runs in a separate thread to ensure it can report stalls even when the loop is blocked.
    """
    def __init__(self, threshold_seconds=2.0, check_interval=1.0):
        self.threshold = threshold_seconds
        self.interval = check_interval
        self._last_tick = time.time()
        self._stop_event = threading.Event()
        self._monitor_thread = None
        self._loop = None

    async def _tick_task(self):
        """Task that runs in the event loop to update the heartbeat."""
        while not self._stop_event.is_set():
            self._last_tick = time.time()
            await asyncio.sleep(self.interval / 2)

    def _monitor(self):
        """Thread function that checks for stalls."""
        while not self._stop_event.is_set():
            time.sleep(self.interval)
            
            # Check if the last tick was too long ago
            stale_duration = time.time() - self._last_tick
            if stale_duration > self.threshold:
                # Loop is likely blocked!
                log_warning(f"EVENT LOOP STALL DETECTED: Loop has been unresponsive for {stale_duration:.2f}s")
                
                # Attempt to get the stack trace of the main thread
                # This only works if we know which thread the loop is in.
                # Usually it's the main thread.
                try:
                    # Log the stack frames of the loop thread
                    loop_tid = getattr(self, '_loop_thread_id', None)
                    for thread_id, stack in sys._current_frames().items():
                        if thread_id == loop_tid:
                            stack_str = "".join(traceback.format_stack(stack))
                            log_debug(f"Blocked loop thread stack trace:\n{stack_str}")
                            break
                    else:
                        # Fallback: if loop thread not found, log main thread as it might be blocking the process
                        for thread_id, stack in sys._current_frames().items():
                            t = threading._active.get(thread_id)
                            if t and (t.name == "MainThread" or thread_id == threading.main_thread().ident):
                                stack_str = "".join(traceback.format_stack(stack))
                                log_debug(f"Loop thread not found. Main thread stack trace:\n{stack_str}")
                                break
                except Exception as e:
                    log_debug(f"Failed to capture stack trace: {e}")

    def _record_loop_thread_id(self):
        """Record the thread ID of the event loop."""
        self._loop_thread_id = threading.get_ident()

    def start(self, loop=None):
        """Start the watchdog."""
        self._loop = loop or asyncio.get_event_loop()
        self._stop_event.clear()
        self._last_tick = time.time()
        
        # Capture the loop thread ID synchronously
        self._loop.call_soon_threadsafe(self._record_loop_thread_id)
        
        # Start the tick task in the loop
        asyncio.run_coroutine_threadsafe(self._tick_task(), self._loop)
        
        # Start the monitor thread
        self._monitor_thread = threading.Thread(target=self._monitor, daemon=True, name="LoopWatchdog")
        self._monitor_thread.start()
        log_debug(f"LoopWatchdog started (threshold={self.threshold}s)")

    def stop(self):
        """Stop the watchdog."""
        self._stop_event.set()
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2.0)

# Global instances per threshold
watchdog = LoopWatchdog(threshold_seconds=5.0) # 5s is safe for Discord heartbeats
