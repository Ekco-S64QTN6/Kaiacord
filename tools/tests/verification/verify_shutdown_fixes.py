import asyncio
import sys
import os
from unittest.mock import MagicMock, AsyncMock

# Add project root to path
sys.path.append(os.getcwd())

# Mock dependencies that might fail during import or execution in a test environment
sys.modules['discord'] = MagicMock()
sys.modules['discord.ext'] = MagicMock()
sys.modules['ollama'] = MagicMock()
sys.modules['psutil'] = MagicMock()
sys.modules['watchdog'] = MagicMock()
sys.modules['watchdog.observers'] = MagicMock()
sys.modules['watchdog.events'] = MagicMock()

async def test_shutdown_checks():
    print("Testing shutdown checks...")
    from utils.shutdown_fixed import shutdown_manager
    from Kaiacord import prewarm_main_model
    
    # Set shutting_down to True
    shutdown_manager.shutting_down = True
    
    # This should return immediately without error
    await prewarm_main_model()
    print("✅ prewarm_main_model returned immediately during shutdown.")

async def test_vision_timeout():
    print("\nTesting vision timeout...")
    from utils.kaia_vision import analyze_image
    import utils.kaia_vision
    
    # Mock ollama_client.chat to hang
    async def hanging_chat(*args, **kwargs):
        await asyncio.sleep(60)
    utils.kaia_vision.ollama_client.chat = AsyncMock(side_effect=hanging_chat)
    
    # Create a dummy image file
    with open("test_image.jpg", "w") as f:
        f.write("dummy data")
    
    try:
        await analyze_image("test_image.jpg")
        print("❌ Vision task did not time out!")
    except asyncio.TimeoutError:
        print("✅ Vision task timed out as expected.")
    except Exception as e:
        print(f"❌ Vision task failed with unexpected error: {e}")
    finally:
        if os.path.exists("test_image.jpg"):
            os.remove("test_image.jpg")

async def main():
    await test_shutdown_checks()
    await test_vision_timeout()

if __name__ == "__main__":
    asyncio.run(main())
