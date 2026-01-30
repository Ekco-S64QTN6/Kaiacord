import asyncio
import logging
import aiohttp
import tempfile
import os
import time
import ollama
from pathlib import Path
from PIL import Image
from typing import Optional
from utils.kaia_logger import *
from utils.unified_logging import log_ollama_interaction

# Vision model configuration
VISION_MODEL = "llama3.2-vision:11b"

# Image optimization settings
MAX_VISION_SIZE = 1024  # Max dimension for vision processing
JPEG_QUALITY = 85  # Quality for JPEG conversion

# Create async Ollama client
ollama_client = ollama.AsyncClient()

# Global session for connection pooling
_session = None

async def get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession()
    return _session


async def cleanup_session():
    """Cleanup the aiohttp session. Call this on bot shutdown."""
    global _session
    if _session and not _session.closed:
        await _session.close()
        _session = None


async def download_image(url: str) -> str:
    """
    Download an image from a URL to a temporary file.
    Returns the path to the downloaded file.
    """
    temp_path: Optional[str] = None
    try:
        log_action(f"Downloading image...")
        log_file(url)
        
        session = await get_session()
        async with session.get(url) as response:
            if response.status != 200:
                raise Exception(f"Failed to download image: HTTP {response.status}")
                
            # Get the file extension from the URL or content-type
            content_type = response.headers.get('content-type', '')
            if 'png' in content_type:
                ext = '.png'
            elif 'jpeg' in content_type or 'jpg' in content_type:
                ext = '.jpg'
            elif 'gif' in content_type:
                ext = '.gif'
            elif 'webp' in content_type:
                ext = '.webp'
            else:
                ext = '.png'  # default
            
            # Create temporary file
            temp_fd, temp_path = tempfile.mkstemp(suffix=ext)
            os.close(temp_fd)
            
            # Write image data
            with open(temp_path, 'wb') as f:
                f.write(await response.read())
            
            log_success(f"Image downloaded")
            log_file(temp_path)
            return temp_path
                
    except Exception as e:
        # Clean up temp file on error
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        log_error(f"Error downloading image: {e}")
        raise

def optimize_image_for_vision(image_path: str) -> tuple[str, dict]:
    """
    Optimize an image for vision model processing.
    Resizes large images and converts to JPEG for faster processing.
    
    Args:
        image_path: Path to the original image
        
    Returns:
        Tuple of (optimized_path, stats_dict)
    """
    stats = {
        'original_size': os.path.getsize(image_path),
        'original_dimensions': None,
        'optimized_dimensions': None,
        'was_resized': False,
        'optimized_size': None
    }
    
    try:
        with Image.open(image_path) as img:
            original_width, original_height = img.size
            stats['original_dimensions'] = (original_width, original_height)
            
            # Check if resize needed
            needs_resize = original_width > MAX_VISION_SIZE or original_height > MAX_VISION_SIZE
            
            if needs_resize:
                # Calculate new dimensions maintaining aspect ratio
                if original_width > original_height:
                    new_width = MAX_VISION_SIZE
                    new_height = int(original_height * (MAX_VISION_SIZE / original_width))
                else:
                    new_height = MAX_VISION_SIZE
                    new_width = int(original_width * (MAX_VISION_SIZE / original_height))
                
                log_action(f"Resizing image: {original_width}x{original_height} -> {new_width}x{new_height}")
                
                # Resize with high-quality resampling
                img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                stats['optimized_dimensions'] = (new_width, new_height)
                stats['was_resized'] = True
            else:
                img_resized = img
                stats['optimized_dimensions'] = (original_width, original_height)
            
            # Convert to RGB if necessary (for JPEG compatibility)
            if img_resized.mode in ('RGBA', 'P', 'LA'):
                img_resized = img_resized.convert('RGB')
            
            # Save as optimized JPEG
            temp_fd, optimized_path = tempfile.mkstemp(suffix='.jpg')
            os.close(temp_fd)
            
            img_resized.save(optimized_path, 'JPEG', quality=JPEG_QUALITY, optimize=True)
            stats['optimized_size'] = os.path.getsize(optimized_path)
            
            reduction = ((stats['original_size'] - stats['optimized_size']) / stats['original_size']) * 100
            log_success(f"Image optimized: {stats['original_size']//1024}KB -> {stats['optimized_size']//1024}KB ({reduction:.1f}% reduction)")
            
            return optimized_path, stats
            
    except Exception as e:
        log_error(f"Image optimization failed: {e}, using original")
        return image_path, stats


async def analyze_image(image_path: str, prompt: Optional[str] = None) -> str:
    """
    Analyze an image using Ollama's vision model.
    
    Args:
        image_path: Path to the image file
        prompt: Optional custom prompt. If None, uses a default description prompt.
    
    Returns:
        The model's analysis of the image
    """
    optimized_path = None
    try:
        log_action("Processing vision task...")
        log_file(image_path)
        
        # OPTIMIZE IMAGE FIRST - This dramatically speeds up processing
        optimized_path, stats = optimize_image_for_vision(image_path)
        if stats['was_resized']:
            log_info(f"Using optimized image: {stats['optimized_dimensions']}")
        
        # Default prompt if none provided
        if not prompt:
            prompt = (
                "Describe what you see in this image. "
                "Be specific about objects, people, actions, setting, and any text visible. "
                "Keep it concise but informative."
            )
        
        # Read optimized image as bytes
        with open(optimized_path, 'rb') as f:
            image_data = f.read()
        
        # Use GPU Manager for consistent options
        from utils.gpu_manager import OllamaGPUManager
        gpu_manager = OllamaGPUManager(VISION_MODEL)
        gpu_options = gpu_manager.get_gpu_options(for_chat=False)
        
        # TIERED TIMEOUT STRATEGY: Generous timeouts for slow GPU model loading
        # First request loads the model from disk (can take 1-2 minutes on slow GPU)
        # Subsequent requests are much faster
        timeouts = [120.0, 150.0, 180.0]  # 2min, 2.5min, 3min
        last_error = None
        
        for attempt, timeout in enumerate(timeouts, 1):
            log_action(f"Vision analysis attempt {attempt}/{len(timeouts)} (timeout: {timeout}s)...")
            start_time = time.time()
            try:
                response = await asyncio.wait_for(
                    ollama_client.chat(
                        model=VISION_MODEL,
                        messages=[
                            {
                                'role': 'user',
                                'content': prompt,
                                'images': [image_data]
                            }
                        ],
                        options=gpu_options
                    ),
                    timeout=timeout
                )
                end_time = time.time()
                log_success(f"Vision analysis completed in {end_time - start_time:.2f}s")
                
                # Log interaction
                log_ollama_interaction(prompt, response['message']['content'])
                
                analysis = response['message']['content'].strip()
                log_response("Got response:", analysis[:100] + "..." if len(analysis) > 100 else analysis)
                return analysis
                
            except asyncio.TimeoutError:
                elapsed = time.time() - start_time
                log_error(f"Vision attempt {attempt} TIMED OUT after {elapsed:.2f}s")
                last_error = asyncio.TimeoutError(f"Timed out after {elapsed:.2f}s")
                if attempt < len(timeouts):
                    log_action("Retrying with longer timeout...")
                continue
            except Exception as e:
                error_msg = str(e)
                elapsed = time.time() - start_time
                
                # Check for "server loading model" error - this means Ollama is busy loading
                if "llm server loading model" in error_msg.lower() or "status code: 500" in error_msg.lower():
                    log_warning(f"Vision attempt {attempt} - Ollama is loading model, waiting 5s before retry...")
                    await asyncio.sleep(5)  # Give Ollama time to finish loading
                    if attempt < len(timeouts):
                        continue  # Retry instead of failing
                
                log_error(f"Vision attempt {attempt} FAILED after {elapsed:.2f}s: {e}")
                last_error = e
                break  # Don't retry on other non-timeout errors
        
        # All attempts failed
        raise last_error or Exception("Vision analysis failed")
        
    except Exception as e:
        log_error(f"Error analyzing image: {e}")
        raise
    finally:
        # Clean up optimized temp file if different from original
        if optimized_path and optimized_path != image_path and os.path.exists(optimized_path):
            try:
                os.remove(optimized_path)
            except Exception:
                pass


async def process_discord_image(image_url: str, user_prompt: Optional[str] = None) -> tuple[str, Optional[str]]:
    """
    Download and analyze an image from Discord.
    
    Args:
        image_url: Discord CDN URL of the image
        user_prompt: Optional user prompt for the analysis
    
    Returns:
        Tuple of (analysis_text, temp_file_path)
        The temp file path should be cleaned up by the caller
    """
    temp_path: Optional[str] = None
    try:
        # Download the image
        temp_path = await download_image(image_url)
        
        # Analyze it
        analysis = await analyze_image(temp_path, user_prompt)
        
        return analysis, temp_path
        
    except Exception as e:
        # Clean up temp file on error
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
        raise


async def unload_ollama_models():
    """Unload the vision model from Ollama to free VRAM"""
    try:
        # Sending a request with keep_alive=0 unloads the model
        # Use a minimal message instead of empty list
        await ollama_client.chat(
            model=VISION_MODEL, 
            messages=[{'role': 'user', 'content': 'unload'}], 
            keep_alive=0
        )
    except Exception:
        pass


async def kaia_sees_image(image_url: str, user_message: str = "") -> str:
    """
    Kaia's vision handler that returns her commentary on an image.
    This integrates with her persona to provide blunt, grounded observations.
    """
    # Import here to avoid circular dependency
    from utils.kaia_image import generation_lock
    
    # VRAM Lock is now managed by the caller (Kaiacord.py)
    # to ensure chat model is unloaded first.

    temp_path = None
    try:
        # Download and analyze
        temp_path = await download_image(image_url)
        
        # Build prompt based on user's message
        if user_message and any(word in user_message.lower() for word in ['describe', 'what', 'see', 'look', 'interpret', 'meaning']):
            # User is asking about the image
            prompt = (
                "You are Kaia. Describe what you see in this image. "
                "Be blunt, grounded, and use lowercase. No fluff. "
                "Focus on: objects, people, actions, setting, text, and anything notable."
            )
        else:
            # User just uploaded an image, give a brief comment
            prompt = (
                "You are Kaia. Give a brief, blunt observation about this image. "
                "1-2 sentences. Use lowercase. Be direct and grounded. "
                "Comment on what's interesting or notable."
            )
        
        # Get analysis from vision model
        # We've updated the prompt to be more Kaia-like directly to avoid a second rephrasing step
        analysis = await analyze_image(temp_path, prompt)
        return analysis
        
    except Exception as e:
        log_error(f"Error in kaia_sees_image: {e}")
        raise
        
    finally:
        # Clean up temp file
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
            log_success(f"Cleaned up temp file")
        
        # CRITICAL: Unload vision model from Ollama to free VRAM
        try:
            log_action("Unloading vision model...")
            await unload_ollama_models()
            # Wait to ensure VRAM is fully released (increased from 1s to 3s)
            # This prevents race conditions where chat model loads before vision VRAM is freed
            await asyncio.sleep(3)
            log_success("Vision model unloaded successfully.")
        except Exception as unload_err:
            log_error(f"Failed to unload vision model: {unload_err}")


# Test function for debugging
async def test_vision():
    """Test the vision system with a sample image"""
    print("Testing vision system...")
    print(f"Model: {VISION_MODEL}")
    
    # You can test with a local image or URL
    # analysis = await analyze_image("/path/to/test/image.jpg")
    # print(f"Analysis: {analysis}")
    

if __name__ == "__main__":
    asyncio.run(test_vision())
