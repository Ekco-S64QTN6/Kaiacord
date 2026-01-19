import os

# Set PyTorch CUDA allocator to use expandable segments to reduce fragmentation
# These MUST be set before torch is imported
os.environ["PYTORCH_ALLOC_CONF"] = "expandable_segments:True,max_split_size_mb:512"
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True,max_split_size_mb:512"

import torch
from diffusers import FluxPipeline, FluxTransformer2DModel
from transformers import T5EncoderModel, CLIPTextModel, BitsAndBytesConfig
import asyncio
import aiohttp
import tempfile
import logging
import gc
import time

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kaia_image")

# Allow full use of GPU memory
torch.cuda.set_per_process_memory_fraction(1.0)

# Global lock to prevent concurrent generations
generation_lock = asyncio.Lock()

import urllib.request
import json

async def unload_ollama_models():
    """
    Unloads all running Ollama models to free up VRAM for image generation.
    Uses aiohttp for efficiency.
    """
    try:
        async with aiohttp.ClientSession() as session:
            # 1. List running models
            async with session.get("http://localhost:11434/api/ps") as response:
                if response.status != 200:
                    logger.warning(f"Failed to list Ollama models: HTTP {response.status}")
                    return
                data = await response.json()
                models = data.get('models', [])
                
            if not models:
                logger.info("No Ollama models running.")
                return

            # 2. Unload each model
            for model in models:
                name = model['name']
                logger.info(f"Unloading Ollama model: {name}...")
                
                # Send request to unload (keep_alive=0)
                payload = {"model": name, "keep_alive": 0}
                try:
                    async with session.post("http://localhost:11434/api/generate", json=payload) as resp:
                        await resp.read() # Ensure request is sent
                except Exception as e:
                    logger.warning(f"Failed to unload model {name}: {e}")

            # 3. Verify they are gone (wait up to 5 seconds)
            for i in range(5):
                async with session.get("http://localhost:11434/api/ps") as response:
                    data = await response.json()
                    if not data.get('models', []):
                        logger.info("All Ollama models successfully unloaded.")
                        return
                await asyncio.sleep(1)
            
            logger.warning("Some Ollama models might still be loading/unloading.")
        
    except Exception as e:
        logger.error(f"Error checking/unloading Ollama models: {e}")

# Global pipeline cache
_pipe = None

def _get_pipeline():
    """
    Initializes and returns the Flux pipeline.
    Uses a global cache to avoid reloading from disk on every call.
    Uses CPU offloading to manage VRAM efficiently.
    """
    global _pipe
    if _pipe is not None:
        return _pipe

    model_id = "black-forest-labs/FLUX.1-schnell"
    
    # 4-bit quantization config for T5 and Transformer
    quant_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True
    )

    logger.info("Initializing Flux pipeline (first run will load from disk)...")
    
    # Aggressive cleanup before loading
    gc.collect()
    torch.cuda.empty_cache()
    torch.cuda.synchronize()

    try:
        # Load components one by one on CPU to avoid GPU spike
        logger.info("Loading T5 (4-bit)...")
        text_encoder_2 = T5EncoderModel.from_pretrained(
            model_id,
            subfolder="text_encoder_2",
            quantization_config=quant_config,
            dtype=torch.bfloat16,
            local_files_only=True,
            device_map="balanced",
            low_cpu_mem_usage=True
        )
        
        logger.info("Loading Transformer (4-bit)...")
        transformer = FluxTransformer2DModel.from_pretrained(
            model_id,
            subfolder="transformer",
            quantization_config=quant_config,
            dtype=torch.bfloat16,
            local_files_only=True,
            device_map="balanced",
            low_cpu_mem_usage=True
        )
        
        # Load the full pipeline on CPU
        logger.info("Assembling pipeline...")
        _pipe = FluxPipeline.from_pretrained(
            model_id,
            text_encoder_2=text_encoder_2,
            transformer=transformer,
            dtype=torch.bfloat16,
            local_files_only=True,
            device_map="balanced",
            low_cpu_mem_usage=True
        )
        
        # CRITICAL: Enable model CPU offload
        # This moves components to CPU RAM and only loads them to GPU when needed.
        # This is the key to running Flux on 12GB VRAM.
        logger.info("Enabling model CPU offload...")
        _pipe.enable_model_cpu_offload()
        
        # Memory optimizations
        _pipe.enable_vae_slicing()
        _pipe.enable_vae_tiling()
        
        logger.info("Flux pipeline initialized successfully.")
        return _pipe
        
    except Exception as e:
        logger.error(f"Failed to initialize Flux pipeline: {e}")
        _pipe = None
        # Clean up any partial loads
        gc.collect()
        torch.cuda.empty_cache()
        raise

def _generate_image_sync(prompt: str):
    """
    Synchronous image generation logic.
    """
    try:
        # Ensure VRAM is as clean as possible
        gc.collect()
        torch.cuda.empty_cache()
        torch.cuda.synchronize()
        
        pipe = _get_pipeline()
        
        logger.info(f"Generating image for prompt: {prompt}")
        start_time = time.time()
        
        # Generate image using the pipeline
        # Flux Schnell is optimized for 4 steps and 0 guidance
        with torch.inference_mode():
            result = pipe(
                prompt=prompt,
                num_inference_steps=4,
                guidance_scale=0.0,
                max_sequence_length=256,
                output_type="pil"
            )
        
        image = result.images[0]
        
        # Save to temp file
        temp_fd, temp_path = tempfile.mkstemp(suffix=".png")
        os.close(temp_fd)
        image.save(temp_path)
        
        duration = time.time() - start_time
        logger.info(f"Image generated in {duration:.2f}s and saved to {temp_path}")
        
        return temp_path
        
    except torch.cuda.OutOfMemoryError as oom_err:
        logger.error(f"CUDA Out of Memory during generation: {oom_err}")
        # Clear the pipe on OOM to allow a fresh start next time
        global _pipe
        _pipe = None
        gc.collect()
        torch.cuda.empty_cache()
        raise RuntimeError("GPU out of memory. Try restarting the bot to fully clear VRAM.") from oom_err
        
    except Exception as e:
        logger.error(f"Error during image generation: {e}")
        raise
        
    finally:
        # Aggressive cleanup of residual VRAM
        gc.collect()
        torch.cuda.empty_cache()
        torch.cuda.synchronize()

async def generate_image(prompt: str):
    """
    Wraps image generation in asyncio.to_thread to avoid blocking the Discord heartbeat.
    Uses a lock to ensure only one generation runs at a time.
    """
    async with generation_lock:
        # Free up VRAM from Ollama first (async)
        await unload_ollama_models()
        # Run generation in a separate thread
        return await asyncio.to_thread(_generate_image_sync, prompt)
