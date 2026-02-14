import os
import sys
import asyncio
import psutil
import threading
import concurrent.futures
import traceback
from datetime import datetime
from typing import Optional, Any, List

from utils.infrastructure.logging.kaia_logger import (
    log_info, log_success, log_warning, log_error, log_action, log_separator, log_debug
)
from utils.infrastructure.system.shutdown_fixed import shutdown_manager
from utils.infrastructure.monitoring.stats_helpers import set_stats_poller
from utils.infrastructure.monitoring.btop_dashboard_v2 import BtopDashboardV2
from utils.infrastructure.monitoring.async_task_registry import task_registry

class DashboardManager:
    """Manages the lifecycle of the bot's terminal dashboard and run modes."""
    
    def __init__(self, ctx, bot, config, bot_state, stats_tracker, stats_poller, 
                 logger, model_warm_pool, intent_parser):
        self.ctx = ctx
        self.bot = bot
        self.config = config
        self.bot_state = bot_state
        self.stats_tracker = stats_tracker
        self.stats_poller = stats_poller
        self.logger = logger
        self.model_warm_pool = model_warm_pool
        self.intent_parser = intent_parser
        
        # Internal state
        self.dashboard = None
        self.stop_event = threading.Event()
        self.cleanup_complete_event = threading.Event()
        self.bot_thread = None

    def cleanup_on_startup(self):
        """Kill-other instances of Kaiacord and clear GPU memory."""
        current_pid = os.getpid()
        log_action(f"Startup cleanup (PID: {current_pid})...")
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'exe']):
            try:
                cmdline = proc.info['cmdline']
                exe = proc.info['exe']
                is_python = exe and 'python' in exe.lower()
                is_kaiacord = cmdline and any('Kaiacord.py' in arg for arg in cmdline)
                
                if is_python and is_kaiacord and proc.info['pid'] != current_pid:
                    log_action(f"  - Terminating orphaned instance: PID {proc.info['pid']}")
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                        log_success(f"  - PID {proc.info['pid']} terminated.")
                    except psutil.TimeoutExpired:
                        log_warning(f"  - PID {proc.info['pid']} didn't terminate, killing...")
                        proc.kill()
                        log_success(f"  - PID {proc.info['pid']} killed.")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            except Exception as e:
                log_warning(f"Error checking process: {e}")

        # Clear GPU memory
        try:
            from utils.infrastructure.gpu.clear_gpu_memory import clear_gpu_memory
            clear_gpu_memory()
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
        
        # 2. Shut down RAG thread pool (dashboard-specific)
        try:
            from Kaiacord import rag_executor
            if rag_executor:
                log_action("Shutting down RAG thread pool...")
                try:
                    rag_executor.shutdown(wait=False, cancel_futures=True)
                except TypeError:
                    rag_executor.shutdown(wait=False)
                log_success("RAG thread pool shutdown initiated.")
        except Exception as e:
            log_warning(f"Error shutting down RAG executor: {e}")
        
        # 3. Stop stats poller
        if self.stats_poller:
            self.stats_poller.stop()
        
        # 4. Delegate core cleanup to shutdown_manager (single source of truth)
        # This handles: RAG persistence, task registry cancellation,
        # Ollama model unloading, GPU memory release, process cleanup.
        shutdown_manager.register_rag(rag)
        await shutdown_manager.async_shutdown(self.ctx)
        
        log_success("Shutdown complete.")

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
            print("\n⚠️  Keyboard interrupt received")
        except asyncio.CancelledError:
            print("\n⚠️  Bot task cancelled")
        except Exception as e:
            print(f"\n❌ Error: {e}")
        finally:
            # RAG and Ollama Client for cleanup
            await self.perform_async_cleanup(self.ctx.rag, self.ctx.ollama_client)

    async def sequenced_boot_tasks(self, run_rag, rag, run_news_update, 
                                   prewarm_main_model):
        """Sequenced boot tasks migrated from Kaiacord.py."""
        log_info("📦 Phase 1/3: Rebuilding knowledge index...")
        try:
            await run_rag(rag.refresh_knowledge_base)
            log_success("📦 Knowledge index ready.")
        except Exception as e:
            log_error(f"RAG refresh failed: {e}")
        
        if self.config.startup_news_update:
            log_info("📰 Phase 2/3: Updating news...")
            try:
                await run_news_update()
                log_success("📰 News update complete.")
            except Exception as e:
                log_error(f"News update failed: {e}")
        
        log_info("🧠 Phase 3/3: Loading chat model into VRAM...")
        try:
            await prewarm_main_model()
            log_success("🧠 Chat model hot.")
            
            # Now pre-warm classifier sequentially to avoid VRAM contention
            log_info("🧠 Warming classifier...")
            await self.intent_parser.pre_warm()
        except Exception as e:
            log_error(f"Model prewarm failed: {e}")
        
        # Pre-warm RAG (mostly CPU/disk/IO) - Await this so it finishes before Ready
        log_action("Pre-warming RAG cache...")
        await run_rag(rag.pre_warm)
        
        # Final Readiness Milestone
        self.bot_state.boot_complete = True
        from utils.infrastructure.logging.kaia_logger import log_ready
        log_ready("Kaia is online and ready.")
    def run_curses_mode(self, initialize_logic_layer, run_bot_async):
        """Run in curses dashboard mode."""
        if not self.config.discord_token:
            log_critical("DISCORD_TOKEN not found!")
            sys.exit(1)
        
        log_info("Starting curses dashboard mode...")
        shutdown_manager.setup()
        
        # REQUIREMENT: Set dashboard mode EARLY to prevent logs from leaking
        # before the curses screen can take over.
        self.logger.set_dashboard_mode(True)
        
        def run_bot_in_thread():
            sp = self.perform_startup_tasks()
            
            if self.dashboard and sp:
                self.dashboard.stats_poller = sp
                
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Initialize logic inside the loop
                initialize_logic_layer()
                loop.run_until_complete(run_bot_async(sp, self.stop_event))
            finally:
                # FINAL DRAIN: Ensure all tasks (especially discord.ext.tasks)
                # have finished their internal cleanup callbacks before closing loop.
                try:
                    # Give tasks a final moment to react to the cancellation
                    # that should have happened in perform_async_cleanup
                    pending = asyncio.all_tasks(loop)
                    
                    if pending:
                        # Process any immediate callbacks
                        loop.run_until_complete(asyncio.sleep(0.2))
                        
                        # Gather again in case sleep triggered more tasks
                        pending = asyncio.all_tasks(loop)
                        for task in pending:
                            if not task.done():
                                task.cancel()
                        
                        # Wait for tasks to finish their finally blocks
                        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                    
                    # Handle async generators
                    loop.run_until_complete(loop.shutdown_asyncgens())
                except Exception as e:
                    # Curses might be dead, but we log to stderr if possible
                    print(f"[SHUTDOWN] Loop drainage error: {e}", file=sys.stderr)
                
                self.cleanup_complete_event.set()
                # Final safeguard: ensure loop is still running before closing
                if not loop.is_closed():
                    loop.close()
        
        try:
            self.dashboard = BtopDashboardV2(
                stats_poller=None,
                logger=self.logger,
                stats_tracker=self.stats_tracker,
                stop_event=self.stop_event,
                cleanup_complete_event=self.cleanup_complete_event
            )
            
            self.bot_thread = threading.Thread(target=run_bot_in_thread, daemon=True, name="DiscordBot")
            self.bot_thread.start()
            
            self.dashboard.run()
        except KeyboardInterrupt:
            print("\n⚠️  Keyboard interrupt received")
        except Exception as e:
            print(f"\n❌ Dashboard error: {e}")
            traceback.print_exc()
        finally:
            if self.dashboard:
                try: self.dashboard.stop()
                except: pass
            
            self.logger.set_dashboard_mode(False)
            sys.__stdout__.write('\033[0m\033[?25h\033[?1049l\033[H\033[2J')
            sys.__stdout__.flush()
            sys.__stdout__.write("\n[SUCCESS] Kaia has entered hibernation.\n")
            sys.__stdout__.flush()

    async def run_simple_mode(self, run_bot_async):
        """Run in simple ANSI mode."""
        if not self.config.discord_token:
            log_critical("DISCORD_TOKEN not found!")
            sys.exit(1)
            
        print("🚀 Using simple logger")
        sp = self.perform_startup_tasks()
        # Ensure logic layer is initialized
        from Kaiacord import initialize_logic_layer
        initialize_logic_layer()
        await run_bot_async(sp)
