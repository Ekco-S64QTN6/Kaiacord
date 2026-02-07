import asyncio
import time
import re
import hashlib
from datetime import datetime
from typing import Optional, Any, List, Dict

from utils.infrastructure.logging.kaia_logger import log_info, log_debug, log_warning, log_error, log_action, log_success
from utils.core.message_context import MessageContext
from utils.core.response_filter import HallucinationDetector
from utils.core.background_tasks import run_news_update # If needed, or just import logic

# Constants (Could be moved to config later)

class MessageProcessor:
    """
    Modular message processor that decomposes the complex on_message logic.
    """
    def __init__(self, bot, ollama_client, run_rag, rag, config, bot_state, 
                 performance_monitor, intent_parser, 
                 response_optimizer, context_optimizer, relevance_feedback,
                 personalization_engine, stats_tracker, rate_limiter,
                 shutdown_manager, news_enhancer, rag_enhancer,
                 news_manager, dream_engine):
        self.bot = bot
        self.ollama_client = ollama_client
        self.run_rag = run_rag
        self.rag = rag
        self.config = config
        self.bot_state = bot_state
        self.performance_monitor = performance_monitor
        self.intent_parser = intent_parser
        self.response_optimizer = response_optimizer
        self.context_optimizer = context_optimizer
        self.relevance_feedback = relevance_feedback
        self.personalization_engine = personalization_engine
        self.stats_tracker = stats_tracker
        self.rate_limiter = rate_limiter
        self.shutdown_manager = shutdown_manager
        self.news_enhancer = news_enhancer
        self.rag_enhancer = rag_enhancer
        self.news_manager = news_manager
        self.dream_engine = dream_engine
        
        # Internal components
        from utils.core.context_enricher import ContextEnricher
        self.context_enricher = ContextEnricher(self.bot)
        
        # Explicit verification
        if self.news_manager is None:
            log_warning("MessageProcessor initialized with news_manager=None")
        if self.dream_engine is None:
            log_warning("MessageProcessor initialized with dream_engine=None")

    async def process(self, msg):
        """Main entry point for message processing."""
        # 1. Preliminary Checks
        is_social = getattr(msg, 'platform', 'discord') != 'discord'
        if not is_social and msg.author == self.bot.user:
            return

        author_name = str(msg.author).lower()
        author_id = str(msg.author.id)
        if any(ignored.lower() in [author_name, author_id] for ignored in self.config.ignored_users):
            log_info(f"Silently ignoring message from ignored user: {author_name} ({author_id})")
            return

        if not is_social and msg.guild is not None:
            channel_name = msg.channel.name.lower()
            if channel_name in self.config.blacklisted_channels:
                return
            whitelisted = self.config.whitelisted_channels
            if whitelisted and channel_name not in whitelisted:
                return

        # 2. Boot Guard
        if not self.bot_state.boot_complete:
            if not is_social:
                log_info(f"Message from {msg.author.display_name} ignored - still booting")
                try:
                    await msg.channel.send("```\nstill waking up. give me a minute.\n```")
                except:
                    pass
            return

        # 3. Command Dispatching (Phase 3 Registry)
        from utils.commands.registry import dispatch_command
        from utils.social.kaia_social_responder import load_persona_async
        from utils.infrastructure.system.messaging import send_kaia_response
        
        # Note: on_message reference here might need care if we fully decompose
        if await dispatch_command(msg, self.bot, self.ollama_client, self.run_rag, self.rag, 
                                 self.news_manager, self.dream_engine, self.bot_state, 
                                 self.config, load_persona_async, 
                                 self.bot.on_message, send_kaia_response):
            return

        # 4. Trigger Logic
        is_mention = "kaia" in msg.content.lower() or (not is_social and self.bot.user.mentioned_in(msg))
        if not is_mention and not is_social:
            return

        # 5. Rate Limiting & Shutdown Guard
        if not self.rate_limiter.is_allowed(msg.author.id):
            log_warning(f"Rate limit hit for user {msg.author.name}")
            return

        if self.shutdown_manager.shutting_down:
            return

        # 6. Initialize Context & Update State
        from utils.core.sanitizer import sanitize_prompt
        
        # Enriched Context: Extract embed text and resolve links
        enriched_raw = await self.context_enricher.enrich_content(msg)
        sanitized_content = sanitize_prompt(enriched_raw)
        
        ctx = MessageContext(
            message=msg,
            sanitized_content=sanitized_content,
            is_social=is_social,
            is_mention=is_mention,
            start_time=time.time()
        )

        self.bot_state.reset_quips()
        self.bot_state.update_interaction(msg.channel.id)

        from utils.infrastructure.monitoring.async_task_registry import task_registry
        
        # 7. Specific Command Handling
        from utils.commands.memory_handler import handle_memory_command
        if await handle_memory_command(msg, sanitized_content, self.run_rag, self.rag):
            return

        from utils.commands.profile_handler import handle_profile_query
        if await handle_profile_query(msg, sanitized_content, send_kaia_response, self.run_rag, self.rag):
            return

        # Proceed to intelligence pipeline in a tracked task
        # 8. Start intelligence pipeline
        gen_task = asyncio.create_task(self._run_intelligence_pipeline(ctx))
        task_registry.register(f"gen_{ctx.author_id}_{int(time.time()*1000)}", gen_task)
        
        try:
            await gen_task
        except asyncio.CancelledError:
            log_warning(f"Generation task for {msg.author.name} was cancelled (likely bot shutdown).")
        except Exception as e:
            log_error(f"Error in intelligence pipeline: {e}")
            await self._send_response(msg.channel, "Something went wrong in my head. Try again?")

    async def _run_intelligence_pipeline(self, ctx: MessageContext):
        """Stage 2: Intelligence, Retrieval, and Response Generation."""
        # 1. Hallucination Detection
        if await self._check_hallucination(ctx):
            return

        # 2. Classification
        await self._perform_classification(ctx)

        # 3. Cache Check
        if await self._check_cache(ctx):
            return

        # 4. Retrieval & Response Generation (Stage 3)
        async with ctx.message.channel.typing():
            await self._retrieve_and_generate(ctx)

    async def _check_hallucination(self, ctx: MessageContext) -> bool:
        """Check if query contains hallucinations."""
        if HallucinationDetector.contains_hallucination(ctx.sanitized_content):
            log_warning(f"Hallucination detected in query from {ctx.author_name}. Blocking.")
            await ctx.message.channel.send("```\nnot following. try that again.\n```")
            return True
        return False

    async def _perform_classification(self, ctx: MessageContext):
        """Classify the query using fast-path and prepare full-path task."""
        # 1. Fast Path
        fast_intent = self.intent_parser.fast_parse(ctx.message.content)
        
        if fast_intent:
            ctx.intent = fast_intent
            ctx.category = self._derive_legacy_category(fast_intent)
            log_info(f"Fast-path intent: {fast_intent.suggested_strategy} ({ctx.category})")
            
            # If high confidence command/greeting, we might skip full analysis
            if fast_intent.confidence > 0.9 and fast_intent.suggested_strategy in ["SOCIAL_GREETING", "COMMAND_EXECUTION"]:
                return

        # 2. Start Logic Analysis (Layer 2)
        # Deduplication check
        task_name = f"intent_{ctx.author_id}_{hash(ctx.message.content)}"
        from utils.infrastructure.monitoring.async_task_registry import task_registry
        
        all_tasks = task_registry.get_all_tasks()
        if task_name in all_tasks and not all_tasks[task_name].done():
            log_debug(f"Intent analysis already in progress for {ctx.author_name}, reusing task.")
            ctx.classification_task = all_tasks[task_name]
            return

        # Start full analysis
        # We need to construct ContextCtx here if we want context-aware intent
        from utils.core.kaia_intelligence import ContextWeaver
        
        # Use ContextWeaver to build rich context from memory
        channel_mem = list(self.bot_state.channel_memory.get(ctx.channel_id, []))
        context_obj = ContextWeaver.weave(channel_mem)
        
        ctx.classification_task = asyncio.create_task(self.intent_parser.parse_intent(ctx.message.content, context_obj))
        task_registry.register(task_name, ctx.classification_task)

    def _derive_legacy_category(self, intent) -> str:
        """Map new strategies to old categories for backward compatibility."""
        strategy = intent.suggested_strategy
        if strategy == "SOCIAL_GREETING": return "greeting"
        if strategy == "COMMAND_EXECUTION": return "command"
        if strategy == "RELATIONAL_MIRROR": return "social_identity"
        if strategy == "SYNTHESIS_SCAN": return "news"
        if strategy == "DIAGNOSTIC_DEEP_DIVE": return "tech"
        if strategy == "DREAM_RECALL": return "dream"
        if strategy == "ASSOCIATIVE_WANDERING": return "dream"  # Fallback for creative variant
        if strategy == "CREATIVE_ASSOCIATION": return "general" 
        if strategy == "PRECISE_RECALL": return "identity" 
        if strategy == "EXPLORATORY_DIALOGUE": return "general"
        return "general"

    async def _check_cache(self, ctx: MessageContext):
        """DECOMMISSIONED: Semantic cache removed per user request."""
        return None

    async def _finalize_classification(self, ctx: MessageContext):
        """Await the parallel intent task and update context."""
        if hasattr(ctx, 'classification_task') and ctx.classification_task:
            try:
                # Use config value for timeout
                join_timeout = getattr(self.config, 'classification_join_seconds', 5.0)
                
                new_intent = await asyncio.wait_for(ctx.classification_task, timeout=join_timeout)
                if new_intent:
                    ctx.intent = new_intent
                    ctx.category = self._derive_legacy_category(new_intent)
                    log_info(f"Full intent analysis: {new_intent.suggested_strategy} ({ctx.category})")
            except asyncio.TimeoutError:
                log_warning("Intent analysis timed out. Using fast-path result.")
            except Exception as e:
                log_error(f"Intent analysis failed: {e}")

    async def _retrieve_and_generate(self, ctx: MessageContext):
        """Stage 3: Retrieval, Context Optimization, and Ollama Generation."""

        # 2. Setup Retrieval Tasks (Named dictionary to prevent IndexError)
        tasks_dict, ask_whats_new, is_news_query, clean_query = await self._setup_retrieval_tasks(ctx)
        
        # 3. Wait for Retrieval
        log_action(f"Waiting for parallel tasks: {list(tasks_dict.keys())}")
        self.performance_monitor.start_timer('retrieval')
        
        # Resolve names to results
        task_names = list(tasks_dict.keys())
        task_objects = list(tasks_dict.values())
        raw_results = await asyncio.gather(*task_objects)
        
        # Re-map results back to a dict
        results = dict(zip(task_names, raw_results))
        
        self.performance_monitor.stop_timer('retrieval', 'retrieval_time')
        
        # 4. Process Results & Diversify
        await self._process_retrieval_results(ctx, results, ask_whats_new, is_news_query, clean_query)

        # 5. Final Classification Sync
        await self._finalize_classification(ctx)

        # 6. Generate Response (Stage 4)
        await self._generate_response_stage(ctx)

    async def _setup_retrieval_tasks(self, ctx: MessageContext):
        """Prepare all parallel tasks for retrieval."""
        from utils.social.kaia_social_responder import load_persona_async
        
        # Determine query details
        clean_query = ctx.sanitized_content.lower().replace("kaia", "").strip("?,. ")
        display_name = ctx.message.author.display_name.strip(".")
        
        target_user_id = ctx.author_id
        target_user_name = ctx.message.author.display_name
        
        if not clean_query or clean_query in ["who am i", "what am i"]:
            clean_query = f"Who is {display_name}?"
        elif clean_query in ["who are you", "what are you", "who is kaia"]:
            clean_query = "Who is Kaia?"
            target_user_id = self.bot.user.id
            target_user_name = self.bot.user.name

        # Tasks dictionary (Prevents IndexErrors)
        tasks = {}
        tasks['persona'] = asyncio.create_task(load_persona_async())
        tasks['traits'] = asyncio.create_task(self.personalization_engine.get_user_traits(ctx.author_id))

        # Always perform RAG (Skip logic removed for stability)
        tasks['rag'] = asyncio.create_task(self.run_rag(
            self.rag.retrieve, 
            clean_query, 
            user_id=target_user_id, 
            user_name=target_user_name, 
            top_k=self.config.rag_top_k,
            strict_identity=(ctx.category in ["identity", "self", "whoami", "entity"]),
            include_news=False,
            category=ctx.category,
            intent=ctx.intent
        ))

        # News triggers
        news_inquiry_triggers = ["what's new", "what's up", "any updates", "whats new", "whats up"]
        ask_whats_new = any(trigger in ctx.sanitized_content.lower() for trigger in news_inquiry_triggers)
        
        from utils.core.response_filter import EmergencyContaminationFilter
        from utils.news.kaia_news import NewsRetrievalEnhancer, RAGEnhancer
        
        is_news_query = self.config.news_auto_trigger and (
            (ctx.category == 'news') or 
            any(word in clean_query.lower() for word in ['news', 'latest', 'update', 'happening', 'today']) or 
            ask_whats_new
        )

        if is_news_query:
            log_info("Detected news query - activating enhanced news retrieval")
            enhanced_query = self.news_enhancer.enhance_news_query(clean_query, ctx.author_id)
            rag_params = self.rag_enhancer.prepare_news_query(enhanced_query)
            
            # Use 'rag_news' for distinct tracking if needed, but 'rag' is the primary context
            tasks['rag_news'] = asyncio.create_task(self.run_rag(
                self.rag.retrieve, 
                rag_params['query'], 
                top_k=rag_params['params']['similarity_top_k']
            ))
            
        if ask_whats_new:
            news_expansions = EmergencyContaminationFilter.expand_news_query(clean_query)
            for i, expansion in enumerate(news_expansions):
                tasks[f'news_extra_{i}'] = asyncio.create_task(self.run_rag(self.rag.retrieve, expansion, top_k=2))

        return tasks, ask_whats_new, is_news_query, clean_query

    async def _process_retrieval_results(self, ctx: MessageContext, results: dict, ask_whats_new, is_news_query, clean_query):
        """Handle RAG results, persona adaptation, and news diversification."""
        ctx.system_prompt = results.get('persona', "")
        ctx.raw_nodes = results.get('rag', [])
        
        # Merge news results if they were run separately
        if 'rag_news' in results and results['rag_news']:
            ctx.raw_nodes.extend(results['rag_news'])
            
        ctx.user_traits = results.get('traits', {})
        
        # Adaptation
        ctx.system_prompt = self.personalization_engine.adapt_prompt(ctx.system_prompt, ctx.user_traits)
        now = datetime.now()
        ctx.system_prompt += f"\n\nToday is {now.strftime('%A, %B %d, %Y %I:%M %p')}."

        # Diversification
        if is_news_query:
            log_info(f"Applying news diversification to {ctx.category} query results")
            news_nodes = []
            other_nodes = []
            for node in ctx.raw_nodes:
                metadata = node.get('metadata', {}) if isinstance(node, dict) else getattr(node, 'metadata', {})
                if metadata.get('source_type') in ['news', 'news_brief', 'news_summary'] or "news" in (metadata.get('file_path', '') or '').lower():
                    news_nodes.append(node)
                else:
                    other_nodes.append(node)
            
            deduplicated_news = self.rag_enhancer.deduplicate_results(news_nodes)
            news_items = []
            for node in deduplicated_news:
                content = node.get('content', str(node)) if isinstance(node, dict) else (node.text if hasattr(node, 'text') else str(node))
                metadata = node.get('metadata', {}) if isinstance(node, dict) else getattr(node, 'metadata', {})
                item_id = hashlib.md5(content[:200].encode()).hexdigest()[:8]
                news_items.append({'content': content, 'metadata': metadata, 'id': item_id})
            
            diversified_items = self.news_enhancer.diversify_news_results(news_items, ctx.author_id)
            self.news_enhancer.track_mentioned_news([i['id'] for i in diversified_items], ctx.author_id)
            
            ctx.context_nodes = [node.text if hasattr(node, 'text') else str(node) for node in other_nodes]
            ctx.context_nodes.extend([item['content'] for item in diversified_items])
        else:
            ctx.context_nodes = ctx.raw_nodes

        # Append legacy expansions if any (news_extra_0, news_extra_1, etc)
        for key, res in results.items():
            if key.startswith('news_extra_') and res:
                for node in res:
                    text = node.text if hasattr(node, 'text') else str(node)
                    if text and text not in ctx.context_nodes:
                        ctx.context_nodes.append(text)

    async def _generate_response_stage(self, ctx: MessageContext):
        """Stage 4: Context Optimization and Multi-pass Generation."""
        # 1. Context Optimization
        optimized = self.context_optimizer.optimize_context(
            ctx.category, 
            ctx.system_prompt, 
            ctx.context_nodes, 
            list(self.bot_state.channel_memory.get(ctx.channel_id, []))
        )
        
        # 2. Build Message List
        messages = self._construct_messages(ctx, optimized)
        
        # 3. Generation Loop (Self-Healing)
        ctx.response_text = await self._call_ollama_with_retries(ctx, messages)
        
        # 4. Final Processing & Logging
        await self._post_process_and_log(ctx)

    def _construct_messages(self, ctx: MessageContext, optimized: Dict[str, str]) -> List[Dict[str, str]]:
        """Build the system, RAG, history, and user messages."""
        system_prompt = optimized['persona']
        context_str = optimized['rag']
        history_str = optimized['history']
        
        rag_block = (
            f"### DATA RETRIEVAL FOR: {ctx.author_name}\n"
            f"{context_str or 'No specific historical records found.'}\n"
            "---"
        ) if context_str else f"### CURRENT_USER: {ctx.author_name}\nNo records found."

        # Core Unification: Persona + RAG + History + Reinforcement
        # This keeps the model anchored to the persona while keeping rules top-of-memory.
        reinforcement = self._get_reinforcement_prompt(ctx.is_social)
        
        full_system_prompt = (
            f"{system_prompt}\n\n"
            f"{rag_block}\n\n"
            f"{reinforcement}"
            "\n\n### CRITICAL PERSONA ADHERENCE\n"
            "Do NOT engage in 'meta-talk'. Never mention technical internal systems like 'RAG', 'classifier', 'context fragments', or 'retrieval thresholds' to the user. "
            "Talk like a grounded person. If you can't recall something, just say you can't put your finger on it or it's a bit hazy."
        )

        messages = [
            {"role": "system", "content": full_system_prompt}
        ]
        
        # Add channel memory
        history = list(self.bot_state.channel_memory.get(ctx.channel_id, []))
        for m in history:
            if messages[-1]["role"] == m["role"] and m["role"] != "system":
                messages[-1]["content"] += f"\n\n{m['content']}"
            else:
                messages.append(m.copy())
        
        messages.append({"role": "user", "content": ctx.sanitized_content})
        
        return messages

    def _get_reinforcement_prompt(self, is_social: bool) -> str:
        """Get the specific reinforcement rules for the persona."""
        rules = (
            "### REINFORCEMENT RULES\n"
            "1. Speak in lowercase. Be blunt, direct, and slightly cynical.\n"
            "2. NO markdown formatting. NO meta-talk about being an AI.\n"
            "3. NATURAL GROUNDING: Refer to your reading history or conversations naturally. ONLY mention your environment (neon signs, coffee) if it fits the mood, NOT as a suffix.\n"
            "4. NO AI ASSISTANT SPEAK: You are Kaia. Do not say 'I am here to help' or 'I am a technical assistant'.\n"
            "5. NO ROLEPLAY: Do not describe actions in asterisks or parentheses (e.g., *sighs*, (types slowly)). Only type the spoken response.\n"
            "6. NO FORMULAIC BAIT: Avoid ending every response with generic questions like 'what do you think?' or 'what's on your mind?'. If it doesn't fit the flow, don't ask it.\n"
            "7. NATURAL CURIOSITY: You can ask questions to keep the vibe real, but stay in persona. Don't interrogate; just be humanly curious if the situation warrants it. State your piece first.\n"
        )
        if is_social:
            rules += "8. SOCIAL BREVITY: Under 280 chars.\n9. NO formulaic greetings.\n"
        return rules

    async def _call_ollama_with_retries(self, ctx: MessageContext, messages: List[Dict[str, str]]) -> str:
        """Execute the self-healing generation loop."""
        from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager
        from utils.infrastructure.system.self_healing import SelfHealingSystem
        from utils.core.response_filter import EmergencyContaminationFilter
        
        gpu_manager = OllamaGPUManager(self.config.chat_model)
        options = gpu_manager.get_gpu_options(for_chat=True, num_ctx=self.config.max_context_tokens or 28000)
        
        max_attempts = self.config.generation_max_retry_attempts
        base_temp = self.config.generation_base_temperature
        temp_scaling = self.config.generation_temperature_scaling
        
        for attempt in range(max_attempts):
            # Scaled parameters on retry
            current_options = options.copy()
            if attempt > 0:
                current_options['temperature'] = base_temp + (temp_scaling * attempt)
            
            try:
                log_action(f"Calling ollama.chat (Attempt {attempt + 1}/{max_attempts})...")
                response = await SelfHealingSystem.call_with_fallback(
                    self.ollama_client.chat,
                    model=self.config.chat_model,
                    messages=messages,
                    options=current_options
                )
                
                content = response['message']['content']
                
                # Cleanup
                content = HallucinationDetector.clean_response(content)
                content = EmergencyContaminationFilter.filter_response(content)
                
                # Style Hardening (Programmatic enforcement of persona rules)
                from utils.core.response_filter import ResponseStyleHarden
                content = ResponseStyleHarden.strip_trailing_questions(content)
                
                if content and content.strip():
                    return content
            except Exception as e:
                log_error(f"Attempt {attempt + 1} failed: {e}")
                
        return "The data's a bit scrambled right now. Ask me again later."

    async def _post_process_and_log(self, ctx: MessageContext):
        """Final cleanups, sending response, and logging."""
        if not ctx.response_text:
            return
            
        # 1. SEND RESPONSE (This should be the very first thing we do to minimize delay)
        # We do this while still potentially in the typing context.
        await self._send_response(ctx.message.channel, ctx.response_text)
        
        # 2. LOGGING & STATE (Move slow tasks here)
        # The typing context will exit as soon as this function returns to _generate_response_stage
        # and _generate_response_stage returns. 
        # Register in task_registry so we can await/cancel it on shutdown.
        from utils.infrastructure.monitoring.async_task_registry import task_registry
        bg_task = asyncio.create_task(self._background_logging_and_memory(ctx))
        task_registry.register(f"bg_log_{ctx.author_id}_{int(time.time())}", bg_task)

    async def _background_logging_and_memory(self, ctx: MessageContext):
        """Perform slow updates in the background to avoid holding up the UI."""
        try:
            # Update memory
            if ctx.channel_id not in self.bot_state.channel_memory:
                 from collections import deque
                 self.bot_state.channel_memory[ctx.channel_id] = deque(maxlen=self.config.max_memory_messages)
            
            self.bot_state.channel_memory[ctx.channel_id].append({"role": "user", "content": ctx.sanitized_content})
            self.bot_state.channel_memory[ctx.channel_id].append({"role": "assistant", "content": ctx.response_text})
            
            # Log for RAG
            await self.run_rag(self.rag.log_user_interaction, ctx.author_id, ctx.author_name, ctx.message.content, ctx.response_text)
            
            self.performance_monitor.stop_timer('total', 'response_time')
        except Exception as e:
            log_error(f"Error in background logging: {e}")

    async def _send_response(self, channel, text: str):
        """Helper to send response via messaging utility."""
        from utils.infrastructure.system.messaging import send_kaia_response
        await send_kaia_response(channel, text)

