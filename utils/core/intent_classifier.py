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
        # for_chat is False so a CPU-only model (the gemma2:2b classifier) is
        # not forced onto the GPU by the warm-up. get_gpu_options(for_chat=True)
        # returns num_gpu: 99 regardless of the model.
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
    

    def __init__(self, ollama_client=None, model=None, logger=None, host="http://localhost:11434", timeout=120.0):
        from utils.infrastructure.system.yaml_config import config
        self.ollama_client = ollama_client
        self.host = host
        self.host_model = model or config.chat_model
        self.logger = logger or log_info
        self.timeout = timeout
        
        # Lazy client initialization if needed
        if self.ollama_client is None:
            try:
                import ollama
                self.ollama_client = ollama.AsyncClient(host=self.host, timeout=self.timeout)
            except ImportError:
                log_error("Ollama library not found. IntentParser will fail.")
        
        # Optimized options for analysis
        from utils.infrastructure.system.yaml_config import config
        from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager
        
        # LAYER 0: Classification Model Selection (Default to gemma2:2b on CPU)
        # Using a smaller model on CPU prevents GPU semaphore contention.
        self.classification_model = config.get('models.classification_model', 'gemma2:2b')
        self.use_gpu_for_classification = config.get('models.classification_on_gpu', False)
        
        # DEFENSIVE GUARD: Ensure config values are real types, not MagicMock objects
        # from test contamination (see: test_intent_fix.py sys.modules poisoning incident)
        if not isinstance(self.classification_model, str):
            log_warning(f"[IntentParser] classification_model is {type(self.classification_model).__name__}, falling back to 'gemma2:2b'")
            self.classification_model = 'gemma2:2b'
        if not isinstance(self.use_gpu_for_classification, bool):
            self.use_gpu_for_classification = False
        
        # [MEMORY OPTIMIZATION]: Intent analysis only needs the current query and 
        # minimal context. 
        # We cap this to the value in config (default 2048).
        classification_ctx = config.classification_context_tokens
        if not isinstance(classification_ctx, int):
            classification_ctx = 2048
        
        _num_thread = config.num_thread
        if not isinstance(_num_thread, int):
            _num_thread = 6
        
        # Get base options
        if self.use_gpu_for_classification:
            gpu_mgr = OllamaGPUManager(self.classification_model)
            self.classification_options = gpu_mgr.get_gpu_options(for_chat=True, num_ctx=classification_ctx)
        else:
            # CPU-only options
            self.classification_options = {
                "num_gpu": 0,
                "num_thread": _num_thread, # Utilize Ryzen 5 9600X cores
                "num_ctx": classification_ctx,
                "num_predict": 256,
                "temperature": 0.1,
                "top_p": 0.9
            }
        
        if self.use_gpu_for_classification:
            self.classification_options.update({
                "temperature": 0.1,
                "top_p": 0.9,
                "num_predict": 256
            })
        
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

        log_success(f"IntentParser initialized (Model: {self.classification_model})")
    
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

    async def parse_intent(self, query: str, context: Optional[ContextCtx] = None) -> Intent:
        """Main Entry Point: Analyze query into Intent Object"""
        
        # 1. Layer 1: Fast Path
        fast_intent = self.fast_parse(query)
        # If it's a Greeting, Command, or Summarization, return immediately.
        if fast_intent and fast_intent.suggested_strategy in ["SOCIAL_GREETING", "COMMAND_EXECUTION", "SUMMARIZATION"]:
             return fast_intent

        # 2. Layer 2: LLM Intent Analysis (with fast-path hint if available)
        hint = fast_intent.suggested_strategy if fast_intent else None
        
        # EXECUTION: If classification is on CPU, we BYPASS the GPU semaphore.
        # This allows classification to run while another task is generating.
        if not self.use_gpu_for_classification:
            log_debug(f"Executing CPU-based intent classification: {self.classification_model}")
            llm_intent = await self._analyze_with_llm(query, context, fast_path_hint=hint)
        else:
            from utils.infrastructure.gpu.gpu_manager import gpu_memory_manager, GPUTaskPriority
            
            llm_intent = await gpu_memory_manager.run_with_gpu_guard(
                model_name=self.classification_model,
                priority=GPUTaskPriority.CRITICAL,
                coro=self._analyze_with_llm(query, context, fast_path_hint=hint),
                task_id=f"intent_{int(time.time())}"
            )
        
        # 3. Layer 3: Strategy Merging (Cognitive Stabilization)
        # If the LLM confidence is low or it returned EXPLORATORY_DIALOGUE, 
        # while a specific fast-path hint exists, we trust the technical/specific hint.
        if hint and hint != "EXPLORATORY_DIALOGUE":
            if llm_intent.confidence < 0.7 or llm_intent.suggested_strategy == "EXPLORATORY_DIALOGUE":
                log_debug(f"Strategy Merge: Overriding LLM '{llm_intent.suggested_strategy}' with fast-path '{hint}'")
                llm_intent.suggested_strategy = hint
                # Don't overwrite confidence, as the merger itself might be a slightly fuzzy decision
                
        return llm_intent

    async def _analyze_with_llm(self, query: str, context: Optional[ContextCtx], fast_path_hint: Optional[str] = None) -> Intent:
        """Layer 2: Deep Analysis via LLM"""
        try:
            # Context string construction
            ctx_str = ""
            if context:
                ctx_str = f"Active Entities: {', '.join(context.active_entities)}\nLast Topic: {context.last_turns[-1] if context.last_turns else 'None'}"

            hint_str = f"\nFAST_PATH_HINT: {fast_path_hint} (Use this as a strong indicator if it matches the content)\n" if fast_path_hint else ""

            prompt = (
                "SYSTEM: You are an Intent Analysis Engine. JSON OUTPUT ONLY.\n"
                "{\n"
                "  \"explicit_intent\": \"literal meaning\",\n"
                "  \"implied_needs\": [\"need1\", \"need2\"],\n"
                "  \"emotional_context\": \"neutral|urgent|frustrated\",\n"
                "  \"temporal_focus\": \"present_immediate\",\n"
                "  \"relational_context\": \"general\",\n"
                "  \"confidence\": 0.0 to 1.0,\n"
                "  \"suggested_strategy\": \"PRECISE_RECALL|DIAGNOSTIC_DEEP_DIVE|DREAM_RECALL|CREATIVE_ASSOCIATION|RELATIONAL_MIRROR|SYNTHESIS_SCAN|EXPLORATORY_DIALOGUE|SUMMARIZATION\"\n"
                "}\n\n"
                "suggested_strategy must be one of: PRECISE_RECALL|DIAGNOSTIC_DEEP_DIVE|DREAM_RECALL|"
                "CREATIVE_ASSOCIATION|RELATIONAL_MIRROR|SYNTHESIS_SCAN|EXPLORATORY_DIALOGUE|SUMMARIZATION\n"
                f"{hint_str}"
                f"CONTEXT: {ctx_str[:200]}\n"
                f"QUERY: \"{query}\"\n/no_think\nJSON:"
            )


            # EXECUTION: The GPU guard/routing is now handled entirely in the parent parse_intent()
            # method. This child method is a "dumb" executor to avoid re-entrant deadlock.
            from utils.infrastructure.system.yaml_config import config
            response = await asyncio.wait_for(
                self.ollama_client.chat(
                    model=self.classification_model,
                    messages=[{"role": "user", "content": prompt}],
                    options=self.classification_options
                ),
                timeout=config.classification_timeout
            )
            
            raw_json = response['message']['content'].strip()
            
            if not raw_json:
                log_warning(f"Intent classifier returned empty response.")
                raise json.JSONDecodeError("Empty response from classifier", "", 0)
            
            clean_json = await self._repair_json(raw_json)
            try:
                data = json.loads(clean_json)
            except json.JSONDecodeError as jde:
                log_error(f"Intent Analysis JSON Error: {jde}. Raw Content: {raw_json[:200]}...")
                raise jde
            
            return Intent(
                explicit_intent=data.get('explicit_intent', query),
                implied_needs=data.get('implied_needs', []),
                emotional_context=data.get('emotional_context', 'neutral'),
                temporal_focus=data.get('temporal_focus', 'present_immediate'),
                relational_context=data.get('relational_context', 'general'),
                suggested_strategy=data.get('suggested_strategy', 'EXPLORATORY_DIALOGUE'),
                confidence=float(data.get('confidence', 0.85))
            )

        except Exception as e:
            err_msg = str(e).lower()
            if isinstance(e, TimeoutError):
                from utils.infrastructure.system.yaml_config import config
                log_warning(f"Intent Analysis timed out after {config.classification_timeout}s. Falling back to fast-path/default.")
            elif "no json in thinking field" in err_msg:
                # Expected fallback case when model ignores /no_think.
                # Already logged as warning in _analyze_with_llm.
                pass
            elif "out of memory" in err_msg or "cudamalloc" in err_msg or "terminat" in err_msg:
                log_error(f"Intent Analysis CRITICAL OOM: {e}. Falling back to fast-path/default.")
            else:
                import traceback
                err_display = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
                log_error(f"Intent Analysis Failed: {err_display}")
                log_debug(f"Intent Analysis Traceback:\n{traceback.format_exc()}")
            
            # Fallback Intent
            # If we have a hint from the fast-path regex, use it. Otherwise, default.
            strategy = fast_path_hint if fast_path_hint else "EXPLORATORY_DIALOGUE"
            
            return Intent(
                explicit_intent=query,
                implied_needs=["emergency fallback"],
                emotional_context="neutral",
                temporal_focus="present_immediate",
                relational_context="general",
                suggested_strategy=strategy,
                confidence=0.5
            )

    async def _repair_json(self, text: str) -> str:
        """Attempt to repair broken JSON from LLM output using precompiled regex."""
        # Remove think blocks and markdown code blocks if present
        text = RE_THINK_BLOCK.sub('', text)
        text = RE_MD_JSON_BLOCK_START.sub('', text)
        text = RE_MD_BLOCK_BACKTICKS.sub('', text).strip()
        
        if hasattr(self, '_json_repairs'):
            for p, r in self._json_repairs:
                text = p.sub(r, text)
        
        # Find first { and last } to ensure valid JSON structure
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            return text[start:end+1]
        return text

    async def pre_warm(self):
        """Pre-warm the model with a direct call. Pulls the model if missing."""
        log_action(f"Pre-warming IntentParser model: {self.classification_model}...")
        try:
            # 1. Check if model exists
            model_exists = False
            try:
                await self.ollama_client.show(model=self.classification_model)
                model_exists = True
            except Exception as e:
                if "404" in str(e) or "not found" in str(e).lower():
                    log_warning(f"Model {self.classification_model} not found in Ollama. Attempting to pull...")
                else:
                    raise e

            # 2. Pull if missing
            if not model_exists:
                log_action(f"📥 Pulling {self.classification_model} — this may take a few minutes...")
                async for progress in self.ollama_client.pull(model=self.classification_model, stream=True):
                    if hasattr(progress, 'status'):
                        status = progress.status
                        if "downloading" not in status.lower() or "100%" in status:
                             log_info(f"  [Pull] {status}")
                    elif isinstance(progress, dict) and 'status' in progress:
                        status = progress['status']
                        if "downloading" not in status.lower() or "100%" in status:
                             log_info(f"  [Pull] {status}")
                log_success(f"✅ Successfully pulled {self.classification_model}")

            # [BUG FIX]: name 'config' is not defined
            from utils.infrastructure.system.yaml_config import config
            
            # 3. Warming (Respect configuration for GPU/CPU and residency)
            log_action(f"🔥 Warming {self.classification_model} ({'GPU' if self.use_gpu_for_classification else 'CPU'})...")
            
            # Use appropriate residency: -1 (infinite) if we want it to stay resident, 
            # or 0 if we want it to unload immediately.
            keep_alive = -1 if self.use_gpu_for_classification or config.get('models.classification_stay_resident', True) else 0
            
            options = self.classification_options.copy()
            # Ensure the pre-warm call matches the intended device
            options["num_gpu"] = 99 if self.use_gpu_for_classification else 0
            
            await asyncio.wait_for(
                self.ollama_client.generate(
                    model=self.classification_model,
                    prompt=".",
                    options=options,
                    keep_alive=keep_alive
                ),
                timeout=180.0
            )
            log_success(f"IntentParser model {self.classification_model} warmed ({'GPU' if self.use_gpu_for_classification else 'CPU'}).")
        except Exception as e:
            import traceback
            log_error(f"IntentParser pre-warm failed: {type(e).__name__}: {e}")
            log_debug(f"IntentParser Pre-warm Traceback:\n{traceback.format_exc()}")

# Legacy Alias for Refactor Compatibility
QueryClassifier = IntentParser
