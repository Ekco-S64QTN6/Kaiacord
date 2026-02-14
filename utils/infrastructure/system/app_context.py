import asyncio
from dataclasses import dataclass, field
from typing import Optional, Any
import ollama
import discord
from discord.ext import commands

@dataclass
class AppContext:
    """
    Central application context to replace module-level globals.
    Provides explicit dependency passing for better testability and stability.
    """
    bot: commands.Bot = None
    config: Any = None
    bot_state: Any = None
    ollama_client: Optional[ollama.AsyncClient] = None
    
    # Core Components
    rag: Any = None
    dream_engine: Any = None
    performance_monitor: Any = None
    model_warm_pool: Any = None
    intent_parser: Any = None
    persistent_state_manager: Any = None
    
    # Utilities
    stats_tracker: Any = None
    stats_poller: Any = None
    rate_limiter: Any = None
    shutdown_manager: Any = None
    clear_gpu_memory: Any = None
    
    # Logic Layers
    message_processor: Any = None
    news_manager: Any = None
    personalization_engine: Any = None
    news_enhancer: Any = None
    rag_enhancer: Any = None
    
    # Synchronization
    logic_layer_ready: asyncio.Event = field(default_factory=asyncio.Event)
    
    def set_ready(self):
        """Signal that the logic layer is initialized."""
        self.logic_layer_ready.set()
    
    async def wait_until_ready(self, timeout: float = 30.0):
        """Wait for the logic layer to be ready."""
        await asyncio.wait_for(self.logic_layer_ready.wait(), timeout=timeout)

    async def close(self):
        """Clean up resources."""
        if self.ollama_client:
            try:
                await self.ollama_client.close()
            except Exception:
                pass
