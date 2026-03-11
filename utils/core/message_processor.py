import asyncio
import time
import re
import hashlib
import uuid
import aiohttp
import base64
from datetime import datetime
from typing import Optional, Any, List, Dict, Set

from utils.infrastructure.logging.kaia_logger import log_info, log_debug, log_warning, log_error, log_action, log_success
from utils.core.message_context import MessageContext
from utils.core.response_filter import HallucinationDetector, BotSpeakFilter
from utils.core.knowledge_boundary import KnowledgeBoundary
from utils.core.rag_executor import run_rag_retrieval
from utils.infrastructure.monitoring.async_task_registry import task_registry
from utils.core.kaia_intelligence import ContextWeaver
from utils.social.kaia_social_responder import load_persona_async
from utils.commands.memory_handler import handle_memory_command
from utils.commands.profile_handler import handle_profile_query
from utils.commands.registry import dispatch_command
from utils.infrastructure.system.messaging import send_kaia_response
from utils.core.sanitizer import sanitize_prompt

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
        r"summarize\s+(all\s+)?(user\s+)?(interactions?|conversations?|chat|activity|messages?)\s+(over|in|for|from)?\s*(the\s+)?(past|last)\s+\d+\s*(hour|day|minute|week)",
        r"(what|show|tell me)\s+(happened|was said|went on|occurred)\s+(over|in|during|for)?\s*(the\s+)?(past|last)\s+\d+\s*(hour|day|minute|week)",
        r"(recap|summary|overview)\s+(of\s+)?(today'?s?|recent|the\s+last|past)\s+(chat|interactions?|activity|conversations?)",
    ]
]

# Pre-compiled regex for hot-path sanitization
_JSON_RESPONSE_PATTERN = re.compile(r'^\s*\{.*"response"\s*:', re.DOTALL)
_JSON_WRAPPER_PATTERN = re.compile(r'^\s*\{[\s\S]*"response"\s*:\s*"([\s\S]*)"\s*\}\s*$', re.MULTILINE)

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
        self.dream_engine = ctx.dream_engine
    
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
        return await run_rag_retrieval(fn, *args, **kwargs)

    async def process(self, msg):
        """Main entry point for message processing."""
        # 1. Preliminary Checks
        platform = getattr(msg, 'platform', 'discord')
        is_social = platform != 'discord'
        
        if is_social:
            author_name = getattr(msg.author, 'name', 'Unknown User')
            log_debug(f"Processing social message. Platform: {platform}, Author: {author_name}")
            
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

        # Update engagement: Kaia was just talked to
        try:
            if self.bot_state:
                self.bot_state.update_kaia_state(engagement_delta=0.05)
        except Exception:
            pass

        # 6. Initialize Context & Update State
        
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
        if await handle_memory_command(msg, sanitized_content, self.run_rag, self.rag):
            return

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
            author_name = getattr(msg.author, 'name', 'Unknown')
            log_action(f"TOTAL processing for {author_name}: {duration:.2f}s")
        except asyncio.CancelledError:
            log_warning(f"Generation task for {msg.author.name} was cancelled (likely bot shutdown).")
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            log_error(f"Error in intelligence pipeline: {e}\n{error_trace}")
            await self._send_response(msg.channel, "Something went wrong in my head. Try again?")

    async def _run_intelligence_pipeline(self, ctx: MessageContext):
        """Stage 2: Intelligence, Retrieval, and Response Generation."""
        # 2. Classification (Regex Fast-Path Only)
        c_start = time.perf_counter()
        await self._perform_classification(ctx)
        # Skip _finalize_classification entirely — regex fast-path only
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

    async def _perform_classification(self, ctx: MessageContext):
        """Classify the query using fast-path and prepare full-path task."""
        # Ensure we have the latest parser from context if it was late-initialized
        if self.intent_parser is None and hasattr(self.ctx, 'intent_parser'):
             self.intent_parser = self.ctx.intent_parser

        if self.intent_parser is None:
            log_warning("IntentParser not yet initialized. Skipping classification.")
            ctx.intent = None
            ctx.category = "general"
            return

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
        task_name = f"intent_{ctx.author_id}_{hash(ctx.message.content)}"

        all_tasks = task_registry.get_all_tasks()
        if task_name in all_tasks and not all_tasks[task_name].done():
            log_debug(f"Intent analysis already in progress for {ctx.author_name}, reusing task.")
            ctx.classification_task = all_tasks[task_name]
            return

        from utils.core.kaia_intelligence import ContextWeaver
        channel_mem = list(self.bot_state.channel_memory.get(ctx.channel_id, []))
        context_obj = ContextWeaver.weave(channel_mem)

        ctx.classification_task = asyncio.create_task(
            self.intent_parser.parse_intent(ctx.sanitized_content, context_obj)
        )
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
        """Check the semantic cache for similar recent queries."""
        # Semantic mapping moved to KaiaRAG for better contextual awareness
        # and easier testing.
        # noqa: SC001 - Stub intentional until cache re-implementation
        return False


    async def _retrieve_and_generate(self, ctx: MessageContext):
        """Stage 3: Retrieval, Context Optimization, and Ollama Generation."""

        # 1. REDUNDANCY BYPASS: Skip RAG for simple greetings and commands
        # This saves ~4-6 seconds of latency for simple interactions.
        if ctx.intent and ctx.intent.confidence >= 0.9 and ctx.intent.suggested_strategy in ["SOCIAL_GREETING", "COMMAND_EXECUTION"]:
            from utils.social.kaia_social_responder import load_persona_async
            log_info(f"Adaptive Skip: Bypassing RAG for high-confidence {ctx.intent.suggested_strategy}")
            
            # Populate minimum context needed for generation
            raw_persona = await load_persona_async()
            
            # Resolve runtime tags (Bug 2 Fix implementation)
            from datetime import datetime
            current_time = datetime.now().strftime("%A, %B %d, %Y | %I:%M %p")
            ctx.system_prompt = raw_persona.replace("[CURRENT_TIME]", current_time)
            
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
        # Outer gather timeout is double the internal retrieval timeout to allow for orchestration overhead
        rag_gather_timeout = self.config.rag_retrieval_timeout * 2  
        try:
            raw_results = await asyncio.wait_for(
                asyncio.gather(*task_objects, return_exceptions=True),
                timeout=rag_gather_timeout
            )
            # Handle individual task exceptions
            filtered_results = []
            for i, r in enumerate(raw_results):
                if isinstance(r, Exception):
                    log_warning(f"Retrieval task {task_names[i]} failed: {r}")
                    filtered_results.append([])
                else:
                    filtered_results.append(r)
            raw_results = filtered_results
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

        # 4c. Capture retrieval confidence from RAG instance and store on context
        if self.rag and hasattr(self.rag, '_last_retrieval_confidence'):
            ctx.retrieval_confidence = self.rag._last_retrieval_confidence
            ctx.retrieval_node_count = getattr(self.rag, '_last_retrieval_node_count', 0)
            # Update Kaia's coherence state with this retrieval's quality
            if self.bot_state:
                self.bot_state.update_kaia_state(coherence_sample=ctx.retrieval_confidence)
            log_debug(f"Retrieval confidence: {ctx.retrieval_confidence:.2f} "
                      f"({ctx.retrieval_node_count} nodes)")

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
        whitelist = {ctx.author_name, "Kaia"}
        if self.bot and self.bot.user:
            whitelist.add(self.bot.user.name)
        # Resolve display name variants
        if hasattr(ctx.message.author, 'display_name') and ctx.message.author.display_name:
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

        # 7. Curiosity injection — soft follow-up prompt for unresolved user mentions
        curiosity_note = ""
        try:
            from utils.core.curiosity_scanner import get_curiosity_prompt
            curiosity_note = get_curiosity_prompt(
                user_id=ctx.author_id,
                user_name=ctx.author_name,
                knowledge_base_dir=self.config.knowledge_base_dir,
                last_sent_timestamps=self.bot_state.curiosity_last_sent
            ) or ""
            if curiosity_note:
                # Record that we sent this prompt so cooldown applies
                import time as _time
                self.bot_state.curiosity_last_sent[str(ctx.author_id)] = _time.time()
                self.bot_state.save()
        except Exception as _ce:
            log_debug(f"Curiosity scanner error (non-fatal): {_ce}")
            curiosity_note = ""

        # Append curiosity note to system prompt if present
        if curiosity_note:
            ctx.system_prompt = ctx.system_prompt + f"\n\n{curiosity_note}"

        # 8. Mood state injection — one sentence of situational context
        try:
            if self.bot_state:
                mood_line = self.bot_state.get_kaia_state_line()
                if mood_line:
                    ctx.system_prompt = ctx.system_prompt + f"\n\n{mood_line}"
        except Exception:
            pass  # Never let mood injection break generation

        # 9. Generate Response (Stage 4)
        await self._generate_response_stage(ctx)

    async def _setup_retrieval_tasks(self, ctx: MessageContext):
        """Prepare all parallel tasks for retrieval."""
        
        # Determine query details
        clean_query = ctx.sanitized_content.lower().replace("kaia", "").strip("?,. ")
        display_name = (getattr(ctx.message.author, 'display_name', '') or "").strip(".")
        
        target_user_id = ctx.author_id
        target_user_name = ctx.author_name
        
        if not clean_query or clean_query in ["who am i", "what am i"]:
            clean_query = f"Who is {display_name}?"
        elif clean_query in ["who are you", "what are you", "who is kaia"]:
            clean_query = "Who is Kaia?"
            if self.bot and self.bot.user:
                target_user_id = self.bot.user.id
                target_user_name = self.bot.user.name
            else:
                target_user_id = 0
                target_user_name = "Kaia"

        # Tasks dictionary (Prevents IndexErrors)
        tasks = {}
        tasks['persona'] = asyncio.create_task(load_persona_async())
        tasks['traits'] = asyncio.create_task(self.personalization_engine.get_user_traits(ctx.author_id))

        is_observational = _is_observational_query(ctx.sanitized_content)
        
        if is_observational:
            log_info(f"Observational query detected, routing to search_recent_events/get_recent_highlights for {clean_query}")
            tasks['rag'] = asyncio.create_task(self.run_rag(
                self.rag.search_recent_events,
                clean_query,
                hours=24,
                limit=10
            ))
        else:
            retrieval_top_k = self.config.rag_top_k
            strict_identity_flag = (ctx.category in ["identity", "self", "whoami", "entity"])

            if ctx.intent and ctx.intent.suggested_strategy == "RECAP_QUERY":
                retrieval_top_k = 5
                strict_identity_flag = True
                
            tasks['rag'] = asyncio.create_task(self.run_rag(
                self.rag.retrieve, 
                clean_query, 
                user_id=target_user_id, 
                user_name=target_user_name, 
                top_k=retrieval_top_k,
                strict_identity=strict_identity_flag,
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
        # 1. PERSONA LOADING (Trace life-cycle)
        raw_persona = results.get('persona', "")
        
        # FIX: Ensure we don't end up with a list from a cancelled task/timeout
        if isinstance(raw_persona, list):
            log_warning("Persona result was a list (likely from gather timeout). Resetting to empty string.")
            raw_persona = ""
            
        ctx.system_prompt = str(raw_persona)
        log_debug(f"PERSONA LOADED: {len(ctx.system_prompt)} chars | preview: {ctx.system_prompt[:100]}")

        ctx.raw_nodes = results.get('rag', [])
        
        # Merge news results if they were run separately
        if 'rag_news' in results and results['rag_news']:
            if isinstance(ctx.raw_nodes, list) and isinstance(results['rag_news'], list):
                ctx.raw_nodes.extend(results['rag_news'])
            
        ctx.user_traits = results.get('traits', {})
        
        # Adaptation
        ctx.system_prompt = self.personalization_engine.adapt_prompt(ctx.system_prompt, ctx.user_traits)

        # Inject self-model at top of system prompt if available
        # memory/kaia_self_model.md is Kaia's own synthesized identity across time.
        # It takes precedence over generic persona — it's not who she is, it's who she's been.
        try:
            import os
            self_model_path = os.path.join("memory", "kaia_self_model.md")
            if os.path.exists(self_model_path):
                with open(self_model_path, 'r', encoding='utf-8') as _smf:
                    self_model_content = _smf.read().strip()
                # Strip the generation comment header if present
                if self_model_content.startswith('<!--'):
                    self_model_content = self_model_content[self_model_content.find('-->')+3:].strip()
                if self_model_content:
                    ctx.system_prompt = (
                        f"[SELF-MODEL — who i've been lately, my own words]\n"
                        f"{self_model_content}\n\n"
                        f"[PERSONA — core identity]\n"
                        f"{ctx.system_prompt}"
                    )
                    log_debug(f"Self-model injected ({len(self_model_content)} chars)")
        except Exception as _sme:
            log_debug(f"Self-model injection skipped: {_sme}")

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
        # 1. CONTEXT OPTIMIZATION
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


        messages = self._construct_messages(ctx, optimized)
        
        # 2.5 Inline Vision Processing (native multimodal)
        if hasattr(ctx.message, 'attachments') and ctx.message.attachments:

            images = []
            for att in ctx.message.attachments:
                filename = getattr(att, 'filename', '').lower()
                if any(filename.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
                    try:
                        is_gif = filename.endswith('.gif')
                        log_debug(f"Fetching image attachment for inline vision: {att.url}")
                        b64 = await self._fetch_image_as_base64(att.url, is_gif=is_gif)
                        if b64:
                            images.append(b64)
                        if is_gif:
                            try:
                                await ctx.message.channel.send("*(Viewing first frame of GIF)*")
                            except Exception:
                                pass
                    except Exception as e:
                        log_warning(f"Failed to fetch image {getattr(att, 'filename', 'unknown')} for inline vision: {e}")
            
            if images and messages and messages[-1].get("role") == "user":
                messages[-1]["images"] = images
                log_info(f"Attached {len(images)} images to user message for inline multimodal processing.")
        
        # 3. LLM Generation (flag active to block quips/dreams)
        self.bot_state.is_generating = True
        try:
            g_start = time.perf_counter()
            ctx.response_text = await self._call_ollama_with_retries(ctx, messages)
        finally:
            self.bot_state.is_generating = False
        
        # 4. Final Processing & Logging
        await self._post_process_and_log(ctx)

    def _construct_messages(self, ctx: MessageContext, optimized: Dict[str, Any]) -> List[Dict[str, str]]:
        """Build the system, RAG, history, and user messages."""
        system_prompt = optimized['persona']
        context_str = optimized['rag']
        optimized_history = optimized.get('history', [])
        
        # Core Unification: Persona + RAG + History
        rag_block = (
            f"### DATA RETRIEVAL FOR: {ctx.author_name}\n"
            f"{context_str or 'No specific historical records found.'}\n"
            "---"
        ) if context_str else f"### CURRENT_USER: {ctx.author_name}\nNo records found."

        # Grounding Enforcement
        grounding_categories = {"identity", "social_identity", "self", "whoami", "entity"}
        is_observational = _is_observational_query(ctx.sanitized_content)
        needs_grounding = ctx.category in grounding_categories or is_observational

        if not context_str and needs_grounding:
            if is_observational:
                rag_block += (
                    "\n\nCRITICAL: No interaction logs found for that time window. "
                    "Do not invent users, events, or conversations."
                )
            else:
                rag_block += "\n\nCRITICAL: No specific records found. Do not invent details."

        # Epistemic honesty: when retrieval was weak, tell the model to hedge
        if hasattr(ctx, 'retrieval_confidence') and ctx.retrieval_confidence < 0.45 and ctx.retrieval_node_count < 2:
            rag_block += (
                "\n[note: memory retrieval was weak for this query — "
                "speak from what you know, hedge where uncertain, do not invent]"
            )

        current_time_str = datetime.now().strftime("%A, %B %d, %Y | %I:%M %p")

        # Bug 2 Fix: Move time to a metadata block at the end, and stop replacing it inside persona
        # to prevent the LLM from thinking it's a catchphrase it must repeat.
        metadata_block = (
            "\n\n--- METADATA ---\n"
            f"CURRENT_TIME: {current_time_str}\n"
            "CRITICAL: Any timestamps in conversation history are outdated. Do not repeat the CURRENT_TIME string in your response."
        )

        recap_constraint_block = ""
        if ctx.intent and ctx.intent.suggested_strategy == "RECAP_QUERY":
            recap_constraint_block = (
                "RECALL CONSTRAINT — ACTIVE\n"
                "You have been asked to recall recent events or interactions.\n"
                "You MUST only reference events that appear explicitly in your retrieved RAG context nodes.\n"
                "If the RAG context is sparse or empty for the requested time window, say so plainly.\n"
                "Do NOT reconstruct or infer conversations that are not in your retrieved nodes.\n"
                "A correct response when nodes are sparse is: \"i don't have clear records for that window. the logs i can actually see are from [date of most recent node].\"\n"
                "Do NOT generate plausible-sounding summaries from your base knowledge. That is a hallucination.\n"
                "END RECALL CONSTRAINT\n\n"
            )

        full_system_prompt = (
            f"{recap_constraint_block}"
            f"{system_prompt}\n\n"
            f"{rag_block}"
            f"{metadata_block}"
        )

        # [DEBUG] Trace final prompt assembly
        f_snippet = (full_system_prompt[:200] + "...") if len(full_system_prompt) > 200 else full_system_prompt
        log_debug(f"DEBUG: Assembled system prompt (total len={len(full_system_prompt)}): {f_snippet}")

        messages = [
            {"role": "system", "content": full_system_prompt}
        ]
        
        # USE ONLY OPTIMIZED HISTORY (Fixes Double-History Bug)
        for turn in optimized_history:
            if isinstance(turn, dict) and 'role' in turn and 'content' in turn:
                if turn.get('role') == 'system':
                    continue
                # Scrub [CURRENT_TIME] and resolved date strings from history to prevent mimicry
                turn = turn.copy()
                content = turn['content']
                # Remove literal tag
                content = re.sub(r'\[CURRENT_TIME\]', '', content)
                # Remove resolved date strings (e.g., Friday, March 06, 2026 | 07:30 PM)
                content = re.sub(
                    r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+'
                    r'(January|February|March|April|May|June|July|August|September|October|November|December)'
                    r'\s+\d{1,2},\s+\d{4}\s+\|[^\n]*',
                    '', content
                )
                turn['content'] = content.strip()
                messages.append(turn)

        # Re-assert conversation target
        if ctx.parent_context:
            label = "[REPLYING_TO_CONTEXT]"
            if ctx.root_context == ctx.parent_context:
                label = "[THREAD_ROOT_AND_PARENT]"
            clipped_parent = ctx.parent_context[:1000] + ("..." if len(ctx.parent_context) > 1000 else "")
            
            context_reminder = f"{label}\nIgnore recent channel chatter if unrelated. The user is replying DIRECTLY to this message:\n{clipped_parent}"
            messages.append({"role": "system", "content": context_reminder})

        messages.append({"role": "user", "content": ctx.sanitized_content})
        
        log_debug(f"DEBUG: Final messages list contains {len(messages)} items (System + {len(optimized_history)} history turns + User).")
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
                
                from utils.infrastructure.gpu.gpu_manager import gpu_memory_manager, GPUTaskPriority
                
                response = await gpu_memory_manager.run_with_gpu_guard(
                    model_name=self.config.chat_model,
                    priority=GPUTaskPriority.CHAT,
                    coro=asyncio.wait_for(
                        SelfHealingSystem.call_with_fallback(
                            self.ollama_client.chat,
                            model=self.config.chat_model,
                            messages=messages,
                            options=current_options,
                            keep_alive=-1
                        ),
                        timeout=self.config.chat_generation_timeout
                    ),
                    task_id=f"chat_{uuid.uuid4().hex[:8]}"
                )
                
                content = response['message']['content']

                # Strip LLM-added outer codeblocks
                content = content.strip()
                while content.startswith("```") and content.endswith("```"):
                    content = content[3:-3].strip()
                    if "\n" in content:
                        first_line = content.split('\n')[0].strip()
                        if first_line and not any(c.isspace() for c in first_line) and len(first_line) < 20:
                            content = '\n'.join(content.split('\n')[1:]).strip()

                content = content.replace("```", "").replace("``", "")

                # EMERGENCY FILTER: Strip hallucinated [CURRENT_TIME] or time signatures
                # preventing history pollution if the LLM ignores instructions.
                content = re.sub(r'\[CURRENT_TIME\].*', '', content).strip()
                content = re.sub(r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\s+\|.*', '', content).strip()

                if not content:
                    log_warning(f"Attempt {attempt + 1}: Empty response. Retrying...")
                    continue

                # Cleanup
                should_detect = self.config.get('features.hallucination_detection', True)
                author_display = getattr(ctx.message.author, 'name', 'Unknown')
                is_owner = self.config.is_owner(author_display, ctx.author_name, ctx.author_id)
                log_debug(f"[HALLUCINATION_CHECK] Author: {author_display} (ID: {ctx.author_id}), Config Owner: {is_owner}")

                if should_detect and not is_owner:
                    content = HallucinationDetector.clean_response(content)
                    
                if not content:
                    log_warning(f"Attempt {attempt + 1} failed: Empty response after filtering (is_owner={is_owner}). Author: {author_display}")
                    continue
                
                if not is_owner:
                    content = EmergencyContaminationFilter.filter_response(content)
                    
                if not content:
                    log_warning(f"Attempt {attempt + 1} failed: Veracity violation (Fiction/Contamination detected). Author: {author_display}, is_owner: {is_owner}")
                    continue
                
                # Style Hardening (Silent Stripping)
                filtered = BotSpeakFilter.strip_bot_speak(content)
                # Safety net: never let the BotSpeakFilter empty a valid response
                content = filtered if filtered and filtered.strip() else content
                
                if content and content.strip():
                    self.bot_state.first_chat_done = True
                    return content
                else:
                    log_warning(f"Attempt {attempt + 1} failed: Result empty after filtering.")
                    continue
            except Exception as e:
                log_error(f"Attempt {attempt + 1} failed: {e}")
                
        return "The data's a bit scrambled right now. Ask me again later."

    async def _post_process_and_log(self, ctx: MessageContext):
        """Final cleanups, sending response, and logging."""
        # 1. FINAL OUTPUT FILTER: Strip hallucinated [CURRENT_TIME] from outgoing text
        ctx.response_text = re.sub(r'\[CURRENT_TIME\].*?(\n|$)', '', ctx.response_text).strip()
        
        # 2. SEND RESPONSE
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
                
                # BUG 1 FIX: Before writing to interaction log or memory, strip JSON wrapper if found
                bot_response = ctx.response_text
                match = _JSON_WRAPPER_PATTERN.search(bot_response)
                if match:
                    bot_response = match.group(1).replace('\\"', '"').replace('\\n', '\n')

                # Add author prefix to user message for history disambiguation
                user_msg_with_author = f"{ctx.author_name}: {ctx.sanitized_content}"
                self.bot_state.channel_memory[ctx.channel_id].append({"role": "user", "content": user_msg_with_author})
                self.bot_state.channel_memory[ctx.channel_id].append({"role": "assistant", "content": bot_response})
                
                # Update personalization and relevance feedback
                await self.personalization_engine.learn_from_interaction(ctx.author_id, ctx.sanitized_content, bot_response)
                await self.relevance_feedback.log_interaction(ctx.sanitized_content, bot_response, ctx.author_id, ctx.author_name)
                
                # Log for RAG
                # CRITICAL FIX: Use sanitized_content to avoid poisoning RAG with [REPLYING_TO] tags
                await self.rag.log_user_interaction_async(ctx.author_id, ctx.author_name, ctx.sanitized_content, bot_response)
                
                self.performance_monitor.stop_timer('total', 'response_time')
                
                # Direct metrics
                response_time = time.time() - ctx.start_time
                self.stats_tracker.record_response_time(response_time)
                # Also feed stats_poller so the dashboard VRM/RTime display works
                try:
                    from utils.infrastructure.monitoring.stats_helpers import safe_record_response_time
                    safe_record_response_time(response_time)
                except Exception:
                    pass
                
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

    async def _fetch_image_as_base64(self, url: str, is_gif: bool = False) -> str:
        """Fetch an image from a URL and return as a base64 string for inline multimodal vision."""
        timeout_seconds = self.config.url_fetch_timeout
        try:
            async with asyncio.timeout(timeout_seconds + 2.0): # Outer safety
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout_seconds)) as resp:
                        if resp.status == 200:
                            data = await resp.read()

                            # GIFs: extract first frame and convert to PNG
                            if is_gif:
                                try:
                                    from PIL import Image
                                    import io
                                    gif = Image.open(io.BytesIO(data))
                                    gif.seek(0)  # first frame
                                    frame = gif.convert("RGBA")
                                    buf = io.BytesIO()
                                    frame.save(buf, format="PNG")
                                    data = buf.getvalue()
                                    log_info("GIF detected — extracted first frame as PNG for vision processing.")
                                except Exception as gif_err:
                                    log_warning(f"GIF frame extraction failed: {gif_err}. Skipping attachment.")
                                    return ""

                            return base64.b64encode(data).decode('utf-8')
                        else:
                            log_warning(f"Failed to fetch image: Status {resp.status} for {url}")
                            return ""
        except asyncio.TimeoutError:
            log_warning(f"Timeout fetching image from {url}")
            return ""
        except Exception as e:
            log_error(f"Error fetching image: {e}")
            return ""
