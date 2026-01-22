import asyncio
import logging
import aiohttp
import tempfile
import os
import ollama
from pathlib import Path
from kaia_logger import *

# Vision model configuration
VISION_MODEL = "llama3.2-vision:11b"

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


async def analyze_image(image_path: str, prompt: Optional[str] = None) -> str:
    """
    Analyze an image using Ollama's vision model.
    
    Args:
        image_path: Path to the image file
        prompt: Optional custom prompt. If None, uses a default description prompt.
    
    Returns:
        The model's analysis of the image
    """
    try:
        log_action("Processing vision task...")
        log_file(image_path)
        
        # Default prompt if none provided
        if not prompt:
            prompt = (
                "Describe what you see in this image. "
                "Be specific about objects, people, actions, setting, and any text visible. "
                "Keep it concise but informative."
            )
        
        # Read image as bytes
        with open(image_path, 'rb') as f:
            image_data = f.read()
        
        # Call Ollama vision API
        response = await ollama_client.chat(
            model=VISION_MODEL,
            messages=[
                {
                    'role': 'user',
                    'content': prompt,
                    'images': [image_data]
                }
            ],
            options={
                "temperature": 0.7,
                "num_predict": 512,
            }
        )
        
        analysis = response['message']['content'].strip()
        log_response("Got response:", analysis[:100] + "..." if len(analysis) > 100 else analysis)
        return analysis
        
    except Exception as e:
        log_error(f"Error analyzing image: {e}")
        raise


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


async def kaia_sees_image(image_url: str, user_message: str = "") -> str:
    """
    Kaia's vision handler that returns her commentary on an image.
    This integrates with her persona to provide blunt, grounded observations.
    """
    # Import here to avoid circular dependency
    from kaia_image import generation_lock, unload_ollama_models
    
    # CHECK: Is Kaia currently busy generating an image?
    if generation_lock.locked():
        return "busy rendering something else. ask me later."

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
            # Wait to ensure VRAM is fully released
            await asyncio.sleep(1)
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
