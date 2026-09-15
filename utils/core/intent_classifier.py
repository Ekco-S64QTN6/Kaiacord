"""
Intent Classification & Model Warm Pool
=========================================

Extracted from kaia_intelligence.py (Phase 28 / CQ-01).

Contains:
- ModelWarmPool: Keep models warm between uses to prevent cold starts
- IntentParser: Advanced intent understanding engine with fast-path triggers and LLM analysis
- QueryClassifier: Legacy alias for IntentParser
"""

import time
import asyncio
import re
import json
from typing import Optional

from utils.infrastructure.logging.kaia_logger import (
    log_info, log_action, log_success, log_error, log_warning, log_debug
)
from utils.core.context_optimizer import Intent, ContextCtx

# Pre-compiled regex patterns used by IntentParser
RE_MD_JSON_BLOCK_START = re.compile(r'```json\s*')
RE_MD_BLOCK_BACKTICKS = re.compile(r'```')
RE_THINK_BLOCK = re.compile(r'<think>[\s\S]*?</think>')


class ModelWarmPool:
    """Keep models warm between uses to prevent cold starts."""
    def __init__(self, ollama_client):
        self.ollama_client = ollama_client
        self.pool = {}
        self._scheduler_task = None
        self._cached_options = {}  # model_name -> gpu_options (avoids re-instantiation)
        
    async def pre_warm(self, model_name):
        if not model_name: return
        if model_name in self.pool:
            self.pool[model_name]['last_used'] = time.time()
            return

        log_action(f"Adding {model_name} to keep-alive pool...")
        self.pool[model_name] = {'last_used': time.time()}
        
        # Initial warm.
        #
        # This loads a model into VRAM and pins it there (keep_alive=-1), so it
        # must go through the GPU guard like every other model load — otherwise
        # it can collide with an in-flight chat. It also needs a timeout: the
        # bare `except Exception: pass` below would swallow a hang completely.
        #
        # for_chat is False so a CPU-only model is not forced onto the GPU by
        # the warm-up. get_gpu_options(for_chat=True) returns num_gpu: 99
        # regardless of the model.
        try:
            from utils.infrastructure.gpu.gpu_manager import (
                OllamaGPUManager, gpu_memory_manager, GPUTaskPriority,
            )
            gpu_mgr = OllamaGPUManager(model_name)
            options = gpu_mgr.get_gpu_options(for_chat=False)

            async def _warm():
                return await self.ollama_client.generate(
                    model=model_name, prompt=".", options=options, keep_alive=-1
                )

            await gpu_memory_manager.run_with_gpu_guard(
                model_name=model_name,
                priority=GPUTaskPriority.BACKGROUND,
                coro=asyncio.wait_for(_warm(), timeout=120.0),
                task_id=f"warm_{model_name.replace(':', '_')}",
            )
        except Exception as e:
            log_warning(f"[ModelWarmPool] Warm-up of {model_name} failed: {e}")

        if not self._scheduler_task or self._scheduler_task.done():
            self._scheduler_task = asyncio.create_task(self._scheduler_loop())
            try:
                from utils.infrastructure.monitoring.async_task_registry import task_registry
                task_registry.register("model_warm_scheduler", self._scheduler_task)
            except Exception: pass
            
        # Execute tiny generation to force load into VRAM with full cache
        # Max 300s (5 mins) per attempt. If CPU is busy (e.g. embedding indexing),
        # retry once after a cooldown to let embeddings finish.
        max_attempts = 2
        try:
            from utils.infrastructure.system.yaml_config import config
            max_ctx = config.max_context_tokens
            # Load with full context size from config
            options = {
                "num_gpu": 99,
                "num_ctx": max_ctx,
                "num_predict": 1
            }
            # Cache these options for keep_alive reuse
            self._cached_options[model_name] = options.copy()
            
            for attempt in range(1, max_attempts + 1):
                try:
                    # Execute tiny generation to force load into VRAM with full cache
                    # Max 600s (10 mins) per attempt. If CPU is busy (e.g. embedding indexing),
                    # retry once after a cooldown to let embeddings finish.
                    await asyncio.wait_for(
                        self.ollama_client.generate(model=model_name, prompt=".", options=options, keep_alive=-1),
                        timeout=120.0  # Reduced from 600s
                    )
                    self.pool[model_name] = {'last_used': time.time(), 'status': 'ready'}
                    return True
                except asyncio.TimeoutError:
                    if attempt < max_attempts:
                        log_warning(f"Model {model_name} pre-warm timed out (attempt {attempt}/{max_attempts}). "
                                    f"CPU may be busy with embeddings. Retrying in 10s...")
                        await asyncio.sleep(10)
                    else:
                        log_error(f"CRITICAL FAILURE: Model {model_name} failed to pre-warm after {max_attempts} attempts (total ~12 min).")
                        return False
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            log_error(f"Failed to pre-warm model {model_name}: {e}")
            log_debug(f"Pre-warm details (Full Traceback):\n{error_details}")
            return False
    
    async def _scheduler_loop(self):
        """Centralized scheduler to keep all pooled models warm."""
        log_debug("Model warm pool scheduler started.")
        while self.pool:
            await asyncio.sleep(600) # Increased to 10m
            now = time.time()
            models_to_remove = []
            
            # Use list of keys to allow modification during iteration
            for model_name, info in list(self.pool.items()):
                idle_sec = now - info['last_used']
                # LRU Eviction: 30m idle
                if idle_sec > 1800:
                    log_info(f"Model {model_name} idle for 30m, stopping keep-alive.")
                    models_to_remove.append(model_name)
                    continue
                
                # Only tickle if idle for at least 5m
                if idle_sec < 300:
                    continue

                try:
                    from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager
                    gpu_mgr = OllamaGPUManager(model_name)
                    # For shared chat models in the pool, use full chat options
                    options = gpu_mgr.get_gpu_options(for_chat=True)
                    # Lighter: generate(prompt=".") instead of chat()
                    await self.ollama_client.generate(model=model_name, prompt=".", options=options, keep_alive=3600)
                    log_debug(f"Tickled model: {model_name}")
                except Exception as e:
                    log_warning(f"Failed to tickle {model_name}: {e}")
                    models_to_remove.append(model_name)
            
            for m in models_to_remove:
                if m in self.pool: del self.pool[m]
                
        log_debug("Model warm pool scheduler stopped (pool empty).")


class IntentParser:
    """
    Advanced Intent Understanding Engine. 
    Replaces simple classification with cognitive intent parsing.
    """
    

    def __init__(self, ollama_client=None, model=None, logger=None,
                 host="http://localhost:11434", timeout=120.0):
        """Regex intent matching. No model is loaded and none is called.

        The arguments are kept so existing call sites and tests keep working;
        they are ignored. This class used to hold an Ollama client, a
        `classification_model` (gemma2:2b), CPU option tuning and a pre-warm
        routine for a second LLM pass — `parse_intent` / `_analyze_with_llm` —
        that ran on every ambiguous message and whose verdict nothing ever
        read. `ctx.intent` was only ever assigned from `fast_parse`, so the
        model was pulled, warmed, held ~1.6 GB of host RAM and answered 135
        times in one production log, into the void.
        """
        self.logger = logger or log_info


        # LAYER 1: Fast Pattern Triggers (Precompiled for performance)
        self.fast_triggers = {}
        raw_triggers = {
            "SOCIAL_GREETING": [
                r"^\s*(<@!?\d+>\s*)?(kaia|hey kaia|hi kaia|hello kaia)[!?.,]*\s*$",
                r"^\s*(<@!?\d+>\s*)?(hi|hello|hey|greetings|sup|yo|hi there|hello there)[!?.,]*\s*$",
                r"^\s*(<@!?\d+>\s*)?(hi|hello|hey|greetings|sup|yo)\s+kaia[!?.,]*\s*$",
                r"^\s*(<@!?\d+>\s*)?kaia[!?.,]*$"
            ],
            "COMMAND_EXECUTION": [
                r"^\s*(kaia\s+)?(status|stats|ping|uptime|clear|reset|quip)\b",
                r"^\s*[!/](quip|news|dreams|cache)\b"
            ],
            "DREAM_RECALL": [
                r"\b(dream(s|t|ing)?|nightmare(s)?)\b",
                r"^\s*(kaia\s+)?what did you dream",
                r"^\s*(kaia\s+)?tell me about your dream",
                r"^\s*(kaia\s+)?any recent dreams"
            ],
            "PRECISE_RECALL": [
                r"^\s*(kaia\s+)?who (is|are|was|were|am) ",
                r"^\s*(kaia\s+)?what (is|are|was|were) ",
                r"\b(dossier on|tell me about|biography of|background on)\b",
                r"\b(mark|elara|thorne|jules|elias)\b"
            ],
            "DIAGNOSTIC_DEEP_DIVE": [
                r"\b(error|bug|fail|crash|exception|traceback|fix|broken|dogshit)\b",
                r"\b(logs?|status|restart|boot|system|debug)\b",
                r"\b(why is it slow|latency|lag|responsive|hang|lockup)\b"
            ],
            "RECAP_QUERY": [
                r"recap\b.*\b\d+\s*(hours?|days?|minutes?|hrs?)",
                r"what happened.{0,15}\blast\s+\d+\s*(hours?|days?|hrs?)",
                r"elaborate on the (past|last) \d+ (hours?|days?|hrs?)",
                r"\b(summary|overview|recap|rundown|digest)\s+(of\s+)?(the\s+)?(past|last)\s+\d+\s*(hours?|days?|minutes?|hrs?|weeks?)\b",
                r"\b(summary|overview|recap|rundown)\s+(of\s+)?(all\s+)?(user\s+)?(interactions?|conversations?|chat|activity|messages?|chatter)\b",
                r"\b(can|could|would)\s+(i|you)\s+(get|give|have)\s+(me\s+)?(a\s+)?(summary|recap|overview|rundown)\b",
                r"\b(summarize|recap)\b.*?\b(past|last)\s+\d+\s*(hours?|days?|minutes?|hrs?|weeks?)\b",
                r"\b(past|last)\s+\d+\s*(hours?|days?|hrs?)\s+(of\s+)?(chat|chatter|messages?|activity|interactions?|conversations?)\b",
                r"summarize (all\s+)?(user\s+)?(recent|the last|today'?s?|past)?\s*(interactions?|conversations?|chat|activity|messages?|chatter)",
                r"what have you been (doing|up to)",
                r"recall the last \d+",
                r"\b(get|give)\s+(me\s+)?a\s+recap\b",
                r"\brecap (the|this)?\s*(thread|conversation|chat|channel)\b",
                r"what('s| has| have) been (going on|happening)",
                r"what did (i|we|you|people|everyone) (miss|talk about)",
                r"catch me up",
                r"what'?s been said",
                # Channel-scoped recall — "anything aware of from kaia-opolis", "summary of #general chatter"
                r"\b(summary|recap|overview)\s+of\s+(#?\w[\w-]*|\<#\d+\>).*(chatter|chat|messages?|conversations?|activity)\b",
                r"(anything|something).{0,20}(aware of|know about|should know).{0,20}(from|in)\s+\w",
                r"(what|anything).{0,20}(going on|happening|discussed|said).{0,20}(in|from)\s+\w",
            ],
            "SUMMARIZATION": [
                r"^\s*(kaia\s+)?(summarize|summary of|digest|tl;?dr)\b",
                r"\b(give me a summary|brief on|overview of|breakdown of|tell me about the (?:file|article|doc|paper|whitepaper)|what does .*? say)\b",
                r"\b(can you|please|could you)\s+(summarize|give a summary|break down|explain the file)\b",
                r"\b(tell me about|what is in)\s+[\w\-]+?\.(?:md|txt|pdf|docx|json|yaml)\b",
            ],
            "SYNTHESIS_SCAN": [
                r"\b(headlines|current events|happening today|latest on)\b",
                r"^\s*(kaia\s+)?(what's the|any) news\b",
                r"^\s*(kaia\s+)?what's happening in the (world|news)\b",
                r"\b(anything new (with|about))\b",
                r"\b(latest updates?)\b"
            ],
            "TECH_INQUIRY": [
                r"\b(how do i|how to|explain|what is)\s+(python|nvidia|cuda|gpu|linux|terminal|code|script)\b",
                r"\b(command for|check usage|process list)\b"
            ]
        }
        
        for strategy, patterns in raw_triggers.items():
            self.fast_triggers[strategy] = [re.compile(p, re.IGNORECASE) for p in patterns]

        log_success("IntentParser initialized (regex fast-path only).")
    
    def fast_parse(self, query: str) -> Optional[Intent]:
        """Layer 1: Fast Pattern Detection"""
        query_lower = query.lower().strip()
        
        # Fast-path for explicit file/document review intent.
        # Fix #10: Only match explicit file-reference phrases and extensions to avoid
        # shadowing DIAGNOSTIC_DEEP_DIVE for queries like "check the log file" or
        # "check the error". Generic words like "file"/"doc" are intentionally excluded.
        _FILE_REVIEW_CUES = ["take a look at", "looked at", "read the", "seen the", "go over"]
        _FILE_EXTENSIONS = [".md", ".txt", ".pdf", ".docx"]
        # Compound noun phrases that unambiguously refer to a document (not a system file/log)
        _FILE_COMPOUND_PHRASES = ["research file", "research doc", "research report",
                                   "setup research", "setup file", "setup doc",
                                   "aquarium research", "planning doc", "planning report"]
        if any(phrase in query_lower for phrase in _FILE_REVIEW_CUES):
            if (any(ext in query_lower for ext in _FILE_EXTENSIONS)
                    or any(phrase in query_lower for phrase in _FILE_COMPOUND_PHRASES)):
                log_debug("Fast-path trigger: PRECISE_RECALL (file review request)")
                return Intent(
                    explicit_intent="file review request",
                    implied_needs=["knowledge retrieval"],
                    emotional_context="neutral",
                    temporal_focus="present",
                    relational_context="general",
                    suggested_strategy="PRECISE_RECALL",
                    confidence=0.80  # Lowered slightly to let LLM override if context differs
                )

        for strategy, patterns in self.fast_triggers.items():
            for compiled_re in patterns:
                if compiled_re.search(query_lower):
                    # Guard: SUMMARIZATION triggered by incidental phrases in long
                    # conversational messages (e.g. "overview of phylogenetics").
                    # Real summarization requests are short and directive.
                    if strategy == "SUMMARIZATION" and len(query_lower.split()) > 25:
                        log_debug(f"SUMMARIZATION trigger suppressed: message too long ({len(query_lower.split())} words)")
                        continue

                    log_debug(f"Fast-path trigger: {strategy}")
                    
                    temporal_focus = "past_recent" if strategy == "RECAP_QUERY" else "present_immediate"
                    
                    # Construct a basic Intent object from the trigger
                    return Intent(
                        explicit_intent=query,
                        implied_needs=["immediate_response"],
                        emotional_context="neutral",
                        temporal_focus=temporal_focus,
                        relational_context="direct_command" if "COMMAND" in strategy else "social_casual",
                        suggested_strategy=strategy,
                        confidence=1.0
                    )
        return None

QueryClassifier = IntentParser
