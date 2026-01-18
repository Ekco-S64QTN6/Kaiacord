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

def _generate_image_sync(prompt: str):
    model_id = "black-forest-labs/FLUX.1-schnell"
    
    # 4-bit quantization config
    quant_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True
    )

    # Initialize variables to None for safe cleanup
    pipe_enc = None
    text_encoder = None
    text_encoder_2 = None
    pipe_gen = None
    transformer = None
    prompt_embeds = None
    pooled_prompt_embeds = None
    image = None

    try:
        # --- STEP 1: ENCODING ---
        logger.info("Step 1/2: Loading encoders...")
        
        # Load CLIP (text_encoder) manually to ensure we can delete it
        text_encoder = CLIPTextModel.from_pretrained(
            model_id,
            subfolder="text_encoder",
            torch_dtype=torch.bfloat16,
            local_files_only=True
        )
        
        # Load T5 in 4-bit to save VRAM (3GB)
        text_encoder_2 = T5EncoderModel.from_pretrained(
            model_id,
            subfolder="text_encoder_2",
            quantization_config=quant_config,
            torch_dtype=torch.bfloat16,
            local_files_only=True
        )
        
        # Load Pipeline with Encoders only
        pipe_enc = FluxPipeline.from_pretrained(
            model_id,
            text_encoder=text_encoder,
            text_encoder_2=text_encoder_2,
            transformer=None,
            vae=None,
            torch_dtype=torch.bfloat16,
            local_files_only=True
        )
        pipe_enc.to("cuda")
        
        logger.info("Encoding prompt...")
        with torch.no_grad():
            # encode_prompt returns prompt_embeds, pooled_prompt_embeds, text_ids
            prompt_embeds, pooled_prompt_embeds, text_ids = pipe_enc.encode_prompt(
                prompt=prompt,
                prompt_2=prompt,
                device="cuda"
            )
            
        # Move embeddings to CPU and delete GPU versions
        prompt_embeds = prompt_embeds.cpu()
        pooled_prompt_embeds = pooled_prompt_embeds.cpu()
        text_ids = text_ids.cpu()
        
        logger.info(f"Embeddings moved to CPU. GPU memory: {torch.cuda.memory_allocated() / 1024**3:.2f} GiB allocated")
        
        # Cleanup Encoders
        logger.info("Deleting encoders from GPU...")
        # pipe_enc.to("cpu")  <-- REMOVED: Causes RAM spike
        # text_encoder.to("cpu")
        # text_encoder_2.to("cpu")
        
        del pipe_enc
        del text_encoder
        del text_encoder_2
        
        # Explicitly set to None
        pipe_enc = None
        text_encoder = None
        text_encoder_2 = None
        
        # Clear any other local variables that might hold GPU tensors
        if 'text_ids' in locals():
            del text_ids
        
        # Run GC multiple times
        for _ in range(3):
            gc.collect()
        torch.cuda.empty_cache()
        
        # Additional aggressive cleanup to prevent fragmentation
        torch.cuda.synchronize()  # Wait for all CUDA operations to complete
        torch.cuda.reset_peak_memory_stats()  # Reset memory stats
        
        # Force another cache clear after sync
        torch.cuda.empty_cache()
        
        logger.info("Encoders unloaded.")
        logger.info(f"GPU memory allocated: {torch.cuda.memory_allocated() / 1024**3:.2f} GiB")
        logger.info(f"GPU memory reserved: {torch.cuda.memory_reserved() / 1024**3:.2f} GiB")
        
        # Check if we have enough free memory before loading transformer
        free_memory = (torch.cuda.get_device_properties(0).total_memory - torch.cuda.memory_allocated()) / 1024**3
        logger.info(f"Free GPU memory: {free_memory:.2f} GiB")
        if free_memory < 6.0:
            raise RuntimeError(f"Insufficient GPU memory to load transformer. Need at least 6 GiB, have {free_memory:.2f} GiB. Try restarting the bot to clear all memory.")
        
        # --- STEP 2: GENERATION ---
        logger.info("Step 2/2: Loading transformer...")
        
        # Load Transformer in 4-bit (7GB)
        transformer = FluxTransformer2DModel.from_pretrained(
            model_id,
            subfolder="transformer",
            quantization_config=quant_config,
            torch_dtype=torch.bfloat16,
            local_files_only=True,
            device_map={"": 0} # Force to GPU 0
        )
        
        logger.info(f"Transformer loaded. Device: {next(transformer.parameters()).device}")
        
        # Load Pipeline with Transformer only
        pipe_gen = FluxPipeline.from_pretrained(
            model_id,
            transformer=transformer,
            text_encoder=None,
            text_encoder_2=None,
            tokenizer=None,
            tokenizer_2=None,
            torch_dtype=torch.bfloat16,
            local_files_only=True
        )
        
        # Move pipeline to CUDA (this handles VAE and other components)
        # For quantized models, this is usually safe if the model is already on GPU
        logger.info("Moving pipeline to CUDA...")
        pipe_gen.to("cuda")
        
        logger.info(f"Pipeline moved. Transformer device: {next(transformer.parameters()).device}")
        
        # Enable CPU offload for VAE and other small parts
        # pipe_gen.enable_model_cpu_offload() <-- REMOVED: We manage lifecycle manually
        
        # Memory optimizations
        pipe_gen.enable_vae_slicing()
        pipe_gen.enable_vae_tiling()
        
        logger.info("Generating image...")
        image = pipe_gen(
            prompt_embeds=prompt_embeds.to("cuda"),
            pooled_prompt_embeds=pooled_prompt_embeds.to("cuda"),
            num_inference_steps=4,
            guidance_scale=0.0,
            max_sequence_length=256,
            output_type="pil"
        ).images[0]
        
        # Save to temp file
        temp_fd, temp_path = tempfile.mkstemp(suffix=".png")
        os.close(temp_fd)
        image.save(temp_path)
        logger.info(f"Image generated and saved to {temp_path}")
        return temp_path
        
    except torch.cuda.OutOfMemoryError as oom_err:
        logger.error(f"CUDA Out of Memory: {oom_err}")
        logger.error("="*60)
        logger.error("RECOVERY STEPS:")
        logger.error("1. Run: python clear_gpu_memory.py")
        logger.error("2. If that doesn't help, restart the bot to fully clear VRAM")
        logger.error("3. Ensure Ollama models are unloaded: curl http://localhost:11434/api/ps")
        logger.error("="*60)
        raise RuntimeError(f"GPU out of memory. {torch.cuda.memory_allocated() / 1024**3:.2f} GiB allocated. Please restart the bot.") from oom_err
        
    except Exception as e:
        logger.error(f"Error during image generation: {e}")
        raise
        
    finally:
        # Robust cleanup
        logger.info("Cleaning up resources...")
        
        # Delete large objects if they exist
        if 'pipe_enc' in locals() and pipe_enc is not None:
            del pipe_enc
        if 'text_encoder' in locals() and text_encoder is not None:
            del text_encoder
        if 'text_encoder_2' in locals() and text_encoder_2 is not None:
            del text_encoder_2
        if 'pipe_gen' in locals() and pipe_gen is not None:
            del pipe_gen
        if 'transformer' in locals() and transformer is not None:
            del transformer
        if 'prompt_embeds' in locals() and prompt_embeds is not None:
            del prompt_embeds
        if 'pooled_prompt_embeds' in locals() and pooled_prompt_embeds is not None:
            del pooled_prompt_embeds
        if 'text_ids' in locals() and text_ids is not None:
            del text_ids
        if 'image' in locals() and image is not None:
            del image
            
        # Force garbage collection
        for _ in range(3):
            gc.collect()
        torch.cuda.empty_cache()
        logger.info("Cleanup complete.")

async def generate_image(prompt: str):
    """
    Wraps image generation in asyncio.to_thread to avoid blocking the Discord heartbeat.
    Uses a lock to ensure only one generation runs at a time.
    """
    async with generation_lock:
        # Free up VRAM from Ollama first (async)
        await unload_ollama_models()
        return await asyncio.to_thread(_generate_image_sync, prompt)
