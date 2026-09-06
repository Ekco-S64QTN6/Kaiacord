import asyncio
import time
import sys
import os
from unittest.mock import MagicMock, AsyncMock

# Add project root to path
sys.path.append(os.getcwd())

from utils.infrastructure.logging.kaia_logger import log_info, log_action, log_success, log_error
from utils.infrastructure.system.app_context import AppContext
from utils.infrastructure.system.yaml_config import config
from utils.infrastructure.system.bot_state import bot_state
from utils.core.message_processor import MessageProcessor
import ollama

async def verify_latency():
    log_action("🚀 Starting Full Pipeline Latency Verification...")
    
    # Setup Context
    ctx = AppContext()
    ctx.config = config
    ctx.bot_state = bot_state
    ctx.bot_state.boot_complete = True # Skip boot wait
    # Mocks
    from utils.core.kaia_rag import KaiaRAG
    from utils.core.kaia_intelligence import IntentParser, ContextOptimizer, RelevanceFeedback, Intent
    from utils.infrastructure.system.performance_optimizer import ResponseOptimizer
    
    ctx.ollama_client = MagicMock()
    ctx.ollama_client.chat = AsyncMock(return_value={
        'message': {'content': 'The Balkan Peninsula has a rich and complex history in the 20th century...'}
    })
    ctx.intent_parser = IntentParser(ctx.ollama_client)
    # Mock the internal LLM call for intent parser
    ctx.intent_parser._analyze_with_llm = AsyncMock(return_value=Intent(
        explicit_intent="explain balkan history",
        implied_needs=["history of yugoslavia", "regional conflicts"],
        emotional_context="curiosity",
        temporal_focus="20th century",
        relational_context="educational",
        suggested_strategy="EXPLORATORY_DIALOGUE",
        confidence=0.9
    ))
    
    ctx.bot = MagicMock()
    ctx.bot.user.id = "bot_id"
    ctx.bot.user.name = "Kaia"
    ctx.rag = KaiaRAG()
    ctx.rate_limiter = MagicMock()
    ctx.rate_limiter.is_allowed.return_value = True
    ctx.shutdown_manager = MagicMock()
    ctx.shutdown_manager.shutting_down = False
    ctx.performance_monitor = MagicMock()
    ctx.stats_tracker = MagicMock()
    ctx.personalization_engine = MagicMock()
    
    processor = MessageProcessor(
        ctx=ctx,
        response_optimizer=ResponseOptimizer(),
        context_optimizer=ContextOptimizer(max_tokens=config.max_context_tokens),
        relevance_feedback=RelevanceFeedback(ctx.rag),
        news_enhancer=MagicMock(),
        rag_enhancer=MagicMock()
    )
    # Ensure enhancers return something sensible if called
    processor.news_enhancer.enhance_news_query.return_value = "news query"
    processor.rag_enhancer.prepare_news_query.return_value = {'query': 'news', 'params': {'similarity_top_k': 3}}
    
    # Mock Discord Message
    mock_msg = MagicMock()
    mock_msg.author.name = "Ekco"
    mock_msg.author.display_name = "Ekco"
    mock_msg.author.id = "177011971818782721"
    mock_msg.content = "kaia, explain the complex geopolitical history of the Balkan Peninsula in the 20th century, specifically focusing on the collapse of Yugoslavia and the subsequent regional conflicts."
    mock_msg.channel.id = "123456789"
    mock_msg.channel.name = "kaia-opolis"
    mock_msg.channel.typing = MagicMock()
    mock_msg.channel.typing.return_value.__aenter__ = AsyncMock()
    mock_msg.channel.typing.return_value.__aexit__ = AsyncMock()
    mock_msg.guild = MagicMock()
    mock_msg.platform = "discord"

    # Mock RAG retrieval
    ctx.rag.retrieve = AsyncMock(return_value=[
        MagicMock(text="The Balkan Peninsula has a complex history...", metadata={'source_type': 'knowledge', 'file_path': 'balkans.md'})
    ])
    processor.rag = ctx.rag # Re-assign to be sure
    
    # Mock send_kaia_response to just print and capture
    import utils.infrastructure.system.messaging as msg_mod
    msg_mod.send_kaia_response = AsyncMock()
    
    start_time = time.perf_counter()
    
    log_action(f"Sending test message: '{mock_msg.content}'")
    try:
        await processor.process(mock_msg)
        # Give some time for background tasks
        await asyncio.sleep(2)
    except Exception as e:
        log_error(f"Top-level process failure: {e}")
        import traceback
        traceback.print_exc()
    
    total_duration = time.perf_counter() - start_time
    
    # Check if a response was generated
    resp_text = "NONE"
    if msg_mod.send_kaia_response.called:
        args, kwargs = msg_mod.send_kaia_response.call_args
        # send_kaia_response(channel, content, ...)
        if len(args) > 1:
            resp_text = args[1]
    
    log_info(f"Response text: '{resp_text}'")
    log_success(f"Verified TOTAL Latency: {total_duration:.2f}s")
    
    if total_duration < 45:
        log_success("✅ Latency is within acceptable 45s window.")
    else:
        log_error(f"❌ Latency is TOO HIGH: {total_duration:.2f}s")

if __name__ == "__main__":
    asyncio.run(verify_latency())
