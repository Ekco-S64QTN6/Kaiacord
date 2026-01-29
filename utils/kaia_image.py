"""
Kaia Image Generation Module
============================

Flux-based image generation with circuit breaker and hard recovery.

Features:
- Lazy model loading to minimize VRAM usage
- Circuit breaker: disables image gen after CUDA OOM
- Hard GPU recovery with forced cleanup
- Output suppression during model operations
"""

import asyncio
import contextlib
import io
import os
import gc
import sys
from typing import Optional, Tuple
from utils.unified_logging import logger

# Set PyTorch allocator configuration BEFORE importing torch
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

# Global lock for generation
generation_lock = asyncio.Lock()

# Global pipeline reference
_pipe = None

# Circuit breaker state
_image_gen_disabled = False
_oom_recovery_in_progress = False
_disable_reason = ""


def is_image_gen_available() -> bool:
    """Check if image generation is available (not disabled by OOM)."""
    return not _image_gen_disabled


def get_disable_reason() -> str:
    """Get the reason image generation was disabled."""
    return _disable_reason


async def _hard_gpu_recovery() -> bool:
    """
    Perform hard GPU recovery after OOM.
    
    This aggressively clears all GPU memory and resets state.
    Returns True if recovery appears successful.
    """
    global _pipe
    
    logger.log("Performing hard GPU recovery...", "ACTION")
    
    try:
        import torch
    except ImportError:
        return False
    
    # Step 1: Delete pipeline reference
    if _pipe is not None:
        try:
            del _pipe
        except:
            pass
        _pipe = None
    
    # Step 2: Force garbage collection multiple times
    for i in range(5):
        gc.collect()
    
    # Step 3: Clear CUDA cache aggressively
    if torch.cuda.is_available():
        try:
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
            torch.cuda.reset_peak_memory_stats()
            torch.cuda.reset_accumulated_memory_stats()
            
            # Additional cache clears
            for _ in range(3):
                gc.collect()
                torch.cuda.empty_cache()
            
            # Check if memory was actually freed
            allocated = torch.cuda.memory_allocated() / 1024**3
            reserved = torch.cuda.memory_reserved() / 1024**3
            free = (torch.cuda.get_device_properties(0).total_memory - torch.cuda.memory_allocated()) / 1024**3
            
            logger.log(f"🔧 GPU Recovery Results:", "INFO")
            logger.log(f"  Allocated: {allocated:.2f} GiB", "INFO")
            logger.log(f"  Reserved: {reserved:.2f} GiB", "INFO")
            logger.log(f"  Free: {free:.2f} GiB", "INFO")
            
            # If still holding significant memory, try IPC collect
            if reserved > 1.0:
                logger.log("Attempting IPC collection for stubborn memory...", "DEBUG")
                try:
                    torch.cuda.ipc_collect()
                    gc.collect()
                    torch.cuda.empty_cache()
                    
                    # Re-check
                    allocated = torch.cuda.memory_allocated() / 1024**3
                    reserved = torch.cuda.memory_reserved() / 1024**3
                    logger.log(f"  After IPC: Allocated {allocated:.2f} GiB, Reserved {reserved:.2f} GiB", "DEBUG")
                except Exception as ipc_err:
                    logger.log(f"IPC collection failed: {ipc_err}", "DEBUG")
            
            # Success if under 0.5 GiB allocated and freed reasonable amount
            success = allocated < 0.5 and free > 4.0
            if success:
                logger.log("✅ GPU recovery successful", "SUCCESS")
            else:
                logger.log(f"⚠️ GPU recovery partial ({allocated:.2f} GiB still allocated)", "WARNING")
            
            return success
            
        except Exception as e:
            logger.log(f"GPU recovery error: {e}", "ERROR")
            return False
    
    return True


async def generate_image(prompt: str, output_path: str) -> Tuple[bool, str]:
    """
    Generate an image using Flux pipeline (Lazy Loaded).
    
    Returns:
        Tuple of (success, result_path_or_error_message)
    """
    global _pipe, _image_gen_disabled, _oom_recovery_in_progress, _disable_reason
    
    # Circuit breaker check
    if _image_gen_disabled:
        return False, f"Image generation disabled: {_disable_reason}. Restart required."
    
    if _oom_recovery_in_progress:
        return False, "GPU recovery in progress. Please wait."
    
    # Lazy import heavy dependencies
    try:
        import torch
        from diffusers import FluxPipeline
        from utils.clear_gpu_memory import clear_gpu_memory
    except ImportError as e:
        return False, f"Failed to import dependencies: {e}"

    try:
        async with generation_lock:
            logger.log("Starting image generation...", "ACTION")
            
            # Set memory fraction to leave headroom
            if torch.cuda.is_available():
                torch.cuda.set_per_process_memory_fraction(0.80)
                
            # Aggressive cleanup DISABLED during active generation (Rollback)
            # clear_gpu_memory() 
            
            # Load model if not loaded
            if _pipe is None:
                logger.log("Loading Flux model (this may take a moment)...", "INFO")
                
                # Pre-flight memory check
                if torch.cuda.is_available():
                    # Get detailed memory info
                    total_mem = torch.cuda.get_device_properties(0).total_memory / 1024**3
                    allocated_mem = torch.cuda.memory_allocated() / 1024**3
                    reserved_mem = torch.cuda.memory_reserved() / 1024**3
                    free_mem = total_mem - allocated_mem
                    
                    logger.log(f"GPU Memory Status:", "DEBUG")
                    logger.log(f"  Total: {total_mem:.2f} GiB", "DEBUG")
                    logger.log(f"  Allocated: {allocated_mem:.2f} GiB", "DEBUG")
                    logger.log(f"  Reserved: {reserved_mem:.2f} GiB", "DEBUG")
                    logger.log(f"  Free: {free_mem:.2f} GiB", "DEBUG")
                    
                    # REQUIREMENT: Fail fast if VRAM is insufficient (need 8GB for safety with chat model)
                    if free_mem < 8.0:
                        logger.log(f"❌ VRAM check failed: {free_mem:.1f} GiB free, need 8.0+ GiB", "ERROR")
                        logger.log("💡 Chat model is using VRAM. Wait or restart to free memory.", "INFO")
                        return False, f"Insufficient VRAM ({free_mem:.1f} GiB free, need 8.0+ GiB). Image generation aborted to protect chat model."
                
                # Suppress stdout/stderr during model load to protect dashboard
                def load_pipeline():
                    with contextlib.redirect_stdout(io.StringIO()), \
                         contextlib.redirect_stderr(io.StringIO()):
                        return FluxPipeline.from_pretrained(
                            "black-forest-labs/FLUX.1-schnell",
                            torch_dtype=torch.bfloat16
                        )
                
                # Run loading in thread to avoid blocking event loop
                _pipe = await asyncio.to_thread(load_pipeline)
                
                # Move to GPU with CPU offloading (also suppress output)
                def enable_offload():
                    with contextlib.redirect_stdout(io.StringIO()), \
                         contextlib.redirect_stderr(io.StringIO()):
                        _pipe.enable_model_cpu_offload()
                
                await asyncio.to_thread(enable_offload)
            
            # Generate
            logger.log(f"Generating: {prompt}", "INFO")
            
            # Run generation in thread with output suppression
            def run_generation():
                with contextlib.redirect_stdout(io.StringIO()), \
                     contextlib.redirect_stderr(io.StringIO()):
                    return _pipe(
                        prompt,
                        guidance_scale=0.0,
                        num_inference_steps=4,
                        max_sequence_length=256,
                        generator=torch.Generator("cpu").manual_seed(0)
                    ).images[0]
            
            image = await asyncio.to_thread(run_generation)
            
            # Save
            await asyncio.to_thread(image.save, output_path)
            
            logger.log(f"Image saved to {output_path}", "SUCCESS")
            return True, output_path
            
    except torch.cuda.OutOfMemoryError as oom:
        # CIRCUIT BREAKER: Disable image generation
        _image_gen_disabled = True
        _oom_recovery_in_progress = True
        _disable_reason = "CUDA out of memory"
        
        logger.log(f"🚨 CUDA Out of Memory Error", "ERROR")
        logger.log(f"Error details: {oom}", "ERROR")
        logger.log("⚠️ IMAGE GENERATION DISABLED until restart.", "CRITICAL")
        logger.log("ℹ️ Chat functionality should still work.", "INFO")
        
        # Attempt hard recovery
        logger.log("Attempting automatic GPU recovery...", "ACTION")
        recovery_success = await _hard_gpu_recovery()
        _oom_recovery_in_progress = False
        
        if recovery_success:
            logger.log("✅ GPU memory recovered successfully.", "SUCCESS")
            logger.log("⚠️ Image generation remains DISABLED for safety (restart required).", "WARNING")
            logger.log("💡 Tip: To prevent this, ensure 8+ GiB VRAM is free before generating images.", "INFO")
        else:
            logger.log("❌ GPU recovery incomplete.", "ERROR")
            logger.log("💡 Manual intervention may be needed. Try restarting the bot.", "WARNING")
        
        return False, "CUDA out of memory. Image generation disabled until restart. Chat still works."
        
    except Exception as e:
        logger.log(f"Image generation failed: {e}", "ERROR")
        # Don't disable for non-OOM errors, but do cleanup
        try:
            await unload_image_model()
        except:
            pass
        return False, str(e)


async def unload_image_model() -> bool:
    """
    Unload the model to free VRAM (Lazy Loaded).
    
    Returns:
        True if unload was successful or no model was loaded
    """
    global _pipe
    
    # Lazy import torch
    try:
        import torch
    except ImportError:
        return True  # Nothing to unload if torch isn't installed
        
    if _pipe is not None:
        logger.log("Unloading image model...", "INFO")
        
        try:
            del _pipe
        except:
            pass
        _pipe = None
        
        # Aggressive cleanup
        for _ in range(3):
            gc.collect()
        
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
        
        logger.log("Image model unloaded", "SUCCESS")
        return True
    
    return True  # Already unloaded


def force_disable_image_gen(reason: str = "Manual disable") -> None:
    """Manually disable image generation (for emergency use)."""
    global _image_gen_disabled, _disable_reason
    _image_gen_disabled = True
    _disable_reason = reason
    logger.log(f"Image generation manually disabled: {reason}", "WARNING")


def get_pipeline_status() -> dict:
    """Get current status of the image pipeline for debugging."""
    try:
        import torch
        gpu_allocated = torch.cuda.memory_allocated() / 1024**3 if torch.cuda.is_available() else 0
        gpu_reserved = torch.cuda.memory_reserved() / 1024**3 if torch.cuda.is_available() else 0
    except:
        gpu_allocated = 0
        gpu_reserved = 0
    
    return {
        "pipeline_loaded": _pipe is not None,
        "disabled": _image_gen_disabled,
        "disable_reason": _disable_reason,
        "recovery_in_progress": _oom_recovery_in_progress,
        "gpu_allocated_gb": round(gpu_allocated, 2),
        "gpu_reserved_gb": round(gpu_reserved, 2),
    }

