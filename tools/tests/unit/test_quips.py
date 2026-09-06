import os
import sys
import asyncio
import tempfile
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))


# Inject dummy env vars to bypass config validation
os.environ["DISCORD_TOKEN"] = "mock_token"
os.environ["BLUESKY_HANDLE"] = "mock_handle"
os.environ["BLUESKY_PASSWORD"] = "mock_password"
os.environ["X_USERNAME"] = "mock_user"
os.environ["X_PASSWORD"] = "mock_pass"
os.environ["X_EMAIL"] = "mock_email"

from utils.core.kaia_rag import KaiaRAG
from utils.infrastructure.logging.kaia_logger import log_info, log_success, log_error
from utils.social.kaia_social_responder import generate_quip, load_persona
from utils.infrastructure.system.bot_state import bot_state
from utils.infrastructure.system.yaml_config import config
import pytest
import os
import ollama

if os.environ.get("KAIACORD_TEST_MODE") == "1":
    pytest.skip("Skipping Ollama test in CI", allow_module_level=True)

# Smoke-test transcript. Kept out of memory/ so a failed or interrupted run
# cannot leave test artifacts in the production memory directory.
SMOKE_LOG_PATH = os.path.join(
    tempfile.gettempdir(), "kaiacord_quip_smoke_test.log"
)


async def run_smoke_test():
    log_info("Starting Quip Smoke Test...")
    
    # 1. Initialize RAG
    rag = KaiaRAG()
    
    # 2. Mock Bot and Ollama
    ollama_client = ollama.AsyncClient()
    
    class MockChannel:
        def __init__(self):
            self.name = "smoke-test-channel"
            self.id = 123
        async def send(self, content):
            # Print to console and log file
            clean_content = content.replace("```\n", "").replace("\n```", "")
            char_count = len(clean_content)
            print(f"[DISCORD] ({char_count} chars) {content}")
            with open(SMOKE_LOG_PATH, "a") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - ({char_count} chars) {content}\n")

    class MockGuild:
        def __init__(self):
            self.text_channels = [MockChannel()]
            self.me = type('obj', (object,), {'id': 123})()
        def permissions_for(self, member):
            return type('obj', (object,), {'send_messages': True})()

    class MockBot:
        def __init__(self):
            self.guilds = [MockGuild()]
        def get_channel(self, id):
            return MockChannel()

    bot = MockBot()
    bot_state.last_active_channel_id = 123 # Force mock channel
    
    # Clear previous log
    if os.path.exists(SMOKE_LOG_PATH):
        os.remove(SMOKE_LOG_PATH)

    log_info("Generating 10 quips...")
    
    async def run_rag_helper(fn, *args, **kwargs):
        # Override limit to get more variety if possible
        if fn.__name__ == 'get_recent_highlights':
            kwargs['limit'] = 10
        res = fn(*args, **kwargs)
        if fn.__name__ == 'get_recent_highlights':
            print(f"[DEBUG] Highlights retrieved: {res}")
        return res

    class MockCtx:
        def __init__(self):
            self.bot = bot
            self.ollama_client = ollama_client
            self.rag = rag
            self.bot_state = bot_state
            self.config = config
    
    ctx = MockCtx()

    for i in range(1, 11):
        log_info(f"Generating quip #{i}...")
        print(f"[DEBUG] Recent quips in history: {bot_state.get_recent_quips()}")
        # The new signature is generate_quip(ctx, is_manual=False, target_channel=None, on_message_func=None)
        await generate_quip(ctx, is_manual=True)
        # Small delay to prevent Ollama overload
        await asyncio.sleep(1)

    log_success(f"Smoke test complete. Check {SMOKE_LOG_PATH}")

if __name__ == "__main__":
    asyncio.run(run_smoke_test())
