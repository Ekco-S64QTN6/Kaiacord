#!/usr/bin/env python3
"""
Utility script to aggressively clear GPU memory when Kaiacord has OOM issues.
Run this script to reset PyTorch's CUDA allocator without restarting the bot.
"""

import gc
import sys


def clear_gpu_memory(silent: bool = False):
    """Aggressively clear all GPU memory"""
    # Lazy import to avoid Python 3.14 startup hang from torch.quantization
    try:
        import torch
    except ImportError:
        if not silent:
            print("PyTorch not installed")
        return
    
    if not torch.cuda.is_available():
        if not silent:
            print("CUDA not available")
        return
    
    if not silent:
        print("Clearing GPU memory...")
    
    # Empty cache multiple times (2 passes is usually sufficient)
    for _ in range(2):
        gc.collect()
        torch.cuda.empty_cache()
    
    # Synchronize CUDA operations
    torch.cuda.synchronize()
    
    # Reset memory stats
    torch.cuda.reset_peak_memory_stats()
    torch.cuda.reset_accumulated_memory_stats()
    
    # Final cache clear
    torch.cuda.empty_cache()
    
    if not silent:
        print("GPU memory cleared")


def force_clear_gpu() -> bool:
    """
    Emergency GPU cleanup - more aggressive than clear_gpu_memory.
    
    Attempts to release ALL GPU memory including reserved pools.
    Use during shutdown or after critical failures.
    
    Returns:
        True if cleanup was successful, False otherwise
    """
    try:
        import torch
    except ImportError:
        return True  # No torch = nothing to clear = success
    
    if not torch.cuda.is_available():
        return True
    
    try:
        # Phase 1: Standard cleanup (Reduced loops for efficiency)
        for _ in range(2):
            gc.collect()
            torch.cuda.empty_cache()
        
        torch.cuda.synchronize()
        
        # Phase 2: Reset allocator stats
        torch.cuda.reset_peak_memory_stats()
        torch.cuda.reset_accumulated_memory_stats()
        
        # Phase 3: IPC cleanup for multi-process scenarios
        try:
            torch.cuda.ipc_collect()
        except:
            pass
        
        # Phase 4: Final cleanup
        gc.collect()
        torch.cuda.empty_cache()
        
        torch.cuda.synchronize()
        
        # Check result
        allocated = torch.cuda.memory_allocated() / 1024**3
        
        return allocated < 0.5  # Success if less than 0.5 GiB still allocated
        
    except Exception as e:
        print(f"GPU force clear error: {e}")
        return False


def kill_orphaned_runners(preserve_model: str = None, preserve_ctx: int = None):
    """Aggressively unload VRAM via sync HTTP, then kill any lingering ollama runners."""
    import psutil
    import os
    import json
    import urllib.request
    import urllib.error

    # 1. Graceful Synchronous Unload (Bypasses active async event loops)
    print("🔄 Ensuring all models are flushed from VRAM via HTTP...")
    try:
        # Check what's ACTUALLY running instead of all installed tags
        req = urllib.request.Request("http://127.0.0.1:11434/api/ps", method="GET")
        with urllib.request.urlopen(req, timeout=3.0) as response:
             data = json.loads(response.read().decode())
             running_models = data.get("models", [])
             
        for model_info in running_models:
             name = model_info.get("name", "")
             ctx_len = model_info.get("context_length", 0)
             
             # Optimization: If the model we want is already running with correct context, skip unloading it
             if preserve_model and (preserve_model in name or name in preserve_model):
                 if preserve_ctx is None or ctx_len == preserve_ctx:
                     print(f"  ✅ Preserving {name} (already resident with {ctx_len} ctx)")
                     continue
             
             print(f"  🔄 Unloading {name}...")
             payload = json.dumps({"model": name, "keep_alive": 0}).encode("utf-8")
             preq = urllib.request.Request(
                 "http://127.0.0.1:11434/api/generate",
                 data=payload,
                 headers={"Content-Type": "application/json"},
                 method="POST"
             )
             try:
                 with urllib.request.urlopen(preq, timeout=2.0) as p_resp:
                     pass # Unloaded cleanly
             except Exception:
                 pass
        print("  ✅ Sent kill signals to Ollama daemon.")
    except Exception as e:
        print(f"  ⚠️ Could not ping Ollama daemon for flush: {e}")

    # 2. Hard Kill lingering rogue runners
    current_pid = os.getpid()
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info.get('cmdline') or []
            cmd_str = ' '.join(cmdline).lower()
            proc_name = proc.info['name'].lower()
            
            if 'ollama' in proc_name or 'ollama' in cmd_str:
                if 'runner' in cmd_str:
                    if proc.info['pid'] != current_pid:
                        try:
                            proc.terminate()
                            proc.wait(timeout=2)
                        except (psutil.TimeoutExpired, Exception):
                            proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    
    print("✨ Ollama cleanup finalized.")


if __name__ == "__main__":
    kill_orphaned_runners()
    clear_gpu_memory()

