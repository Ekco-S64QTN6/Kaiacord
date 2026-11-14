import os
import signal
import sys
import asyncio
import inspect
import psutil
import threading
import time
import traceback
import multiprocessing

from utils.infrastructure.logging.kaia_logger import (
    log_info, log_success, log_warning, log_error, log_action, log_separator, log_debug, log_ready, log_critical
)
from utils.infrastructure.system.shutdown_fixed import shutdown_manager
from utils.infrastructure.monitoring.stats_helpers import set_stats_poller
from utils.infrastructure.monitoring.btop_dashboard_v2 import BtopDashboardV2
from utils.infrastructure.monitoring.async_task_registry import task_registry

# --- MULTIPROCESSING TARGETS (Must be at module level for pickling) ---

# How long the bot's own shutdown may take once it has been asked to stop. It
# saves her state and the RAG indices; ending the process under it loses both.
BOT_SHUTDOWN_DEADLINE_S = 40.0
# A new instance waits this long for the one it replaces, so longer than the above.
OTHER_INSTANCE_GRACE_S = 45.0
# Tasks still running when the bot's loop closes get this long to take a cancel.
LOOP_DRAIN_S = 5.0


def wait_for_bot_shutdown(bot_thread, dashboard_process, logger,
                          deadline_s: float = BOT_SHUTDOWN_DEADLINE_S) -> bool:
    """Wait for the bot thread to finish shutting down; True when it did, cleanly.

    The screen closing is not the bot having stopped: the dashboard exits the
    moment it is asked to, and the bot is then still saving. Only the bot thread
    ending says its shutdown ran, and only `_shutdown_complete` says it ran whole.
    """
    if dashboard_process is not None:
        dashboard_process.join(timeout=2.0)
    # Nothing reads the log queue once the screen is gone; the rest goes to the console.
    logger.set_dashboard_mode(False)
    bot_thread.join(timeout=deadline_s)
    if bot_thread.is_alive():
        log_error(f"Shutdown incomplete: the bot was still shutting down after {deadline_s:.0f}s; "
                  "exiting anyway. State or index changes from this run may not be saved.")
        return False
    if not shutdown_manager._shutdown_complete.is_set():
        log_error("Shutdown incomplete: the bot stopped without finishing its teardown.")
        return False
    return True


def _run_dashboard_process(shared_stats, log_queue, stop_event, error_queue):
    """Entry point for the isolated dashboard process."""
    try:
        dashboard = BtopDashboardV2(
            shared_stats=shared_stats,
            log_queue=log_queue,
            stop_event=stop_event,
        )
        dashboard.run()
    except Exception as e:
        err_info = (str(e), traceback.format_exc())
        try:
            error_queue.put(err_info)
        except Exception:
            print(f"Isolated Dashboard Fatal Error (Failed to queue): {e}")
            traceback.print_exc()
        raise

def _count_recent_hallucinations(log_path: str, seconds: int = 86400) -> int:
    """Count entries in hallucination_log.jsonl from the last N seconds."""
    import json
    import time
    count = 0
    now = time.time()
    if not os.path.exists(log_path):
        return 0
    try:
        with open(log_path, 'r') as f:
            for line in f:
                if not line.strip(): continue
                try:
                    data = json.loads(line)
                    ts = data.get('timestamp')
                    if ts and (now - ts) < seconds:
                        count += 1
                except Exception:
                    continue
    except Exception:
        pass
    return count

async def _stats_sync_task(shared_stats, stats_tracker, stats_poller, stop_event, ctx=None):
    """Sync bot stats to shared memory."""
    hallucination_log = "memory/hallucination_log.jsonl"
    while not stop_event.is_set():
        try:
            s = stats_tracker.get_stats()
            p = stats_poller.get_stats()
            
            # Resolve rag and bot_state dynamically from ctx
            rag = getattr(ctx, 'rag', None) if ctx else None
            bot_state = getattr(ctx, 'bot_state', None) if ctx else None
            
            # Pull RAG metrics
            rag_confidence = 0.0
            rag_nodes = 0
            coherence_ema = 0.85
            rag_stale = True  # Default to stale until proven fresh
            if rag:
                rag_confidence = getattr(rag, '_last_retrieval_confidence', 0.0)
                rag_nodes = getattr(rag, '_last_retrieval_node_count', 0)
                last_query_time = getattr(rag, '_last_retrieval_time', 0.0)
                if last_query_time and (time.time() - last_query_time) < 900:  # 15 min
                    rag_stale = False
            if bot_state:
                coherence_ema = getattr(bot_state, 'kaia_coherence', 0.85)

            # Daily hallucination count
            h_count = await asyncio.to_thread(_count_recent_hallucinations, hallucination_log)

            # We use update for bulk modification
            _payload = ({
                'messages': s.get('messages', 0),
                'avg_response_time': s.get('avg_response_time', 0.0),
                'queue_size': s.get('queue_size', 0),
                'uptime_minutes': p.get('uptime_minutes', 0.0) or s.get('uptime_minutes', 0.0),
                'active_users_display': s.get('active_users_display', "0 (idle)"),
                'ollama_status': p.get('ollama_status', '🔴 OFFLINE'),
                'active_model': p.get('active_model', 'None'),
                'ollama_models': p.get('ollama_models', []),
                'rag_size': p.get('rag_size', '0 MB'),
                'kb_size_mb': p.get('kb_size_mb', 0.0),
                'log_size_mb': p.get('log_size_mb', 0.0),
                'indexed_files': p.get('indexed_files', 0),
                'dreams_count': p.get('dreams_count', 0),
                'gpu_util': p.get('gpu_util', 0.0),
                'gpu_memory': p.get('gpu_memory', 'N/A'),
                
                # Cognitive & Forum Stats
                'beliefs_count': p.get('beliefs_count', 0),
                'anchors_count': p.get('anchors_count', 0),
                'relationship_count': p.get('relationship_count', 0),
                'forum_drafts': s.get('forum_drafts', 0),
                'forum_approved': s.get('forum_approved', 0),
                'forum_rejected': s.get('forum_rejected', 0),
                
                # RAG Health Panel Data
                'rag_confidence': rag_confidence,
                'rag_nodes': rag_nodes,
                'coherence_ema': coherence_ema,
                'hallucination_count': h_count,
                'rag_stale': rag_stale,
            })
            # A call into the manager process: a stalled manager must not stall the loop.
            await asyncio.to_thread(shared_stats.update, _payload)
        except Exception as e:
            try:
                from utils.infrastructure.logging.kaia_logger import log_debug
                log_debug(f"Stats sync task error: {e}")
            except Exception:
                pass
        await asyncio.sleep(1.0)

def _run_bot_in_thread(shared_stats, stats_tracker, stats_poller, stop_event,
                       initialize_logic_layer, run_bot_async, ctx=None):
    """Isolated bot thread runner."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        # Start stats sync task
        sync_task = loop.create_task(_stats_sync_task(shared_stats, stats_tracker, stats_poller, stop_event, ctx))
        task_registry.register("ui_stats_sync", sync_task)
        
        # Initialize logic layer (e.g., config, state)
        if inspect.iscoroutinefunction(initialize_logic_layer):
            loop.run_until_complete(initialize_logic_layer())
        else:
            initialize_logic_layer()
            
        # Run main bot loop
        loop.run_until_complete(run_bot_async(stats_poller, stop_event))
    finally:
        # Graceful loop drainage
        try:
            pending = asyncio.all_tasks(loop)
            if pending:
                loop.run_until_complete(asyncio.sleep(0.1))
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    if not task.done(): task.cancel()
                # A task may swallow the cancel; it does not get to hold the process open.
                loop.run_until_complete(asyncio.wait(pending, timeout=LOOP_DRAIN_S))
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception: pass
        
        if not loop.is_closed(): loop.close()

class DashboardManager:
    """Manages the lifecycle of the bot's terminal dashboard and run modes."""
    
    def __init__(self, ctx, bot, config, bot_state, stats_tracker, stats_poller, 
                 logger):
        self.ctx = ctx
        self.bot = bot
        self.config = config
        self.bot_state = bot_state
        self.stats_tracker = stats_tracker
        self.stats_poller = stats_poller
        self.logger = logger
        
        # Internal state
        self.dashboard = None
        self.stop_event = threading.Event()
        self.cleanup_complete_event = threading.Event()
        self.bot_thread = None

    def cleanup_on_startup(self):
        """Kill-other instances of Kaiacord and clear GPU memory."""
        current_pid = os.getpid()
        log_action(f"Startup cleanup (PID: {current_pid})...")
        survivors = []

        for proc in psutil.process_iter(['pid', 'ppid', 'name', 'cmdline', 'exe']):
            try:
                ppid = proc.info.get('ppid')
                pid = proc.info.get('pid')
                
                # SAFETY: Never kill our own children (like multiprocessing.Manager)
                if ppid == current_pid:
                    continue
                
                cmdline = proc.info['cmdline']
                exe = proc.info['exe']
                is_python = exe and 'python' in exe.lower()
                is_kaiacord = cmdline and any('Kaiacord.py' in arg for arg in cmdline)
                
                if is_python and is_kaiacord and pid != current_pid:
                    # Usually a live instance, not an orphan: one token runs one
                    # bot, so the newest wins. Give it time to shut down cleanly;
                    # that takes ~15 s, most of it persisting the RAG indices, and
                    # 5 s killed it partway through the write.
                    log_action(f"  - Stopping the other running instance: PID {pid}")
                    from utils.infrastructure.gpu.clear_gpu_memory import stop_and_reap
                    if stop_and_reap(proc, grace=OTHER_INSTANCE_GRACE_S, kill_wait=10.0):
                        log_success(f"  - PID {pid} has exited.")
                    else:
                        survivors.append(pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            except Exception as e:
                log_warning(f"Error checking process: {e}")

        if survivors:
            # Two processes on one token answer every message twice and write
            # the same state files; starting beside it is worse than not starting.
            log_critical(f"Another Kaiacord instance survived SIGKILL (PID {survivors}); not starting beside it.")
            raise SystemExit(1)

        # Clear GPU memory
        try:
            from utils.infrastructure.gpu.clear_gpu_memory import clear_gpu_memory
            clear_gpu_memory(silent=True)
        except Exception as e:
            log_warning(f"Failed to clear GPU memory: {e}")

    def perform_startup_tasks(self):
        """Perform startup tasks that need to run before either mode."""
        self.cleanup_on_startup()
        
        if self.config.startup_news_update:
            log_info("📰 News update enabled for this startup.")
        
        self.stats_poller.start()
        log_success("Stats poller started.")
        set_stats_poller(self.stats_poller)
        
        shutdown_manager.register_stats_poller(self.stats_poller)
        shutdown_manager.register_stop_event(self.stop_event)
        shutdown_manager.setup()
        
        print("✅ Startup tasks complete")
        return self.stats_poller

    async def perform_async_cleanup(self, rag, ollama_client):
        """Shutdown logic for both modes.
        
        Dashboard-specific cleanup runs here (stopping modular tasks, thread pool).
        Core cleanup (RAG persist, model unload, GPU release) is delegated to
        shutdown_manager.async_shutdown() to avoid duplicate work.
        """
        log_info("🔄 Shutting down...")
        
        # 1. Stop all modular background tasks (dashboard-specific)
        from utils.social.social_tasks import stop_social_tasks
        from utils.infrastructure.system.maintenance_tasks import stop_maintenance_tasks
        from utils.core.background_tasks import stop_background_core_tasks
        
        log_action("Stopping background tasks...")
        try:
            # 1a. Explicitly stop the tasks
            stop_social_tasks()
            stop_maintenance_tasks()
            stop_background_core_tasks()
            
            # 1b. Short wait for loops to yield before cancelling their tasks in registry
            await asyncio.sleep(0.5) 
            log_info("  ✅ Background loops signaled to stop")
        except Exception as e:
            log_error(f"Error stopping tasks: {e}")
        
        # 3. Stop stats poller
        if self.stats_poller:
            self.stats_poller.stop()
        
        # 4. Delegate core cleanup to shutdown_manager (single source of truth)
        # This handles: RAG persistence, task registry cancellation,
        # Ollama model unloading, GPU memory release, process cleanup.
        shutdown_manager.register_rag(rag)
        await shutdown_manager.async_shutdown(self.ctx)

        if shutdown_manager._shutdown_complete.is_set():
            log_success("Shutdown complete.")
        else:
            log_error("Shutdown is incomplete: pending tasks prevented safe resource teardown; the process will use its bounded emergency exit.")

    async def run_bot_async(self, stats_poller, initialize_logic_layer, 
                            sequenced_boot_tasks, stop_event=None):
        """Run the Discord bot with asyncio."""
        await asyncio.sleep(2)
        
        try:
            async with self.bot:
                if stop_event:
                    async def check_stop():
                        while not stop_event.is_set():
                            await asyncio.sleep(0.5)
                        await self.bot.close()
                    stop_task = asyncio.create_task(check_stop())
                    task_registry.register("stop_checker", stop_task)
                
                # Start boot sequence
                boot_task = asyncio.create_task(sequenced_boot_tasks())
                task_registry.register("sequenced_boot_tasks", boot_task)
                
                await self.bot.start(self.config.discord_token)
        except KeyboardInterrupt:
            print("\n⚠️  Keyboard interrupt received in bot loop")
        except asyncio.CancelledError:
            print("\n⚠️  Bot task cancelled")
        except Exception as e:
            print(f"\n❌ Error: {e}")
        finally:
            # Force the cleanup to finish before yielding back to asyncio.run
            try:
                # We wrap this in asyncio.shield to prevent it from being cancelled by
                # the outer KeyboardInterrupt propagating through asyncio.run
                await asyncio.shield(self.perform_async_cleanup(self.ctx.rag, self.ctx.ollama_client))
            except Exception as e:
                print(f"⚠️ Cleanup interrupted: {e}")

    def run_curses_mode(self, initialize_logic_layer, run_bot_async):
        """Run in curses dashboard mode."""
        if not self.config.discord_token:
            log_critical("DISCORD_TOKEN not found!")
            sys.exit(1)
        
        log_info("Starting curses dashboard mode...")
        
        # 1. Perform ALL startup tasks (cleanup, stats poller) FIRST
        sp = self.perform_startup_tasks()
        
        # 2. Initialize Multiprocessing IPC (Must happen BEFORE spawning process)
        # CRITICAL: Temporarily ignore SIGINT so the Manager subprocess inherits
        # SIG_IGN disposition. This prevents Ctrl+C from killing the Manager's
        # background process and breaking IPC during shutdown.
        original_sigint = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        manager = multiprocessing.Manager()
        signal.signal(signal.SIGINT, original_sigint)  # Restore for main process
        shared_stats = manager.dict()
        log_queue = multiprocessing.Queue(maxsize=1000)
        ui_error_queue = multiprocessing.Queue()
        m_stop_event = multiprocessing.Event()
        clean = False
        
        # Signal dashboard mode to suppress console and enable queue
        self.logger.set_dashboard_mode(True, queue=log_queue)

        try:
            # 3. Start UI in separate process (Isolates psutil and curses from bot GIL)
            self.dashboard_process = multiprocessing.Process(
                target=_run_dashboard_process,
                args=(shared_stats, log_queue, m_stop_event, ui_error_queue),
                name="KaiaDashboard",
                daemon=True
            )
            self.dashboard_process.start()
            
            # 4. Start Bot in separate thread of MAIN process
            self.bot_thread = threading.Thread(
                target=_run_bot_in_thread, 
                args=(shared_stats, self.stats_tracker, self.stats_poller, self.stop_event,
                      initialize_logic_layer, run_bot_async, self.ctx),
                daemon=True, 
                name="DiscordBot"
            )
            self.bot_thread.start()
            
            # 5. Monitor from main thread
            while self.bot_thread.is_alive():
                # Check for UI stop requested
                if m_stop_event.is_set():
                    self.stop_event.set()
                    break
                
                # Check for global shutdown signal (Ctrl+C)
                if shutdown_manager.shutting_down:
                    # Give bot thread time to finish async_shutdown
                    self.stop_event.set()
                    break
                    
                try:
                    # Check for UI errors
                    if not ui_error_queue.empty():
                        err_msg, err_tb = ui_error_queue.get_nowait()
                        log_error(f"DASHBOARD CRASHED: {err_msg}\n{err_tb}")
                        break
                        
                    if not self.dashboard_process.is_alive():
                        log_warning("Dashboard process died unexpectedly.")
                        break
                except (BrokenPipeError, EOFError, ConnectionError):
                    break
                    
                time.sleep(0.5)
            
            # Signaling stop to child process
            if not m_stop_event.is_set():
                try: m_stop_event.set()
                except Exception:
                    pass
            self.stop_event.set()
            
            clean = wait_for_bot_shutdown(self.bot_thread, self.dashboard_process, self.logger)

        except KeyboardInterrupt:
            print("\n⚠️  Keyboard interrupt received")
        except Exception as e:
            print(f"\n❌ Dashboard manager error: {e}")
            traceback.print_exc()
        finally:
            # 1. STOP LOGGING TO QUEUE IMMEDIATELY
            # This prevents deadlocks if we try to log errors while the dashboard process is dying.
            self.logger.set_dashboard_mode(False)
            
            # Terminate dashboard process if still running
            if hasattr(self, 'dashboard_process') and self.dashboard_process:
                if self.dashboard_process.is_alive():
                    self.dashboard_process.terminate()
                    self.dashboard_process.join(timeout=2.0)
                    if self.dashboard_process.is_alive():
                        self.dashboard_process.kill()
            
            # Shutdown the multiprocessing Manager cleanly
            try:
                manager.shutdown()
            except Exception:
                pass
            
            # Explicitly kill any child processes remaining (manager server, dashboard UI, IPC workers)
            try:
                current_process = psutil.Process()
                children = current_process.children(recursive=True)
                for child in children:
                    try:
                        child.terminate()
                    except Exception:
                        pass
                _, still_alive = psutil.wait_procs(children, timeout=1.5)
                for child in still_alive:
                    try:
                        child.kill()
                    except Exception:
                        pass
            except Exception:
                pass
            
            # ALWAYS kill orphaned Ollama runners (synchronous, no IPC needed)
            try:
                from utils.infrastructure.gpu.clear_gpu_memory import kill_orphaned_runners
                kill_orphaned_runners()
            except Exception:
                pass
            
            self.logger.set_dashboard_mode(False)
            try:
                # \033[0m    - Reset all attributes
                # \033[?25h  - Show cursor
                # \033[?1049l - Exit alternate screen buffer
                # \033[H      - Move cursor to home (top-left)
                # \033[2J     - Clear entire screen
                sys.__stdout__.write('\033[0m\033[?25h\033[?1049l\033[H\033[2J')
                sys.__stdout__.flush()
            except Exception:
                pass
            sys.__stdout__.write("\n[SUCCESS] Kaia has entered hibernation.\n" if clean else
                                 "\n[WARNING] Kaia stopped before her shutdown finished; see logs/kaiacord.log.\n")
            sys.__stdout__.flush()
            
            # Direct clean force exit - avoids lingering threads or unjoined multiprocessing server
            shutdown_manager.force_exit(0 if clean else 1)

    async def run_simple_mode(self, initialize_logic_layer, run_bot_async):
        """Run in simple ANSI mode."""
        if not self.config.discord_token:
            log_critical("DISCORD_TOKEN not found!")
            sys.exit(1)
            
        failed = False
        try:
            print("🚀 Using simple logger")
            sp = self.perform_startup_tasks()
            # Ensure logic layer is initialized
            if inspect.iscoroutinefunction(initialize_logic_layer):
                await initialize_logic_layer()
            else:
                initialize_logic_layer()
            # The stop event is what a SIGTERM sets. Without it nothing here
            # closes the client, and the process never exits.
            await run_bot_async(sp, self.stop_event)
        except Exception as e:
            # Check if it's just the expected cascade from the inner loop cancellation
            if not isinstance(e, asyncio.CancelledError):
                print(f"\n❌ Error in simple mode: {e}")
                failed = True
        finally:
            # ALWAYS kill orphaned Ollama runners (synchronous, no IPC needed)
            try:
                from utils.infrastructure.gpu.clear_gpu_memory import kill_orphaned_runners
                kill_orphaned_runners()
            except Exception:
                pass
                
            self.logger.set_dashboard_mode(False)
            sys.__stdout__.write("\n[SUCCESS] Kaia has entered hibernation.\n")
            sys.__stdout__.flush()
            
            # Direct clean force exit
            shutdown_manager.force_exit(1 if failed else 0)
