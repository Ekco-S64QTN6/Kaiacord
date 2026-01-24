import asyncio
import os
import gc
from typing import Optional, Tuple
from utils.unified_logging import logger

# Global lock for generation
generation_lock = asyncio.Lock()

# Global pipeline reference
_pipe = None

async def generate_image(prompt: str, output_path: str) -> Tuple[bool, str]:
    """Generate an image using Flux pipeline (Lazy Loaded)"""
    global _pipe
    
    # Lazy import heavy dependencies
    try:
        import torch
        from diffusers import FluxPipeline
    except ImportError as e:
        return False, f"Failed to import dependencies: {e}"

    try:
        async with generation_lock:
            logger.log("Starting image generation...", "ACTION")
            
            # Load model if not loaded
            if _pipe is None:
                logger.log("Loading Flux model (this may take a moment)...", "INFO")
                # Run loading in thread to avoid blocking event loop
                _pipe = await asyncio.to_thread(
                    FluxPipeline.from_pretrained,
                    "black-forest-labs/FLUX.1-schnell",
                    torch_dtype=torch.bfloat16
                )
                
                # Move to GPU
                await asyncio.to_thread(_pipe.enable_model_cpu_offload)
            
            # Generate
            logger.log(f"Generating: {prompt}", "INFO")
            
            # Run generation in thread
            image = await asyncio.to_thread(
                lambda: _pipe(
                    prompt,
                    guidance_scale=0.0,
                    num_inference_steps=4,
                    max_sequence_length=256,
                    generator=torch.Generator("cpu").manual_seed(0)
                ).images[0]
            )
            
            # Save
            await asyncio.to_thread(image.save, output_path)
            
            logger.log(f"Image saved to {output_path}", "SUCCESS")
            return True, output_path
            
    except Exception as e:
        logger.log(f"Image generation failed: {e}", "ERROR")
        return False, str(e)

async def unload_image_model():
    """Unload the model to free VRAM (Lazy Loaded)"""
    global _pipe
    
    # Lazy import torch
    try:
        import torch
    except ImportError:
        return # Nothing to unload if torch isn't installed
        
    if _pipe is not None:
        logger.log("Unloading image model...", "INFO")
        del _pipe
        _pipe = None
        
        # Clear CUDA cache
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
            
        gc.collect()
        logger.log("Image model unloaded", "SUCCESS")
