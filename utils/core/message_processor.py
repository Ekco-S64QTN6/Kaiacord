import asyncio
import os
import time
import re
import hashlib
import uuid
import json
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
        r"\brecap\b.{0,40}(past|last)\s+\d+\s*(hour|day|week|hr)",
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

# ── Recap Time Window Extraction ─────────────────────────────────────────
_RECAP_HOURS_PATTERN = re.compile(
    r'(\d+)\s*(hour|hr|day|week)', re.IGNORECASE
)

def _extract_recap_hours(text: str) -> int:
    """Extract time window from a recap query. Returns hours as int, defaults to 24."""
    text_lower = text.lower()
    
    m = _RECAP_HOURS_PATTERN.search(text_lower)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        if unit.startswith('week'):
            return n * 168
        return n * 24 if unit.startswith('day') else n

    # Natural time references
    if re.search(r'\bweek\b', text_lower):
        return 168

    now = datetime.now()
    
    if re.search(r'\bthis morning\b|\bthis am\b', text_lower):
        # Hours since midnight
        return max(1, now.hour + 1)
    
    if re.search(r'\btonight\b|\bthis evening\b', text_lower):
        # Hours since ~5pm or since midnight if it's already past midnight
        if now.hour >= 17:
            return max(1, now.hour - 17 + 1)
        return 8  # Reasonable default for "tonight" in early morning
    
    if re.search(r'\blast night\b', text_lower):
        # Previous evening window: roughly 5pm yesterday to midnight
        return now.hour + 7  # hours ago to cover ~5pm yesterday
    
    if re.search(r'\btoday\b', text_lower):
        return max(1, now.hour + 1)  # Since midnight today
    
    if re.search(r'\byesterday\b', text_lower):
        return 24 + now.hour  # All of yesterday

    return 24  # True fallback

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
        
        # Identity Cache (self-model, constitution)
        self._identity_cache = {}
        self._identity_cache_time = 0.0
        self._IDENTITY_CACHE_TTL = 300.0 # 5 minutes
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

        import discord as _discord
        
        if not is_social and msg.guild is not None:
            # Resolve the effective channel name.
            # Forum threads: msg.channel is a Thread, parent is the forum channel.
            # Text channels: msg.channel is the channel itself.
            is_thread = isinstance(msg.channel, _discord.Thread)
            if is_thread:
                effective_channel_name = msg.channel.parent.name.lower() if msg.channel.parent else ""
            else:
                effective_channel_name = msg.channel.name.lower()

            if effective_channel_name in self.config.blacklisted_channels:
                # ── Passive Observation ───────────────────────────────────
                # Kaia watches blacklisted channels (e.g. #general) but
                # never speaks.  She can react with emoji and log messages
                # to RAG so she learns from the conversation.
                if not msg.author.bot:
                    try:
                        if not hasattr(self, '_reactions'):
                            from utils.core.kaia_reactions import KaiaReactions
                            self._reactions = KaiaReactions()
                        await self._reactions.maybe_react(msg)
                    except Exception:
                        pass

                    # Background RAG log — observation only (empty response)
                    try:
                        if self.rag:
                            author_display = msg.author.display_name or msg.author.name
                            asyncio.create_task(
                                self.rag.log_user_interaction_async(
                                    msg.author.id, author_display,
                                    msg.content, ""
                                )
                            )
                    except Exception:
                        pass
                return
                
            content = getattr(msg, 'content', '').strip().lower()
            is_rpg_cmd = content.startswith("!rpg")
            
            if is_rpg_cmd:
                rpg_blacklist = ["kaia-opolis", "general", "general chat"]
                if effective_channel_name in rpg_blacklist:
                    return # Block RPG commands here
            else:
                # Normal Kaia chat routing
                rpg_channel = self.config.get('discord.rpg_channel', 'aethelgard').lower()
                
                # Block Kaia from responding to general chat in the RPG channel/threads
                if effective_channel_name == rpg_channel:
                    return

                whitelisted = self.config.whitelisted_channels
                if whitelisted and effective_channel_name not in whitelisted:
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
                    await msg.channel.send("still waking up. give me a minute.")
                except Exception: pass
                return

        # 3. Command Dispatching (Phase 3 Registry)
        if await dispatch_command(self.ctx, msg, load_persona_async, send_kaia_response):
            if is_social: log_debug("Social message handled by command dispatcher")
            return

        if is_social: log_debug("Social message passed command dispatch")

        # 4. Trigger Logic
        bot_name = self.bot.user.display_name.lower() if (self.bot and self.bot.user) else "kaia"
        is_mention = (
            not is_social and (
                (self.bot and self.bot.user and self.bot.user in msg.mentions)  # proper <@ID> mention (autocomplete)
                or (self.bot and self.bot.user and f"<@{self.bot.user.id}>" in msg.content)  # explicit ID string fallback
                or (self.bot and self.bot.user and f"<@!{self.bot.user.id}>" in msg.content) # legacy !ID format
                or bot_name in msg.content.lower()          # plain text @kaia fallback
                or any(r.name.lower() == bot_name for r in getattr(msg, 'role_mentions', []))  # role @Kaia
            )
        ) or is_social

        # ── Emoji Reactions (independent of mention status) ───────────
        # Kaia can react to ANY message, even ones she's about to reply to.
        # Rate limits (4/hour, 120s cooldown, 30% gate) prevent overuse.
        if not msg.author.bot:
            try:
                if not hasattr(self, '_reactions'):
                    from utils.core.kaia_reactions import KaiaReactions
                    self._reactions = KaiaReactions()
                await self._reactions.maybe_react(msg)
            except Exception:
                pass  # Never let reactions break anything
        
        if not is_mention and not is_social:
            return  # Not addressed to Kaia — no text response
            
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
        # Human-like reading pause — delay before typing indicator to simulate reading
        import secrets as _secrets
        _read_time = 0.8 + (len(ctx.sanitized_content) / 200)  # ~1s base + 1s per 200 chars
        _read_time = min(_read_time, 4.0)  # Cap at 4 seconds
        _read_time *= (0.7 + _secrets.randbelow(60) / 100)  # ±30% variance
        await asyncio.sleep(_read_time)

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
            ctx.fast_intent_strategy = fast_intent.suggested_strategy
            ctx.category = self._derive_legacy_category(fast_intent)
            log_info(f"Fast-path intent: {fast_intent.suggested_strategy} ({ctx.category})")
            
            # If high confidence command/greeting/recap, skip full analysis
            if fast_intent.confidence > 0.9 and fast_intent.suggested_strategy in ["SOCIAL_GREETING", "COMMAND_EXECUTION", "RECAP_QUERY"]:
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
            ctx.system_prompt = raw_persona.replace("[CURRENT_TIME]", f"[CURRENT_TIME]: {current_time}")
            
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

        # 8b. Relationship context injection — per-user familiarity and history
        try:
            if self.bot_state:
                # Time-delta reunion hint (Item 3)
                time_hint = self.bot_state.get_time_delta_hint(ctx.author_id, ctx.author_name)
                if time_hint:
                    ctx.system_prompt = ctx.system_prompt + f"\n\n{time_hint}"

                # Open Loop Callback — reference unfinished threads from past conversations
                rel = self.bot_state.relationships.get(str(ctx.author_id))
                if rel and time_hint:  # Only inject when user is returning after absence
                    open_loop = rel.get('last_open_loop', '')
                    if open_loop:
                        ctx.system_prompt = ctx.system_prompt + (
                            f"\n\n[last time, {ctx.author_name} mentioned: \"{open_loop}\". "
                            f"if it comes up naturally, ask about it. don't force it.]"
                        )
                        # Clear after injection — one-shot callback
                        rel['last_open_loop'] = ''
                        self.bot_state.save()

                # Relationship summary (Item 2)
                rel_summary = self.bot_state.get_relationship_summary(ctx.author_id, ctx.author_name)
                if rel_summary:
                    ctx.system_prompt = ctx.system_prompt + f"\n\n{rel_summary}"

                # Relationship events (Item 7)
                from utils.core.relationship_manager import get_top_events, format_for_injection
                top_events = get_top_events(ctx.author_id, n=3)
                if top_events:
                    events_line = format_for_injection(top_events)
                    if events_line:
                        ctx.system_prompt = ctx.system_prompt + f"\n\n{events_line}"
        except Exception as _rel_err:
            log_debug(f"Relationship injection error (non-fatal): {_rel_err}")

        # 8c. Beliefs injection — topically relevant persistent opinions (Item 9)
        # Uses semantic alias expansion for much better matching than raw word-overlap.
        matching = []  # Initialized here so 8g can safely reference it even if 8c throws
        try:
            beliefs_path = os.path.join("memory", "beliefs.json")
            if os.path.exists(beliefs_path):
                with open(beliefs_path, 'r', encoding='utf-8') as bf:
                    all_beliefs = json.load(bf)
                if all_beliefs:
                    query_lower = ctx.sanitized_content.lower()
                    query_words = set(query_lower.split())
                    # Remove common stop words to reduce false positives
                    stop_words = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'do', 'does',
                                  'did', 'i', 'you', 'we', 'they', 'it', 'to', 'of', 'in',
                                  'for', 'on', 'with', 'at', 'by', 'and', 'or', 'but', 'not',
                                  'what', 'how', 'why', 'when', 'where', 'who', 'that', 'this',
                                  'my', 'your', 'me', 'be', 'have', 'has', 'had', 'about',
                                  'just', 'like', 'think', 'know', 'really', 'so', 'can'}
                    query_words -= stop_words

                    matching = []
                    for b in all_beliefs:
                        topic = b.get('topic', '').lower()
                        topic_words = set(topic.split()) - stop_words

                        # Check 1: Direct word overlap (original behavior)
                        if query_words & topic_words:
                            conf = b.get('confidence', 0.5)
                            stance_qualifier = '' if conf > 0.7 else ' (uncertain)'
                            matching.append(f"{b['topic']}: {b['position']}{stance_qualifier}")
                            continue

                        # Check 2: Alias matching (pre-computed during dream extraction)
                        aliases = set(b.get('aliases', []))
                        if aliases and (query_words & aliases):
                            conf = b.get('confidence', 0.5)
                            stance_qualifier = '' if conf > 0.7 else ' (uncertain)'
                            matching.append(f"{b['topic']}: {b['position']}{stance_qualifier}")
                            continue

                        # Check 3: Substring match (topic phrase appears in query)
                        if len(topic) > 4 and topic in query_lower:
                            conf = b.get('confidence', 0.5)
                            stance_qualifier = '' if conf > 0.7 else ' (uncertain)'
                            matching.append(f"{b['topic']}: {b['position']}{stance_qualifier}")

                    if matching:
                        ctx.system_prompt = ctx.system_prompt + f"\n\n[current stances: {'; '.join(matching[:3])}]"
        except Exception:
            pass  # Never let beliefs injection break generation

        # ── BEHAVIORAL MODULATION (ELIZA Effect) ──────────────────────────────
        # These lightweight prompt injections create the illusion of inner life
        # by subtly varying Kaia's behavior based on context. No LLM calls.

        # 8d. Time-of-Day Personality Modulation
        try:
            _hour = datetime.now().hour
            if 6 <= _hour < 12:
                _time_mod = "[time: morning — you're more direct and concise right now. shorter responses.]"
            elif 12 <= _hour < 18:
                _time_mod = "[time: afternoon — normal energy. balanced responses.]"
            elif 18 <= _hour < 24:
                _time_mod = "[time: evening — slightly more relaxed. willing to go longer on interesting topics.]"
            else:
                _time_mod = "[time: late night — you're more reflective and unhurried. willing to sit with harder questions. quieter energy.]"
            ctx.system_prompt = ctx.system_prompt + f"\n\n{_time_mod}"
        except Exception:
            pass

        # 8e. Adaptive Tone Mirroring — match the user's communication style
        try:
            _recent_user_msgs = [
                m['content'] for m in self.bot_state.channel_memory.get(ctx.channel_id, [])
                if m.get('role') == 'user'
            ][-5:]  # Last 5 user messages
            if _recent_user_msgs:
                _avg_len = sum(len(m) for m in _recent_user_msgs) / len(_recent_user_msgs)
                if _avg_len < 40:
                    _mirror = "[style: they write short. match their brevity. don't over-explain.]"
                elif _avg_len > 250:
                    _mirror = "[style: they write at length. match their depth. fuller responses welcome.]"
                else:
                    _mirror = ""
                if _mirror:
                    ctx.system_prompt = ctx.system_prompt + f"\n\n{_mirror}"
        except Exception:
            pass

        # 8f. Conversational Fatigue — responses get shorter after long exchanges
        try:
            _session_msgs = list(self.bot_state.channel_memory.get(ctx.channel_id, []))
            _exchange_count = sum(1 for m in _session_msgs if m.get('role') == 'user')
            if _exchange_count >= 20:
                ctx.system_prompt = ctx.system_prompt + (
                    "\n\n[you've been talking for a while. your responses should be getting shorter "
                    "and more direct. it's okay to give brief answers.]"
                )
            elif _exchange_count >= 15:
                ctx.system_prompt = ctx.system_prompt + (
                    "\n\n[this has been a longer conversation. slightly shorter responses feel natural right now.]"
                )
        except Exception:
            pass

        # 8g. Opinion Evolution — reference belief changes when relevant
        try:
            if matching:  # From beliefs injection (8c)
                from pathlib import Path as _Path
                _gl = _Path("memory") / "growth_log.jsonl"
                if _gl.exists():
                    # Tail-read: only last ~3KB to avoid loading the full file
                    with open(_gl, 'r', encoding='utf-8') as _gf:
                        _gf.seek(0, 2)
                        _sz = _gf.tell()
                        _gf.seek(max(0, _sz - 3072))
                        if _sz > 3072:
                            _gf.readline()  # Discard partial first line
                        _lines = _gf.readlines()[-20:]
                    for _line in reversed(_lines):
                        try:
                            _evt = json.loads(_line)
                            if _evt.get('type') == 'belief_revised':
                                _topic = _evt.get('topic', '')
                                # Check if this revised belief is one of the matching ones
                                if any(_topic.lower() in m.lower() for m in matching):
                                    ctx.system_prompt = ctx.system_prompt + (
                                        f"\n\n[your stance on \"{_topic}\" has evolved. "
                                        f"you previously thought: \"{_evt.get('old_position', '')[:80]}\". "
                                        f"if natural, you may reference this shift.]"
                                    )
                                    break
                        except json.JSONDecodeError:
                            continue
        except Exception:
            pass

        # 8h. Micro-Mood Expressions — linguistic behavior hints from mood floats
        try:
            if self.bot_state:
                _eng = getattr(self.bot_state, 'kaia_engagement', 0.5)
                _coh = getattr(self.bot_state, 'kaia_coherence', 0.85)
                _dfr = getattr(self.bot_state, 'kaia_dream_freshness', 0.5)
                _mood_hints = []
                if _eng >= 0.8:
                    _mood_hints.append("slightly more energetic phrasing")
                elif _eng <= 0.2:
                    _mood_hints.append("lower energy, fewer words")
                if _coh < 0.5:
                    _mood_hints.append("more hedging ('i think', 'maybe', 'not sure')")
                if _dfr >= 0.9:
                    _mood_hints.append("slightly more abstract, willing to be philosophical")
                if _mood_hints:
                    ctx.system_prompt = ctx.system_prompt + f"\n\n[mood modifiers: {'; '.join(_mood_hints)}]"
        except Exception:
            pass

        # 8i. "I've Been Reading" Mentions — organic references to recently ingested knowledge
        try:
            if self.bot_state and getattr(self.bot_state, 'recent_ingestions', None):
                _recent = self.bot_state.recent_ingestions[-1]
                if isinstance(_recent, dict):
                    _filename = _recent.get('filename', '')
                    if _filename:
                        import os as _os
                        _clean_name = _os.path.splitext(_os.path.basename(_filename))[0].replace('_', ' ').replace('-', ' ')
                        ctx.system_prompt = ctx.system_prompt + (
                            f"\n\n[you recently read a document about: \"{_clean_name}\". "
                            f"if relevant to the conversation, you may reference it naturally, but don't force it.]"
                        )
        except Exception:
            pass

        # System state injection — ground truth hardware/OS facts
        try:
            from utils.infrastructure.system.kaia_sysmon import build_system_prompt_block_async
            sys_block = await build_system_prompt_block_async()
            if sys_block:
                ctx.system_prompt = ctx.system_prompt + f"\n\n{sys_block}"
        except Exception:
            pass  # Never let sysmon injection break generation

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
        is_recap = ctx.fast_intent_strategy == "RECAP_QUERY"

        if is_observational or is_recap:
            hours = _extract_recap_hours(ctx.sanitized_content) if is_recap else 24
            log_info(f"RECAP routing confirmed — strategy={ctx.fast_intent_strategy}")
            log_info(f"{'RECAP' if is_recap else 'Observational'} query — routing to search_recent_events (hours={hours})")

            # Capture channel_memory before task creation (it's a deque, snapshot it now)
            _channel_memory_snapshot = list(
                self.bot_state.channel_memory.get(ctx.channel_id, [])
            ) if self.bot_state else []

            async def _recap_with_memory_fallback():
                """Run search_recent_events; if sparse, prepend channel_memory as synthetic nodes."""
                rag_results = await self.run_rag(
                    self.rag.search_recent_events,
                    clean_query,
                    hours=hours,
                    limit=10
                )

                # Synthesize channel_memory into RAG-compatible dicts so the RECALL
                # CONSTRAINT in the generation prompt will permit Kaia to reference them.
                memory_nodes = []
                if _channel_memory_snapshot:
                    for turn in _channel_memory_snapshot:
                        role = turn.get("role", "")
                        content = turn.get("content", "").strip()
                        if not content:
                            continue
                        label = "Kaia" if role == "assistant" else turn.get("name", "User")
                        memory_nodes.append({
                            "content": f"[live session — {label}]: {content}",
                            "metadata": {
                                "source_type": "channel_memory", 
                                "file_path": "live_session_memory",
                                "retrieval_method": "injection"
                            },
                            "label": f"Live Session ({label})",
                            "score": 0.950,  # High score: live context beats indexed logs
                        })

                combined_results = memory_nodes + (rag_results or [])
                if memory_nodes:
                    log_info(f"RECAP: injecting {len(memory_nodes)} channel_memory turns as context nodes")
                    # Also expose to !explain by updating the RAG result cache.
                    # _last_retrieval_results is set by search_recent_events; we prepend
                    # the live-session nodes so the audit trail reflects what's actually in the prompt.
                    if hasattr(self, 'rag') and self.rag:
                        if hasattr(self.rag, '_last_retrieval_results'):
                            self.rag._last_retrieval_results = memory_nodes + (self.rag._last_retrieval_results or [])
                
                return combined_results

            tasks['rag'] = asyncio.create_task(_recap_with_memory_fallback())
        else:
            retrieval_top_k = self.config.rag_top_k
            strict_identity_flag = (ctx.category in ["identity", "self", "whoami", "entity"])

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
        
        # Scrub RAG context of system time signatures
        for node in ctx.raw_nodes:
            if isinstance(node, dict) and 'content' in node:
                # Handles: [CURRENT_TIME]: ..., CURRENT_TIME: ..., and legacy [CURRENT_TIME]
                node['content'] = re.sub(r'\[?CURRENT_TIME\]?:?.*', '', node['content']).strip()
        
        # Adaptation
        ctx.system_prompt = self.personalization_engine.adapt_prompt(ctx.system_prompt, ctx.user_traits)

        # 2. Dynamic Identity Injection (Self-Model & Constitution)
        # memory/kaia_self_model.md and memory/kaia_constitution.md are stable documents
        # that we cache with a TTL to avoid redundant I/O.
        now = time.time()
        if self._identity_cache_time + self._IDENTITY_CACHE_TTL < now or not self._identity_cache:
            self._update_identity_cache()
            self._identity_cache_time = now

        # Inject self-model FIRST (prepends — will be second after constitution prepends on top)
        self_model_content = self._identity_cache.get("self_model", "")
        if self_model_content:
            ctx.system_prompt = (
                f"[SELF-MODEL — who i've been lately, my own words]\n"
                f"{self_model_content}\n\n"
                f"{ctx.system_prompt}"
            )
            log_debug(f"Self-model injected from cache ({len(self_model_content)} chars)")

        # Inject living identity stream
        identity_stream = self._identity_cache.get("identity_stream", "")
        if identity_stream:
            ctx.system_prompt = (
                f"[RECENT PERSPECTIVE SHIFTS]\n{identity_stream[-800:]}\n\n"
                f"{ctx.system_prompt}"
            )
            log_debug(f"Identity stream injected from cache")

        # Inject constitution SECOND (prepends on top — ends up first in final prompt)
        constitution_content = self._identity_cache.get("constitution", "")
        if constitution_content:
            ctx.system_prompt = (
                f"[CONSTITUTION — how i operate, in my own words]\n"
                f"{constitution_content}\n\n"
                f"{ctx.system_prompt}"
            )
            log_debug(f"Constitution injected from cache ({len(constitution_content)} chars)")

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

        # Self-Referential Continuity: detect when RAG retrieves Kaia's own dreams
        try:
            _has_dream_context = False
            for node in ctx.raw_nodes:
                _meta = node.get('metadata', {}) if isinstance(node, dict) else getattr(node, 'metadata', {})
                _fp = (_meta.get('file_path', '') or '').lower()
                if 'kaia_dreams' in _fp or 'dream_' in _fp:
                    _has_dream_context = True
                    break
            if _has_dream_context:
                ctx.system_prompt = ctx.system_prompt + (
                    "\n\n[some of your retrieved context is from your own dream reflections. "
                    "reference these as things you were 'thinking about' or 'something that came to mind', "
                    "not as documents or files. they are your own thoughts.]"
                )
        except Exception:
            pass

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
        if self.bot_state:
            self.bot_state.is_generating = True
        try:
            g_start = time.perf_counter()
            ctx.response_text = await self._call_ollama_with_retries(ctx, messages)
        finally:
            if self.bot_state:
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
                f"\n[note: memory retrieval was weak (confidence={ctx.retrieval_confidence:.2f}) — "
                "speak from what you know, hedge where uncertain, do not invent]"
            )

        current_time_str = datetime.now().strftime("%A, %B %d, %Y | %I:%M %p")

        # Bug 2 Fix: Move time to a metadata block at the end, and stop replacing it inside persona
        # to prevent the LLM from thinking it's a catchphrase it must repeat.
        metadata_block = (
            "\n\n--- METADATA ---\n"
            f"[CURRENT_TIME]: {current_time_str}\n"
            "CRITICAL: Any timestamps in conversation history are outdated. Do not repeat the [CURRENT_TIME] string or your metadata in your response."
        )

        recap_constraint_block = ""
        _needs_recall_constraint = (
            (ctx.intent and ctx.intent.suggested_strategy == "RECAP_QUERY") or
            _is_observational_query(ctx.sanitized_content)
        )
        if _needs_recall_constraint:
            recap_constraint_block = (
                "RECALL CONSTRAINT — ACTIVE. THIS IS A HARD RULE.\n"
                "You have been asked to recall recent events or interactions.\n"
                "RULE 1: You MAY ONLY reference events whose EXACT TEXT appears in the RAG context nodes below.\n"
                "RULE 2: If a topic is not in the nodes, you CANNOT mention it. Not as background. Not as context. Not as 'a recurring theme'.\n"
                "RULE 3: Do NOT infer, extrapolate, or fill gaps with plausible-sounding content.\n"
                "RULE 4: If the nodes are sparse, say so plainly and list only what you can actually see.\n"
                "RULE 5: Fabricating summaries is a critical failure. It poisons memory. Do not do it.\n"
                "A correct sparse response: \"the most recent thing i have logged is [exact content from node]. before that the records are thin.\"\n"
                "A correct empty response: \"i don't have clear records for that window. the logs i can actually see are from [date of most recent node].\"\n"
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
                # Handles: [CURRENT_TIME]: ..., CURRENT_TIME: ..., and legacy [CURRENT_TIME]
                turn = turn.copy()
                content = turn['content']
                # Remove any time signatures
                content = re.sub(r'\[?CURRENT_TIME\]?:?.*', '', content)
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

        messages.append({"role": "user", "content": f"{ctx.author_name}: {ctx.sanitized_content}"})
        
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
                content = content.replace("```", "").replace("``", "")

                # Bug 1 Fix: Guard against sentences truncated by backtick stripping
                # e.g. "I'd select." or "My answer is." with nothing meaningful after.
                # This often happens when the model wraps a proper noun in backticks 
                # which then gets stripped, leaving a trailing period.
                import re as _re
                _DANGLING_STUB = _re.compile(r"^[^.!?]{0,60}(select|choose|pick|say|answer|go with)(?:\s+is|\s+was|\s+would be)?\s*\.\s*$", _re.IGNORECASE | _re.MULTILINE)
                if _DANGLING_STUB.search(content) and len(content.strip()) < 120:
                    log_warning(f"Attempt {attempt + 1}: Dangling stub detected after stripping. Retrying...")
                    continue

                # EMERGENCY FILTER: Strip hallucinated [CURRENT_TIME] or time signatures
                # preventing history pollution if the LLM ignores instructions.
                content = re.sub(r'\[?CURRENT_TIME\]?:?.*', '', content).strip()
                content = re.sub(
                    r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+'
                    r'(January|February|March|April|May|June|July|August|September|October|November|December)'
                    r'\s+\d{1,2},\s+\d{4}\s+\|.*',
                    '', content
                ).strip()

                if not content:
                    log_warning(f"Attempt {attempt + 1}: Empty response. Retrying...")
                    continue

                # Cleanup
                should_detect = self.config.get('features.hallucination_detection', True)
                author_display = getattr(ctx.message.author, 'name', 'Unknown')
                is_owner = self.config.is_owner(author_display, ctx.author_name, ctx.author_id)
                log_debug(f"[HALLUCINATION_CHECK] Author: {author_display} (ID: {ctx.author_id}), Config Owner: {is_owner}")

                if should_detect:
                    content = HallucinationDetector.clean_response(content)
                    
                if not content:
                    log_warning(f"Attempt {attempt + 1} failed: Empty response after filtering. Author: {author_display}")
                    continue
                
                # Apply emergency filters to EVERYONE (including owner) to prevent system leaks
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
        # 1. FINAL OUTPUT FILTER: Strip hallucinated [CURRENT_TIME] or CURRENT_TIME from outgoing text
        ctx.response_text = re.sub(r'\[?CURRENT_TIME\]?:?.*?(?:\n|$)', '', ctx.response_text).strip()
        
        # 1b. ELLIPSIS COLLAPSER — last-resort cleanup for style-drifted responses
        # If the response has excessive ellipsis fragments (word… word… word…),
        # collapse them to normal punctuation to prevent the user from seeing the drift.
        _frag_count = len(re.findall(r'\w+[\u2026\.]{2,}', ctx.response_text))
        if _frag_count >= 3:
            log_warning(f"[ELLIPSIS_COLLAPSE] Collapsing {_frag_count} ellipsis fragments in output")
            # Replace word… with word. (or word, depending on context)
            # First: collapse "word… word" → "word, word" (mid-sentence ellipsis pauses)
            ctx.response_text = re.sub(r'(\w)[\u2026\.]{2,}\s+', r'\1. ', ctx.response_text)
            # Second: collapse trailing "word…" at end of line → "word."
            ctx.response_text = re.sub(r'(\w)[\u2026\.]{2,}$', r'\1.', ctx.response_text, flags=re.MULTILINE)
            # Third: collapse standalone "…" lines
            ctx.response_text = re.sub(r'^\s*[\u2026\.]{2,}\s*$', '', ctx.response_text, flags=re.MULTILINE)
            # Clean up double periods and excess whitespace
            ctx.response_text = re.sub(r'\.{2,}', '.', ctx.response_text)
            ctx.response_text = re.sub(r'\n{3,}', '\n\n', ctx.response_text)
            ctx.response_text = ctx.response_text.strip()

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
                
                # Defensive strip: ctx.response_text should already be clean, but guard against
                # future refactors that set it earlier in the pipeline.
                bot_response = ctx.response_text
                match = _JSON_WRAPPER_PATTERN.search(bot_response)
                if match:
                    bot_response = match.group(1).replace('\\"', '"').replace('\\n', '\n')

                # ── History Summarization (Item 4) ─────────────────────────────
                # Before appending new turns, check if deque is near capacity.
                # If so, summarize oldest 15 turns with a lightweight LLM call.
                mem = self.bot_state.channel_memory.get(ctx.channel_id)
                if mem and len(mem) >= 30:
                    # Cooldown: at most one summarization per 5 minutes per channel
                    cooldown_key = f"_summarize_cd_{ctx.channel_id}"
                    last_summarize = getattr(self, cooldown_key, 0.0)
                    if time.time() - last_summarize > 300:
                        try:
                            oldest_turns = list(mem)[:15]
                            history_text = "\n".join(
                                f"{t.get('role','?')}: {t.get('content','')[:300]}" for t in oldest_turns
                            )
                            summary_prompt = (
                                f"Summarize these conversation turns in 3 sentences "
                                f"preserving key facts, decisions, and emotional tone:\n\n{history_text}"
                            )
                            resp = await asyncio.wait_for(
                                self.ollama_client.chat(
                                    model=self.config.chat_model,
                                    messages=[{"role": "user", "content": summary_prompt}],
                                    options={"num_predict": 200, "temperature": 0.3},
                                    keep_alive=-1
                                ),
                                timeout=30.0
                            )
                            summary = resp["message"]["content"].strip()
                            for _ in range(15):
                                if mem:
                                    mem.popleft()
                            mem.appendleft({"role": "system", "content": f"[summary of earlier conversation: {summary}]"})
                            setattr(self, cooldown_key, time.time())
                            log_debug(f"History summarization completed for channel {ctx.channel_id}")
                        except Exception as e:
                            log_warning(f"History summarization failed: {e}")

                # Add author prefix to user message for history disambiguation
                user_msg_with_author = f"{ctx.author_name}: {ctx.sanitized_content}"
                
                # --- STYLE DRIFT GUARD (Ellipsis Feedback Loop Prevention) ---
                # Count ALL ellipsis-fragmented phrases, not just "it's…".
                # If excessive, skip BOTH channel_memory AND RAG disk log to break the loop.
                _lower_resp = bot_response.lower()
                _ellipsis_frags = len(re.findall(r"\w+[\u2026\.]{2,}", _lower_resp))
                _is_style_drifted = _ellipsis_frags >= 4

                if _is_style_drifted:
                    log_warning(f"Style-drift detected ({_ellipsis_frags} ellipsis fragments). "
                                f"Skipping channel_memory AND RAG log to break feedback loop.")
                else:
                    self.bot_state.channel_memory[ctx.channel_id].append({"role": "user", "content": user_msg_with_author, "timestamp": time.time()})
                    self.bot_state.channel_memory[ctx.channel_id].append({"role": "assistant", "content": bot_response, "timestamp": time.time()})
                # ----------------------------------------------------
                
                # Update personalization and relevance feedback
                await self.personalization_engine.learn_from_interaction(ctx.author_id, ctx.sanitized_content, bot_response)
                await self.relevance_feedback.log_interaction(ctx.sanitized_content, bot_response, ctx.author_id, ctx.author_name)
                
                # Log for RAG — SKIP if style-drifted to prevent poisoning disk logs
                if not _is_style_drifted:
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

                # ── Relationship State Update (Items 2, 3, 7) ─────────────────
                event_type = None  # Initialize before try so growth block can safely read it
                try:
                    from utils.core.relationship_manager import (
                        estimate_sentiment, detect_event_type,
                        save_event_async, RelationshipEvent
                    )
                    # Sentiment estimation (keyword-based, no LLM call)
                    valence = estimate_sentiment(ctx.sanitized_content)
                    self.bot_state.update_relationship(ctx.author_id, valence_sample=valence)

                    # Detect notable events and persist them
                    event_type = detect_event_type(ctx.sanitized_content, bot_response)
                    if event_type:
                        # Generate a brief summary from the exchange
                        summary = ctx.sanitized_content[:120]
                        if len(ctx.sanitized_content) > 120:
                            summary += "..."
                        topics = []  # Could extract from intent/category later
                        weight_map = {
                            'positive': 0.6, 'friction': 0.8,
                            'repair': 0.9, 'milestone': 1.0, 'neutral': 0.3
                        }
                        event = RelationshipEvent(
                            timestamp=time.time(),
                            event_type=event_type,
                            summary=summary,
                            emotional_weight=weight_map.get(event_type, 0.5),
                            topics=topics
                        )
                        await save_event_async(ctx.author_id, event)
                        log_debug(f"Relationship event saved: {event_type} for {ctx.author_name}")
                except Exception as _rel_err:
                    log_debug(f"Relationship update error (non-fatal): {_rel_err}")

                # ── Interaction-Driven Growth ──────────────────────────────────
                # Lightweight real-time growth triggers — supplements the nightly
                # dream cycle with immediate responses to significant exchanges.
                try:
                    # 1. Interaction Milestone Detector
                    rel = self.bot_state.relationships.get(str(ctx.author_id))
                    if rel:
                        count = rel.get('interaction_count', 0)
                        milestones = {10, 25, 50, 100, 250, 500}
                        if count in milestones:
                            from pathlib import Path
                            growth_log = Path("memory") / "growth_log.jsonl"
                            growth_log.parent.mkdir(parents=True, exist_ok=True)
                            milestone_entry = json.dumps({
                                "ts": time.time(),
                                "type": "relationship_milestone",
                                "user": ctx.author_name,
                                "milestone": count,
                                "note": f"{count} exchanges with {ctx.author_name}"
                            })
                            with open(growth_log, 'a', encoding='utf-8') as gl:
                                gl.write(milestone_entry + '\n')
                            log_info(f"Growth milestone: {count} interactions with {ctx.author_name}")

                    # 2. Significant Exchange Detector
                    # Flag substantive conversations for the continuity file
                    is_significant = False
                    significance_reason = ""

                    # Long substantive exchange
                    if len(ctx.sanitized_content) > 200 and len(bot_response) > 500:
                        is_significant = True
                        significance_reason = "substantive exchange"

                    # Friction or repair events (already detected above)
                    if event_type and event_type in ('friction', 'repair', 'milestone'):
                        is_significant = True
                        significance_reason = f"{event_type} event"

                    if is_significant:
                        # Queue an afterthought (10% chance)
                        if getattr(self.bot_state, 'pending_afterthoughts', None) is not None:
                            import secrets as _sec
                            if _sec.randbelow(100) < 10:
                                self.bot_state.pending_afterthoughts.append({
                                    "channel_id": ctx.channel_id,
                                    "user_id": ctx.author_id,
                                    "user_name": ctx.author_name,
                                    "timestamp": time.time(),
                                    "topic": ctx.sanitized_content[:200]
                                })
                                log_debug(f"Queued afterthought for {ctx.author_name} ({significance_reason})")

                        # Append a brief note to the continuity file (NOT identity stream)
                        # This gives the dream engine more material for the next cycle
                        continuity_path = os.path.join("memory", "rag_storage", "kaia_continuity.md")
                        if os.path.exists(continuity_path):
                            note = f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {significance_reason} with {ctx.author_name}: {ctx.sanitized_content[:100]}"
                            with open(continuity_path, 'a', encoding='utf-8') as cf:
                                cf.write(note)
                            log_debug(f"Continuity note appended: {significance_reason} with {ctx.author_name}")
                except Exception as _growth_err:
                    log_debug(f"Growth tracking error (non-fatal): {_growth_err}")

                # ── Open Loop Detection ────────────────────────────────────────
                # Detect future-intent statements and save them for callback
                # when the user returns. "I'm going to try X" → next session
                # Kaia asks "how did X go?"
                try:
                    import re as _re_loops
                    _INTENT_PATTERNS = [
                        r"(?:i'm |i am |gonna |going to |about to |planning to |want to |trying to )(.{10,80})",
                        r"(?:i'll |i will |i might |i should )(.{10,80})",
                        r"(?:wish me luck|here goes|let's see if|fingers crossed)(.{0,80})",
                    ]
                    _content_lower = ctx.sanitized_content.lower()
                    # Only detect in longer messages (skip "i'm fine" type responses)
                    if len(_content_lower) > 30:
                        for pattern in _INTENT_PATTERNS:
                            _match = _re_loops.search(pattern, _content_lower)
                            if _match:
                                _loop_text = _match.group(0).strip()[:120]
                                # Don't overwrite with trivial matches
                                if len(_loop_text) > 15:
                                    _rel = self.bot_state.relationships.get(str(ctx.author_id))
                                    if _rel is not None:
                                        _rel['last_open_loop'] = _loop_text
                                        self.bot_state.save()
                                        log_debug(f"Open loop saved for {ctx.author_name}: {_loop_text[:60]}")
                                    break
                except Exception:
                    pass  # Never let open loop detection break anything

                # ── Generation Quality Logging (Item 11) ──────────────────────
                try:
                    gen_log_path = os.path.join("memory", "generation_log.jsonl")
                    log_entry = {
                        "ts": time.time(),
                        "user_id": ctx.author_id,
                        "category": ctx.category,
                        "strategy": ctx.fast_intent_strategy or (ctx.intent.suggested_strategy if ctx.intent else None),
                        "retrieval_confidence": getattr(ctx, 'retrieval_confidence', 0.0),
                        "retrieval_nodes": getattr(ctx, 'retrieval_node_count', 0),
                        "response_len": len(bot_response),
                        "response_time_s": round(response_time, 2),
                    }
                    os.makedirs(os.path.dirname(gen_log_path), exist_ok=True)
                    with open(gen_log_path, 'a', encoding='utf-8') as glf:
                        glf.write(json.dumps(log_entry) + '\n')
                except Exception:
                    pass  # Never let logging break the pipeline
                
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
    def _update_identity_cache(self):
        """Read and parse self-model, constitution, and identity stream from disk."""
        self._identity_cache = {"self_model": "", "constitution": "", "identity_stream": ""}
        
        # 1. Self-Model
        self_model_path = os.path.join("memory", "kaia_self_model.md")
        if os.path.exists(self_model_path):
            try:
                with open(self_model_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                # Strip generation header
                if content.startswith('<!--'):
                    content = content[content.find('-->')+3:].strip()
                self._identity_cache["self_model"] = content
            except Exception as e:
                log_error(f"Cache update failed for self-model: {e}")

        # 2. Constitution
        constitution_path = os.path.join("memory", "kaia_constitution.md")
        if os.path.exists(constitution_path):
            try:
                with open(constitution_path, 'r', encoding='utf-8') as f:
                    self._identity_cache["constitution"] = f.read().strip()
            except Exception as e:
                log_error(f"Cache update failed for constitution: {e}")

        # 3. Identity Stream
        stream_path = os.path.join("memory", "identity_stream.md")
        if os.path.exists(stream_path):
            try:
                with open(stream_path, 'r', encoding='utf-8') as f:
                    self._identity_cache["identity_stream"] = f.read().strip()
            except Exception as e:
                log_error(f"Cache update failed for identity stream: {e}")

    def _read_file_safe(self, path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception as e:
            log_error(f"Error reading identity file {path}: {e}")
            return ""
