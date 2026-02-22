import asyncio
import time
import re
import hashlib
import uuid
from datetime import datetime
from typing import Optional, Any, List, Dict, Set

from utils.infrastructure.logging.kaia_logger import log_info, log_debug, log_warning, log_error, log_action, log_success
from utils.core.message_context import MessageContext
from utils.core.response_filter import HallucinationDetector, BotSpeakFilter
from utils.core.knowledge_boundary import KnowledgeBoundary
from utils.infrastructure.monitoring.async_task_registry import task_registry
from utils.core.kaia_intelligence import ContextWeaver

# Constants

# ── Observational Query Detection ──────────────────────────────────────
# Catches queries asking what Kaia has "seen", "observed", or "noticed"
# about other users in chat. These require grounded RAG data — if RAG is
# empty, the LLM must NOT fabricate fictional user interactions.
_OBSERVATIONAL_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"what have you (seen|observed|noticed|heard|watched|witnessed)",
        r"what('ve| have) (you |)(seen|observed|noticed|heard) .*(chat|users?|people|channel|server|today|tonight|lately|recently)",
        r"(any|what) (interesting )?(conversations?|interactions?|discussions?) .*(today|tonight|lately|recently|chat|channel)",
        r"what (are|were|have) (users?|people|everyone|they|others?) .*(saying|talking|discussing|asking|doing|up to|been talking|been discussing|been asking)",
        r"(who|has anyone) (has|have)? ?(been )?(talking|chatting|active|posting|around)",
        r"(tell me|report) .*(chat activity|user activity|what.* users)",
        r"what.* (users?|people|members?) .*(knowledge|know about|understanding of|grasp)",
    ]
]

def _is_observational_query(text: str) -> bool:
    """Detect queries that ask about observed user behaviour in chat."""
    for pat in _OBSERVATIONAL_PATTERNS:
        if pat.search(text):
            return True
    return False

class MessageProcessor:
    """
    Modular message processor that decomposes the complex on_message logic.
    """
    def __init__(self, ctx, response_optimizer, context_optimizer, relevance_feedback,
                 news_enhancer, rag_enhancer):
        self.ctx = ctx
        self.bot = ctx.bot
        self.ollama_client = ctx.ollama_client
        self.rag = ctx.rag
        self.config = ctx.config
        self.bot_state = ctx.bot_state
        self.performance_monitor = ctx.performance_monitor
        self.intent_parser = ctx.intent_parser
        self.stats_tracker = ctx.stats_tracker
        self.rate_limiter = ctx.rate_limiter
        self.shutdown_manager = ctx.shutdown_manager
        self.personalization_engine = ctx.personalization_engine
        
        self.response_optimizer = response_optimizer
        self.context_optimizer = context_optimizer
        self.relevance_feedback = relevance_feedback
        self.news_enhancer = news_enhancer
        self.rag_enhancer = rag_enhancer
        self.news_manager = ctx.news_manager
        self.dream_engine = ctx.dream_engine or getattr(ctx, 'dream_engine', None)
    
        # Internal components
        from utils.core.context_enricher import ContextEnricher
        self.context_enricher = ContextEnricher(self.bot)
        self.knowledge_boundary = KnowledgeBoundary(self.config.knowledge_base_dir)
        
        # Backpressure lock for background logging tasks
        self._bg_semaphore = asyncio.Semaphore(10)
        
        # Explicit verification
        if self.news_manager is None:
            log_warning("MessageProcessor initialized with news_manager=None")
        if self.dream_engine is None:
            log_warning("MessageProcessor initialized with dream_engine=None")
            
    # Helper to maintain compatibility with legacy run_rag pattern
    async def run_rag(self, fn, *args, **kwargs):
        from Kaiacord import run_rag as run_rag_func
        return await run_rag_func(fn, *args, **kwargs)

    async def process(self, msg):
        """Main entry point for message processing."""
        # 1. Preliminary Checks
        platform = getattr(msg, 'platform', 'discord')
        is_social = platform != 'discord' or platform == 'idle_reflection'
        
        if is_social:
            log_debug(f"Processing social message. Platform: {platform}, Author: {msg.author.name}")
            
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

        # 2. Boot Guard & Readiness Wait
        if not self.bot_state.boot_complete:
            if is_social:
                # For social media, we WAIT (up to 60s) for boot to complete 
                # instead of just ignoring, to handle race conditions gracefully.
                log_info(f"Social message from {msg.author.name} - waiting for boot...")
                for _ in range(60):
                    await asyncio.sleep(1.0)
                    if self.bot_state.boot_complete:
                        break
                
                if not self.bot_state.boot_complete:
                    log_warning(f"Social message from {msg.author.name} ignored: Bot still not ready after 60s.")
                    return
            else:
                log_info(f"Message from {msg.author.display_name} ignored - still booting")
                try:
                    await msg.channel.send("```\nstill waking up. give me a minute.\n```")
                except Exception: pass
                return

        # 3. Command Dispatching (Phase 3 Registry)
        from utils.commands.registry import dispatch_command
        from utils.social.kaia_social_responder import load_persona_async
        from utils.infrastructure.system.messaging import send_kaia_response
        
        # Note: on_message reference here might need care if we fully decompose
        if await dispatch_command(self.ctx, msg, load_persona_async, send_kaia_response):
            if is_social: log_debug("Social message handled by command dispatcher")
            return

        if is_social: log_debug("Social message passed command dispatch")

        # 4. Trigger Logic
        is_mention = "kaia" in msg.content.lower() or (not is_social and self.bot.user.mentioned_in(msg))
        if not is_mention and not is_social:
            return
            
        if is_social: log_debug(f"Social message triggger check passed (is_mention={is_mention})")

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
        
        # --- SOCIAL CONTEXT UNWRAPPING ---
        parent_text = None
        root_text = None
        main_content = enriched_raw
        
        # Check for root post context
        if "[ORIGINAL_POST]" in enriched_raw:
            try:
                parts = enriched_raw.split("[ORIGINAL_POST]")
                if len(parts) > 1:
                    # The next part could contain [REPLYING_TO]
                    root_part = parts[1].split("[REPLYING_TO]")[0].strip()
                    root_text = root_part
                    log_debug(f"Unwrapped original post context: {len(root_text)} chars")
            except Exception as e:
                log_warning(f"Failed to unwrap [ORIGINAL_POST] context: {e}")

        # Check for parent post context (the immediate reply target)
        if "[REPLYING_TO]" in enriched_raw:
            try:
                parts = enriched_raw.split("[REPLYING_TO]")
                if len(parts) > 1:
                    # The next part contains [USER_MESSAGE]
                    parent_part = parts[1].split("[USER_MESSAGE]")[0].strip()
                    parent_text = parent_part
                    log_debug(f"Unwrapped parent post context: {len(parent_text)} chars")
            except Exception as e:
                log_warning(f"Failed to unwrap [REPLYING_TO] context: {e}")

        # Final extraction of the main message
        if "[USER_MESSAGE]" in enriched_raw:
            main_content = enriched_raw.split("[USER_MESSAGE]")[-1].strip()
        # ---------------------------------
        
        sanitized_content = sanitize_prompt(main_content)
        
        ctx = MessageContext(
            message=msg,
            sanitized_content=sanitized_content,
            is_social=is_social,
            is_mention=is_mention,
            parent_context=parent_text,
            root_context=root_text,
            start_time=time.time()
        )

        self.bot_state.reset_quips()
        self.bot_state.update_interaction(msg.channel.id)
        
        # Direct metrics: count processed messages (replaces log-scraping)
        self.stats_tracker.increment_messages()


        # 7. Specific Command Handling
        from utils.commands.memory_handler import handle_memory_command
        if await handle_memory_command(msg, sanitized_content, self.run_rag, self.rag):
            return

        from utils.commands.profile_handler import handle_profile_query
        if await handle_profile_query(msg, sanitized_content, send_kaia_response, self.run_rag, self.rag):
            return

        # Proceed to intelligence pipeline in a tracked task
        # 8. Start intelligence pipeline
        start_time = time.perf_counter()
        gen_task = asyncio.create_task(self._run_intelligence_pipeline(ctx))
        task_registry.register(f"gen_{ctx.author_id}_{int(time.time()*1000)}", gen_task)
        
        try:
            await gen_task
            duration = time.perf_counter() - start_time
            log_action(f"TOTAL processing for {msg.author.name}: {duration:.2f}s")
        except asyncio.CancelledError:
            log_warning(f"Generation task for {msg.author.name} was cancelled (likely bot shutdown).")
        except Exception as e:
            import traceback
            log_error(f"Error in intelligence pipeline: {e}\n{traceback.format_exc()}")
            await self._send_response(msg.channel, "Something went wrong in my head. Try again?")

    async def _run_intelligence_pipeline(self, ctx: MessageContext):
        """Stage 2: Intelligence, Retrieval, and Response Generation."""
        # 1. Hallucination Detection
        h_start = time.perf_counter()
        if await self._check_hallucination(ctx):
            return
        h_dur = time.perf_counter() - h_start
        log_debug(f"METRIC: Hallucination check took {h_dur:.3f}s")

        # 2. Classification (Synchronous serial wait to prevent Ollama load spikes)
        c_start = time.perf_counter()
        self._perform_classification(ctx)
        await self._finalize_classification(ctx)
        c_dur = time.perf_counter() - c_start
        log_debug(f"METRIC: Classification took {c_dur:.3f}s")

        # 3. Cache Check
        if await self._check_cache(ctx):
            return

        # 4. Retrieval & Response Generation (Stage 3)
        async with ctx.message.channel.typing():
            r_start = time.perf_counter()
            await self._retrieve_and_generate(ctx)
            r_dur = time.perf_counter() - r_start
            log_debug(f"METRIC: Retrieval/Generation took {r_dur:.3f}s")

    async def _check_hallucination(self, ctx: MessageContext) -> bool:
        """Check if query contains hallucinations."""
        # 1. Respect Feature Flag
        if not self.config.get('features.hallucination_detection', True):
            return False
            
        # 2. Skip for Owners/Admins (They are allowed to discuss architecture)
        if self.config.is_owner(ctx.message.author.name, ctx.author_name, ctx.author_id):
            return False

        if HallucinationDetector.contains_hallucination(ctx.sanitized_content):
            log_warning(f"Hallucination detected in query from {ctx.author_name}. Blocking.")
            log_debug(f"[HALLUCINATION_DEBUG] Content: '{ctx.sanitized_content}'")
            await ctx.message.channel.send("```\nnot following. try that again.\n```")
            return True
        return False

    async def _perform_classification(self, ctx: MessageContext):
        """Classify the query using fast-path and prepare full-path task."""
        # 1. Fast Path
        fast_intent = self.intent_parser.fast_parse(ctx.sanitized_content)
        
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
        
        ctx.classification_task = asyncio.create_task(self.intent_parser.parse_intent(ctx.sanitized_content, context_obj))
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
                join_timeout = getattr(self.config, 'classification_join_seconds', 15.0)
                
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

        # 1. REDUNDANCY BYPASS: Skip RAG for simple greetings and commands
        # This saves ~4-6 seconds of latency for simple interactions.
        if ctx.intent and ctx.intent.confidence >= 0.9 and ctx.intent.suggested_strategy in ["SOCIAL_GREETING", "COMMAND_EXECUTION"]:
            from utils.social.kaia_social_responder import load_persona_async
            log_info(f"Adaptive Skip: Bypassing RAG for high-confidence {ctx.intent.suggested_strategy}")
            
            # Populate minimum context needed for generation
            ctx.system_prompt = await load_persona_async()
            ctx.context_nodes = []
            
            # Proceed straight to generation
            await self._generate_response_stage(ctx)
            return

        # 2. Setup Retrieval Tasks (Named dictionary to prevent IndexError)
        tasks_dict, ask_whats_new, is_news_query, clean_query = await self._setup_retrieval_tasks(ctx)
        
        # 3. Wait for Retrieval
        log_action(f"Waiting for parallel tasks: {list(tasks_dict.keys())}")
        t_start = time.perf_counter()
        
        # Resolve names to results
        task_names = list(tasks_dict.keys())
        task_objects = list(tasks_dict.values())
        rag_gather_timeout = self.config.rag_retrieval_timeout * 2  
        try:
            raw_results = await asyncio.wait_for(asyncio.gather(*task_objects), timeout=rag_gather_timeout)
        except asyncio.TimeoutError:
            log_warning(f"Top-level RAG retrieval timed out ({rag_gather_timeout}s). Cancelling pending tasks.")
            raw_results = []
            for t in task_objects:
                if t.done() and not t.cancelled():
                    try:
                        raw_results.append(t.result())
                    except Exception:
                        raw_results.append([])
                else:
                    t.cancel()
                    raw_results.append([])
        
        t_dur = time.perf_counter() - t_start
        log_debug(f"METRIC: All parallel retrieval tasks took {t_dur:.3f}s")
        
        # Re-map results back to a dict
        results = dict(zip(task_names, raw_results))
        
        self.performance_monitor.stop_timer('retrieval', 'retrieval_time')
        
        # 4. Process Results & Diversify
        await self._process_retrieval_results(ctx, results, ask_whats_new, is_news_query, clean_query)

        # 6. Knowledge Boundary Check (Entity Verification)
        # Cache history in context early to avoid redundant list conversions
        ctx.history = list(self.bot_state.channel_memory.get(ctx.channel_id, []))
        
        from utils.core.rag_utils import get_node_text
        # Avoid massive join for boundary check - KnowledgeBoundary should handle list of strings
        rag_snippets = [get_node_text(n) for n in ctx.context_nodes] if ctx.context_nodes else []
        
        # Extract snippets safely whether history contains strings or dicts
        history_snippets = []
        for m in ctx.history[-5:]:
            if isinstance(m, dict) and 'content' in m:
                history_snippets.append(m['content'])
            elif isinstance(m, str):
                history_snippets.append(m)
                
        context_list = rag_snippets + history_snippets
        
        # Whitelist current author and bot
        whitelist = {ctx.author_name, self.bot.user.name, "Kaia"}
        # Resolve display name variants
        if hasattr(ctx.message.author, 'display_name'):
            whitelist.add(ctx.message.author.display_name)
            
        boundary_check = self.knowledge_boundary.check_known_entities(ctx.sanitized_content, context_list, whitelist=whitelist)
        ctx.knowledge_boundary_check = boundary_check
        
        if not boundary_check["all_known"]:
            log_msg = f"Knowledge Boundary: Detected unknown entities: {boundary_check['unknown_in_context']}"
            # Only escalate to warning for multi-word entities (likely real proper nouns)
            if any(len(e.split()) > 1 for e in boundary_check['unknown_in_context']):
                log_warning(log_msg)
            else:
                log_debug(log_msg)

        # 7. Generate Response (Stage 4)
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

        # Perform RAG retrieval (Adaptive skip handled upstream in _retrieve_and_generate)
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

        # News triggers - Strict list to avoid false positives on small talk (e.g. "what's new")
        news_inquiry_triggers = ["any updates", "latest news", "current events", "headlines"]
        ask_whats_new = any(trigger in ctx.sanitized_content.lower() for trigger in news_inquiry_triggers)
        
        from utils.core.response_filter import EmergencyContaminationFilter
        from utils.news.kaia_news import NewsRetrievalEnhancer, RAGEnhancer
        
        freshness_keywords = ['news', 'latest', 'update', 'happening', 'today', 'current', 'recent', 'yesterday', 'tonight']
        is_news_query = self.config.news_auto_trigger and (
            (ctx.category == 'news' and any(word in clean_query.lower() for word in freshness_keywords)) or 
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
        o_start = time.perf_counter()
        history = list(self.bot_state.channel_memory.get(ctx.channel_id, []))
        optimized = self.context_optimizer.optimize_context(
            category=ctx.category,
            persona=ctx.system_prompt,
            rag_nodes=ctx.context_nodes,
            history=history,
            strategy=ctx.intent.suggested_strategy if ctx.intent else None
        )
        o_dur = time.perf_counter() - o_start
        log_debug(f"METRIC: Context optimization took {o_dur:.3f}s")

        # 2. Build Messages
        messages = self._construct_messages(ctx, optimized)
        
        # 3. LLM Generation
        g_start = time.perf_counter()
        ctx.response_text = await self._call_ollama_with_retries(ctx, messages)
        
        # 4. Final Processing & Logging
        await self._post_process_and_log(ctx)

    def _construct_messages(self, ctx: MessageContext, optimized: Dict[str, str]) -> List[Dict[str, str]]:
        """Build the system, RAG, history, and user messages."""
        system_prompt = optimized['persona']
        context_str = optimized['rag']
        history_str = optimized['history']
        
        # Core Unification: Persona + RAG + History
        # Note: All tone, skepticism, and behavioral constraints MUST be in kaia_persona.md
        rag_block = (
            f"### DATA RETRIEVAL FOR: {ctx.author_name}\n"
            f"{context_str or 'No specific historical records found.'}\n"
            "---"
        ) if context_str else f"### CURRENT_USER: {ctx.author_name}\nNo records found."

        # Grounding Enforcement: If RAG is empty for sensitive categories, add a strict reminder
        grounding_categories = {"identity", "social_identity", "self", "whoami", "entity"}
        is_observational = _is_observational_query(ctx.sanitized_content)
        needs_grounding = ctx.category in grounding_categories or is_observational

        if not context_str and needs_grounding:
            if is_observational:
                rag_block += (
                    "\n\nCRITICAL: You have NO chat logs or records of user interactions to draw from right now. "
                    "Do NOT invent users, conversations, observations, or anecdotes about what people said or did. "
                    "If asked what you've observed or noticed in chat, say you haven't been tracking that closely, "
                    "your memory's blank on it, or you don't have anything specific. Stay honest."
                )
            else:
                rag_block += "\n\nCRITICAL: No specific records found for this person or topic. Do not invent details, threads, or interactions. If you don't know, stay grounded and admit the records are hazy or missing."

        current_time_str = datetime.now().strftime("%A, %B %d, %Y | %I:%M %p")

        full_system_prompt = (
            f"{system_prompt}\n\n"
            f"[CURRENT_TIME] {current_time_str}\n\n"
            f"{rag_block}"
        )

        if ctx.parent_context:
            label = "[REPLYING_TO_CONTEXT]"
            if ctx.root_context == ctx.parent_context:
                label = "[THREAD_ROOT_AND_PARENT]"
            clipped_parent = ctx.parent_context[:1000] + ("..." if len(ctx.parent_context) > 1000 else "")
            full_system_prompt += f"\n\n{label}\n{clipped_parent}"
            
        if ctx.root_context and ctx.root_context != ctx.parent_context:
            clipped_root = ctx.root_context[:1000] + ("..." if len(ctx.root_context) > 1000 else "")
            full_system_prompt += f"\n\n[THREAD_START]\nThis conversation originated from:\n{clipped_root}"
        messages = [
            {"role": "system", "content": full_system_prompt}
        ]
        
        if optimized.get('history'):
            messages.append({"role": "system", "content": optimized['history']})
        
        # Latest History (Already cached in ctx.history if retrieval ran)
        history = ctx.history if ctx.history else list(self.bot_state.channel_memory.get(ctx.channel_id, []))
        
        # Filter for most recent 12 turns (optimized from deque copy)
        for m in history[-12:]:
            if isinstance(m, dict) and 'role' in m and 'content' in m:
                if messages and messages[-1]["role"] == m["role"] and m["role"] != "system":
                    messages[-1]["content"] += f"\n\n{m['content']}"
                else:
                    messages.append(m.copy())
            else:
                # Handle raw string literal format safely
                text_content = str(m)
                
                # Try to infer role roughly for correct concatenation
                inferred_role = "user"
                if "kaia:" in text_content.lower() or "assistant:" in text_content.lower():
                    inferred_role = "assistant"
                    
                if messages and messages[-1]["role"] == inferred_role:
                    messages[-1]["content"] += f"\n\n{text_content}"
                else:
                    messages.append({"role": inferred_role, "content": text_content})
        
        messages.append({"role": "user", "content": ctx.sanitized_content})
        
        return messages

    async def _call_ollama_with_retries(self, ctx: MessageContext, messages: List[Dict[str, str]]) -> str:
        """Execute the self-healing generation loop."""
        from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager
        from utils.infrastructure.system.self_healing import SelfHealingSystem
        from utils.core.response_filter import EmergencyContaminationFilter
        
        gpu_manager = OllamaGPUManager(self.config.chat_model)
        options = gpu_manager.get_gpu_options(for_chat=True, num_ctx=self.config.max_context_tokens)
        
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
                
                # Use run_with_gpu_guard for the main chat generation
                from utils.infrastructure.gpu.gpu_manager import gpu_memory_manager, GPUTaskPriority
                
                response = await gpu_memory_manager.run_with_gpu_guard(
                    model_name=self.config.chat_model,
                    priority=GPUTaskPriority.CHAT,
                    coro=asyncio.wait_for(
                        SelfHealingSystem.call_with_fallback(
                            self.ollama_client.chat,
                            model=self.config.chat_model,
                            messages=messages,
                            options=current_options
                        ),
                        timeout=self.config.llm_request_seconds
                    ),
                    task_id=f"chat_{uuid.uuid4().hex[:8]}"
                )
                
                content = response['message']['content']
                
                # Robust stripping of LLM-added outer codeblocks to avoid double-wrapping in Discord
                content = content.strip()
                while content.startswith("```") and content.endswith("```"):
                    content = content[3:-3].strip()
                    # Strip potential language identifier from the first line (e.g., 'markdown' or 'json')
                    if "\n" in content:
                        first_line = content.split('\n')[0].strip()
                        if first_line and not any(c.isspace() for c in first_line) and len(first_line) < 20:
                            content = '\n'.join(content.split('\n')[1:]).strip()
                    else:
                        # Handle cases like ```message``` without newlines
                        pass
                
                # Cleanup
                should_detect = self.config.get('features.hallucination_detection', True)
                if should_detect and not self.config.is_owner(ctx.message.author.name, ctx.author_name, ctx.author_id):
                    content = HallucinationDetector.clean_response(content)
                    
                if not content:
                    log_warning(f"Attempt {attempt + 1} failed: Hallucination detected (Empty after clean).")
                    continue

                if not self.config.is_owner(ctx.message.author.name, ctx.author_name, ctx.author_id):
                    content = EmergencyContaminationFilter.filter_response(content)
                    
                if not content:
                    log_warning(f"Attempt {attempt + 1} failed: Veracity violation (Fiction/Contamination detected).")
                    continue
                
                # Style Hardening (Silent Stripping)
                # Re-enabled for everyone as bait-y questions break the illusion
                content = BotSpeakFilter.strip_bot_speak(content)
                
                if content and content.strip():
                    return content
                else:
                    log_warning(f"Attempt {attempt + 1} failed: Result empty after filtering.")
                    continue
            except Exception as e:
                log_error(f"Attempt {attempt + 1} failed: {e}")
                
        return "The data's a bit scrambled right now. Ask me again later."

    async def _post_process_and_log(self, ctx: MessageContext):
        """Final cleanups, sending response, and logging."""
        if not ctx.response_text:
            return
        
        # 1. SEND RESPONSE
        await self._send_response(channel=ctx.message.channel, text=ctx.response_text)
        
        # 2. LOGGING & STATE (background to avoid holding up the UI)
        # 3. Background Tasks with Backpressure
        # Create the task and let it manage its own semaphore lifecycle
        bg_task = asyncio.create_task(self._background_logging_and_memory(ctx))
        task_registry.register(f"bg_log_{uuid.uuid4().hex[:6]}", bg_task)

    async def _background_logging_and_memory(self, ctx: MessageContext):
        """Perform slow updates in the background to avoid holding up the UI."""
        # Use semaphore to limit concurrent background tasks
        async with self._bg_semaphore:
            try:
                # Update memory
                if ctx.channel_id not in self.bot_state.channel_memory:
                     from collections import deque
                     self.bot_state.channel_memory[ctx.channel_id] = deque(maxlen=self.config.max_memory_messages)
                
                # Add author prefix to user message for history disambiguation
                user_msg_with_author = f"{ctx.author_name}: {ctx.sanitized_content}"
                self.bot_state.channel_memory[ctx.channel_id].append({"role": "user", "content": user_msg_with_author})
                self.bot_state.channel_memory[ctx.channel_id].append({"role": "assistant", "content": ctx.response_text})
                
                # Update personalization and relevance feedback
                await self.personalization_engine.learn_from_interaction(ctx.author_id, ctx.sanitized_content, ctx.response_text)
                await self.relevance_feedback.log_interaction(ctx.sanitized_content, ctx.response_text, ctx.author_id, ctx.author_name)
                
                # Log for RAG
                # CRITICAL FIX: Use sanitized_content to avoid poisoning RAG with [REPLYING_TO] tags
                await self.rag.log_user_interaction_async(ctx.author_id, ctx.author_name, ctx.sanitized_content, ctx.response_text)
                
                self.performance_monitor.stop_timer('total', 'response_time')
                
                # Direct metrics
                response_time = time.time() - ctx.start_time
                self.stats_tracker.record_response_time(response_time)
                
            except Exception as e:
                log_error(f"Error in background logging: {e}")

    async def _send_response(self, channel, text: str):
        """Helper to send response via messaging utility."""
        from utils.infrastructure.system.messaging import send_kaia_response
        
        # FINAL SAFETY: Strip any extra backticks that might cause double-wrapping
        # if they slipped through the generation loop pre-processing.
        clean_text = text.strip()
        while clean_text.startswith("```") and clean_text.endswith("```"):
            clean_text = clean_text[3:-3].strip()
            # Handle language tags
            if "\n" in clean_text:
                first_line = clean_text.split('\n')[0].strip()
                if first_line and not any(c.isspace() for c in first_line) and len(first_line) < 20:
                    clean_text = '\n'.join(clean_text.split('\n')[1:]).strip()
        
        await send_kaia_response(channel, clean_text)
