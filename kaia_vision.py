import asyncio
import logging
import aiohttp
import tempfile
import os
import ollama
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kaia_vision")

# Vision model configuration
VISION_MODEL = "llama3.2-vision:11b"

# Create async Ollama client
ollama_client = ollama.AsyncClient()

# Global session for connection pooling
_session = None

async def get_session():
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession()
    return _session


async def download_image(url: str) -> str:
    """
    Download an image from a URL to a temporary file.
    Returns the path to the downloaded file.
    """
    try:
        logger.info(f"Downloading image from: {url}")
        
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
            
            logger.info(f"Image downloaded to: {temp_path}")
            return temp_path
                
    except Exception as e:
        logger.error(f"Error downloading image: {e}")
        raise


async def analyze_image(image_path: str, prompt: str = None) -> str:
    """
    Analyze an image using Ollama's vision model.
    
    Args:
        image_path: Path to the image file
        prompt: Optional custom prompt. If None, uses a default description prompt.
    
    Returns:
        The model's analysis of the image
    """
    try:
        logger.info(f"Analyzing image: {image_path}")
        
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
        logger.info(f"Vision analysis complete: {analysis[:100]}...")
        return analysis
        
    except Exception as e:
        logger.error(f"Error analyzing image: {e}")
        raise


async def process_discord_image(image_url: str, user_prompt: str = None) -> tuple[str, str]:
    """
    Download and analyze an image from Discord.
    
    Args:
        image_url: Discord CDN URL of the image
        user_prompt: Optional user prompt for the analysis
    
    Returns:
        Tuple of (analysis_text, temp_file_path)
        The temp file path should be cleaned up by the caller
    """
    temp_path = None
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


async def kaia_sees_image(image_url: str, user_message: str = "", system_prompt: str = "") -> str:
    """
    Kaia's vision handler that returns her commentary on an image.
    This integrates with her persona to provide blunt, grounded observations.
    
    Args:
        image_url: Discord CDN URL of the image
        user_message: The user's message accompanying the image
        system_prompt: The bot's persona/system instructions
    
    Returns:
        Kaia's commentary on the image
    """
    temp_path = None
    try:
        # Download and analyze
        temp_path = await download_image(image_url)
        
        # Build prompt based on user's message
        if user_message and any(word in user_message.lower() for word in ['describe', 'what', 'see', 'look', 'interpret', 'meaning']):
            # User is asking about the image
            prompt = (
                "Describe what you see in this image. "
                "Be direct and specific. No fluff. "
                "Focus on: objects, people, actions, setting, text, and anything notable."
            )
        else:
            # User just uploaded an image, give a brief comment
            prompt = (
                "Give a brief, blunt observation about this image. "
                "1-2 sentences. Be direct and grounded. "
                "Comment on what's interesting or notable."
            )
        
        # Get raw analysis from vision model
        analysis = await analyze_image(temp_path, prompt)
        
        # Now, use the persona to "filter" or "rephrase" the analysis if a system prompt is provided
        if system_prompt:
            logger.info("Rephrasing vision analysis with persona...")
            messages = [
                {"role": "system", "content": system_prompt + "\n\nYou are Kaia. You just looked at an image and got this technical description of it. Rephrase it in your own blunt, grounded, lowercase style. Don't be an assistant. Just say what you see based on this data."},
                {"role": "user", "content": f"Technical description of the image: {analysis}\n\nUser's original message: {user_message}"}
            ]
            
            # Use the main model (Gemma 3) for rephrasing
            # We'll use a slightly lower temperature for consistency
            response = await ollama_client.chat(
                model="gemma3:12b",
                messages=messages,
                options={
                    "temperature": 0.4,
                    "num_predict": 512,
                }
            )
            content = response['message']['content'].strip()
            return content
        
        return analysis
        
    except Exception as e:
        logger.error(f"Error in kaia_sees_image: {e}")
        return f"can't process that image. {str(e)[:50]}"
        
    finally:
        # Clean up temp file
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
            logger.info(f"Cleaned up {temp_path}")


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
