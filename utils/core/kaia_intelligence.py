import time
import os
import asyncio
import numpy as np
import re
import json
import hashlib
import traceback
import threading
from datetime import datetime
from collections import defaultdict
from ollama import Client
from llama_index.embeddings.ollama import OllamaEmbedding
from utils.infrastructure.logging.kaia_logger import log_info, log_action, log_success, log_error, log_warning, log_debug
from dataclasses import dataclass, field
from typing import List, Optional, Dict

@dataclass
class Intent:
    explicit_intent: str
    implied_needs: List[str]
    emotional_context: str
    temporal_focus: str
    relational_context: str
    suggested_strategy: str
    confidence: float

@dataclass
class ContextCtx:
    last_turns: List[str] = field(default_factory=list)
    active_entities: List[str] = field(default_factory=list)
    user_role: str = "user"
    system_state: str = "active"

# NOTE: config is imported lazily in ContextOptimizer.__init__ to avoid circular import

# PerformanceMonitor and SemanticCache have been moved to dedicated utility modules.
# Semantic cache was removed (never worked reliably). Caching is decommissioned.

class ModelWarmPool:
    """Keep models warm between uses to prevent cold starts."""
    def __init__(self, ollama_client):
        self.ollama_client = ollama_client
        self.pool = {}
        self.keep_alive_tasks = {}
        self._cached_options = {}  # model_name -> gpu_options (avoids re-instantiation)
        
    async def pre_warm(self, model_name):
        if model_name in self.pool:
            self.pool[model_name]['last_used'] = time.time()
            return True
            
        log_action(f"Pre-warming model: {model_name}...")
        try:
            # Load with FULL context size - allows first message to be instant
            from utils.infrastructure.system.yaml_config import config
            max_ctx = config.max_context_tokens
            options = {
                "num_gpu": -1,
                "num_ctx": max_ctx,
                "num_predict": 1
            }
            # Cache these options for keep_alive reuse
            self._cached_options[model_name] = options.copy()
            # Execute tiny generation to force load into VRAM with full cache
            await self.ollama_client.generate(model=model_name, prompt=".", options=options, keep_alive=3600)
            self.pool[model_name] = {'last_used': time.time(), 'status': 'ready'}
            if model_name not in self.keep_alive_tasks:
                self.keep_alive_tasks[model_name] = asyncio.create_task(self.keep_alive(model_name))
            return True
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            log_error(f"Failed to pre-warm model {model_name}: {e}")
            log_debug(f"Pre-warm failure details:\n{error_details}")
            return False
    
    async def keep_alive(self, model_name):
        while True:
            await asyncio.sleep(300)
            if model_name not in self.pool: break
            if time.time() - self.pool[model_name]['last_used'] > 1800:
                log_info(f"Model {model_name} idle for 30m, stopping keep-alive.")
                del self.pool[model_name]
                break
            try:
                # Reuse cached GPU options (set during pre_warm) to avoid re-instantiation
                options = self._cached_options.get(model_name, {'num_predict': 1})
                await self.ollama_client.chat(model=model_name, messages=[{"role": "user", "content": "ping"}], options=options)
            except Exception:
                if model_name in self.pool: del self.pool[model_name]
                break

class ContextOptimizer:
    """Model-aware token allocation and context trimming."""
    def __init__(self, model_name="gemma3:12b", max_tokens=None):
        # Lazy import to avoid circular import during module loading
        from utils.infrastructure.system.yaml_config import config
        
        self.model_name = model_name
        # Use config as single source of truth if not explicitly provided
        self.max_tokens = max_tokens if max_tokens is not None else config.max_context_tokens
        # Token estimation multiplier (configurable for different languages/content types)
        self.token_multiplier = config.token_multiplier
        # Reserved tokens for system reinforcement rules
        self.system_reserve = config.system_reserve_tokens
        # Optimal ratios for different models
        self.ratios = {
            'gemma3:12b': {'persona': 0.10, 'rag': 0.50, 'history': 0.35, 'system': 0.05},
            'llama3.2': {'persona': 0.15, 'rag': 0.45, 'history': 0.35, 'system': 0.05},
            'default': {'persona': 0.10, 'rag': 0.50, 'history': 0.30, 'system': 0.10}
        }
        self.min_rag_tokens = config.min_rag_tokens if hasattr(config, 'min_rag_tokens') else 1024
        self.min_history_tokens = 512
        self.summarization_tokens = config.summarization_context_tokens
        
    def optimize_context(self, category, persona, rag_nodes, history, strategy=None):
        """
        Optimize context by treating the persona as a non-negotiable anchor.
        PERSONA IS NEVER TRUNCATED.
        """
        # 1. Determine Effective Token Limit (Dynamic scaling for Summarization)
        effective_max_tokens = self.max_tokens
        if strategy == "SUMMARIZATION":
            effective_max_tokens = self.summarization_tokens # Boost for full transcript processing (Safe for 12GB VRAM)
            log_info(f"Summarization strategy detected. Boosting context window to {effective_max_tokens} tokens.")

        # 2. Persona is non-negotiable - calculate its actual cost first
        optimized_persona = persona 
        persona_tokens = len(persona.split()) * self.token_multiplier
        
        # 3. Reserve tokens for system reinforcement (configurable)
        system_reserve = self.system_reserve
        
        # 4. Calculate remaining budget for RAG and History
        remaining_budget = effective_max_tokens - persona_tokens - system_reserve
        
        # 5. Handle emergency budget depletion
        if remaining_budget < (self.min_rag_tokens + self.min_history_tokens):
            # Persona is massive. Give RAG and History absolute minimums.
            # We might exceed budget slightly, but content integrity (Persona) is priority.
            log_warning(f"Persona is massive ({persona_tokens:.0f} tokens). RAG/History prioritized at minimums.")
            rag_budget = self.min_rag_tokens
            history_budget = self.min_history_tokens
        else:
            # Allocate remainder based on model ratios
            model_ratios = self.ratios.get(self.model_name, self.ratios['default']).copy()
            
            # Rebalance weights for RAG and History only
            if strategy == "SUMMARIZATION":
                # For summarization, we want almost ALL RAG. History is irrelevant.
                rag_weight = 0.95
                hist_weight = 0.05
            else:
                rag_weight = model_ratios['rag']
                hist_weight = model_ratios['history']
                
            total_weight = rag_weight + hist_weight
            
            rag_budget = int((rag_weight / total_weight) * remaining_budget)
            history_budget = int((hist_weight / total_weight) * remaining_budget)
            
            # Ensure minimums
            rag_budget = max(rag_budget, self.min_rag_tokens)
            history_budget = max(history_budget, self.min_history_tokens)

        token_budget = {
            'persona': int(persona_tokens),
            'rag': rag_budget,
            'history': history_budget
        }
        
        # Group and label RAG nodes by source type for structural attribution
        history_nodes = []
        reference_nodes = []
        news_nodes = []
        
        from utils.core.rag_utils import get_node_text, get_node_metadata
        for n in rag_nodes:
            content_raw = get_node_text(n)
            metadata = get_node_metadata(n)
            
            source_type = metadata.get('source_type', '')
            user_name = metadata.get('user_name', '').upper()
            path_raw = metadata.get('file_path', '')
            path = path_raw.lower()
            
            # COMPOSITE NODE SPLITTING (Specifically for Dream Interactions)
            if "## original fragment" in content_raw.lower() and "## kaia's reflection" in content_raw.lower():
                # Split the composite node
                content_lower = content_raw.lower()
                orig_start = content_lower.find("## original fragment")
                refl_start = content_lower.find("## kaia's reflection")
                
                # Extract sections
                original_fragment = content_raw[orig_start:refl_start].strip()
                kaia_reflection = content_raw[refl_start:].strip()
                
                # Clean up "## Original Fragment" header for external record
                original_fragment = re.sub(r"## Original Fragment\s*", "", original_fragment, flags=re.IGNORECASE)
                
                # Try to extract the source from the header if possible
                file_origin = os.path.basename(path_raw or 'Dream Source')
                source_match = re.search(r"Source:\s*(.+)", original_fragment, re.IGNORECASE)
                if source_match:
                    file_origin = os.path.basename(source_match.group(1).strip())
                    original_fragment = re.sub(r"Source:\s*.+", "", original_fragment, flags=re.IGNORECASE).strip()
                
                # Add Original Fragment as RECORDED KNOWLEDGE
                wrapped_orig = f"<recorded_knowledge source=\"{file_origin}\">\n{original_fragment}\n</recorded_knowledge>"
                reference_nodes.append(wrapped_orig)
                
                # Add Kaia's Reflection as LIVED EXPERIENCE
                kaia_reflection = re.sub(r"## Kaia's Reflection\s*", "", kaia_reflection, flags=re.IGNORECASE).strip()
                history_nodes.append(f"[INTERNAL REFLECTION (DREAM)]\n{kaia_reflection}")
                continue

            # Standard Logic for non-composite nodes
            is_log = source_type in ['logs', 'user_logs', 'user_profile'] or "user_logs" in path
            is_reflection = "interactions/" in path or "reflections/" in path
            is_persona = source_type == 'persona' or "kaia_persona" in path
            is_source_dream = "injected/" in path or "books/" in path
            
            # Decide if it's Lived Experience or Learned Knowledge
            if (is_log or is_persona or is_reflection) and not is_source_dream:
                type_label = "CONVERSATION HISTORY"
                if "kaia_dreams" in path: type_label = "INTERNAL REFLECTION (DREAM)"
                elif is_persona: type_label = "IDENTITY CORE"
                elif user_name: type_label += f": {user_name}"
                history_nodes.append(f"[{type_label}]\n{content_raw}")
            elif source_type == 'news' or "news" in path:
                news_nodes.append(f"[EXTERNAL NEWS]\n{content_raw}")
            else:
                # Learned Knowledge - Isolated Records (Books, Injected Dream Sources, etc)
                file_name = os.path.basename(path_raw or 'Library')
                source_label = file_name
                
                # IMPROVEMENT: If it's a forum thread, make the source more readable
                if "thread_" in file_name.lower() and "_" in file_name:
                    parts = file_name.split("_")
                    if len(parts) >= 3:
                        thread_id = parts[1]
                        # Extract slug and convert to Title Case
                        slug = parts[2].replace(".md", "").replace("-", " ")
                        title = slug.title()
                        source_label = f"Thread: '{title}' (ID: {thread_id})"
                
                # Structural isolation wrapping with semantic tagging
                wrapped_content = f"<recorded_knowledge source=\"{source_label}\">\n{content_raw}\n</recorded_knowledge>"
                reference_nodes.append(wrapped_content)
                

        # Construct final RAG text with structural grouping
        rag_segments = []
        if history_nodes:
            rag_segments.append("### YOUR SAVED CONVERSATIONS & PERSONAL NOTES\n" + "\n---\n".join(history_nodes))
        if news_nodes:
            rag_segments.append("### RECENT REPORTS & ARTICLES YOU HAVE READ\n" + "\n---\n".join(news_nodes))
        if reference_nodes:
            rag_segments.append("### DOCUMENTS, BOOKS & SAVED FILES YOU HAVE READ\n" + "\n---\n".join(reference_nodes))
            
        rag_text = "\n\n".join(rag_segments)
        optimized_rag = self.trim_to_tokens(rag_text, token_budget['rag'])
        
        history_text = ""
        if isinstance(history, list):
            for msg in history:
                if isinstance(msg, dict):
                    history_text += f"{msg.get('role', 'user')}: {msg.get('content', '')}\n"
                else:
                    history_text += str(msg) + "\n"
        else:
            history_text = str(history)
        optimized_history = self.trim_to_tokens(history_text, token_budget['history'])
        
        return {
            'persona': optimized_persona,
            'rag': optimized_rag,
            'history': optimized_history,
            'tokens_saved': self.max_tokens - (len(optimized_persona.split()) + len(optimized_rag.split()) + len(optimized_history.split())) * self.token_multiplier
        }
    
    def trim_to_tokens(self, text, max_tokens):
        if not text: return ""
        words = text.split()
        if len(words) * self.token_multiplier <= max_tokens: return text
            
        lines = text.split('\n')
        important_lines = [l for l in lines if any(marker in l.lower() for marker in ['###', 'important:', 'core:', 'rule:'])]
        important_tokens = sum(len(l.split()) * self.token_multiplier for l in important_lines)
        remaining_tokens = max_tokens - important_tokens
        
        if remaining_tokens <= 0: 
            return '\n'.join(important_lines[:5]) if important_lines else ' '.join(words[:int(max_tokens/self.token_multiplier)])
            
        regular_lines = []
        for line in reversed(lines):
            if line not in important_lines:
                line_tokens = len(line.split()) * self.token_multiplier
                if line_tokens <= remaining_tokens:
                    regular_lines.insert(0, line)
                    remaining_tokens -= line_tokens
                else: 
                    # If we still have room but the line is too big, take a chunk of it
                    if remaining_tokens > 100:
                        chunk = ' '.join(line.split()[:int(remaining_tokens/self.token_multiplier)])
                        regular_lines.insert(0, chunk)
                    break
        
        result = '\n'.join(important_lines + regular_lines)
        if not result and words:
            return ' '.join(words[:int(max_tokens/self.token_multiplier)])
        return result

class RelevanceFeedback:
    """Learn from user interactions to improve retrieval."""
    def __init__(self, rag):
        self.rag = rag
        self.feedback_log = []
        
    async def log_interaction(self, query, response, user_id, user_name="Unknown"):
        # ECHO CHAMBER PROTECTION: Don't log generic "what's new" or status queries
        # as synthetic RAG documents, as they create a feedback loop.
        query_lower = query.lower()
        blacklist = ["what's new", "whats new", "what have you", "learned", "status", "info", "uptime", "stats", "how are you"]
        if any(trigger in query_lower for trigger in blacklist):
            return
            
        self.feedback_log.append({'query': query, 'response': response, 'user_id': user_id, 'user_name': user_name, 'timestamp': time.time()})
        if len(self.feedback_log) >= 50: await self.process_feedback()
            
    async def process_feedback(self):
        log_action("Processing relevance feedback to improve RAG...")
        recent_pairs = self.feedback_log[-50:]
        self.feedback_log = []
        
        from llama_index.core import Document
        synthetic_docs = []
        for item in recent_pairs:
            doc = Document(
                text=f"User Query: {item['query']}\nKaia Response: {item['response']}",
                metadata={'source': 'feedback', 'type': 'successful_qa', 'user_id': str(item['user_id']), 'user_name': item.get('user_name', 'Unknown'), 'timestamp': item['timestamp']}
            )
            synthetic_docs.append(doc)
            
        if synthetic_docs:
            try:
                for doc in synthetic_docs:
                    await asyncio.to_thread(self.rag.indices['logs'].insert, doc)
                log_success(f"Added {len(synthetic_docs)} feedback nodes to RAG.")
            except Exception as e:
                log_error(f"Error adding feedback to RAG: {e}")

class PersonalizationEngine:
    """Learn user preferences and adapt responses."""
    def __init__(self):
        self.user_profiles = {} # user_id -> {traits}
        
    async def get_user_traits(self, user_id):
        return self.user_profiles.get(str(user_id), {
            'conciseness': 0.5,
            'technicality': 0.5,
            'formality': 0.5,
            'humor': 0.5
        })

    def adapt_prompt(self, system_prompt, traits):
        """Persona is the anchor. No hardcoded ad-hoc adaptations."""
        return system_prompt

    async def learn_from_interaction(self, user_id, query, response):
        """Update user profile based on interaction characteristics."""
        u_id_str = str(user_id)
        canonical_id = u_id_str
        
        # Identity Unification
        try:
            from utils.social.kaia_identities import registry
            if u_id_str.startswith("forum_"):
                fid_parts = u_id_str.rsplit("_", 1)
                if len(fid_parts) > 1 and fid_parts[1].isdigit():
                    did = registry.get_discord_id(int(fid_parts[1]))
                    if did: canonical_id = did
            elif u_id_str.isdigit() and len(u_id_str) < 15:
                did = registry.get_discord_id(int(u_id_str))
                if did: canonical_id = did
        except Exception:
            pass # Fallback to original ID if registry fails

        traits = await self.get_user_traits(canonical_id)
        
        # Simple heuristics for learning
        word_count = len(response.split())
        
        # Conciseness: if user gets long responses and doesn't complain, maybe they like them?
        # Or if they ask short questions, they might want short answers.
        query_len = len(query.split())
        
        # EMA update
        # 0.5 is the "balanced" sweet spot. < 0.3 is yapping. > 0.7 is terse.
        target_conciseness = 0.6 if query_len < 4 else 0.4
        traits['conciseness'] = 0.9 * traits['conciseness'] + 0.1 * target_conciseness
        
        # Technicality: detect technical keywords in query
        tech_keywords = ['how', 'why', 'code', 'implement', 'system', 'architecture', 'error', 'bug', 'terminal', 'logs']
        has_tech = any(kw in query.lower() for kw in tech_keywords)
        target_tech = 0.8 if has_tech else 0.4
        traits['technicality'] = 0.9 * traits['technicality'] + 0.1 * target_tech
        
        self.user_profiles[user_id] = traits
        log_info(f"Updated personalization for {user_id}: C={traits['conciseness']:.2f}, T={traits['technicality']:.2f}")

class PersistentStateManager:
    """Save and load system state to survive restarts."""
    def __init__(self, state_dir="./memory/state"):
        self.state_dir = state_dir
        os.makedirs(state_dir, exist_ok=True)
        self.state_path = os.path.join(self.state_dir, "kaia_state.json")
        
    async def save_state_async(self, personalization, monitor, cache=None):
        """Async wrapper for save_state."""
        await asyncio.to_thread(self.save_state, personalization, monitor, cache)

    def save_state(self, personalization, monitor, cache=None):
        """Atomic save of critical state (Thread-safe synchronous version)."""
        try:
            state = {
                'user_profiles': personalization.user_profiles.copy(),
                'performance_metrics': {
                    'cache_hits': monitor.metrics.get('cache_hits', 0),
                    'cache_misses': monitor.metrics.get('cache_misses', 0),
                    'exact_hits': monitor.metrics.get('exact_hits', 0)
                },
                'saved_at': time.time()
            }
            
            if cache:
                state['exact_cache'] = getattr(cache, 'exact_cache', {}).copy()
                state['full_cache'] = getattr(cache, 'cache', {}).copy()
            
            # Delta check: only save if content actually changed
            current_state_str = json.dumps(state, sort_keys=True)
            current_hash = hashlib.sha256(current_state_str.encode()).hexdigest()
            if hasattr(self, '_last_state_hash') and current_hash == self._last_state_hash:
                return
            self._last_state_hash = current_hash

            temp_path = self.state_path + ".tmp"
            with open(temp_path, 'w') as f:
                f.write(current_state_str)
            os.replace(temp_path, self.state_path)
            log_success("Cold state persisted successfully.")
        except Exception as e:
            log_error(f"Failed to save state: {e}")

    async def load_state_async(self, personalization, monitor, cache=None):
        """Async wrapper for load_state."""
        return await asyncio.to_thread(self.load_state, personalization, monitor, cache)

    def load_state(self, personalization, monitor, cache=None):
        """Load state if not too stale (Thread-safe synchronous version)."""
        if not os.path.exists(self.state_path): return False
        
        try:
            with open(self.state_path, 'r') as f:
                state = json.load(f)
            
            # 24h stale check
            if time.time() - state.get('saved_at', 0) > 86400:
                log_warning("Persisted state is too old (>24h), skipping.")
                return False
                
            personalization.user_profiles.update(state.get('user_profiles', {}))
            
            metrics = state.get('performance_metrics', {})
            monitor.metrics['cache_hits'] = metrics.get('cache_hits', 0)
            monitor.metrics['cache_misses'] = metrics.get('cache_misses', 0)
            monitor.metrics['exact_hits'] = metrics.get('exact_hits', 0)
            
            if cache:
                if hasattr(cache, 'cache') and isinstance(cache.cache, dict):
                    cache.cache.update(state.get('full_cache', {}))
                if hasattr(cache, 'exact_cache') and isinstance(cache.exact_cache, dict):
                    cache.exact_cache.update(state.get('exact_cache', {}))
            
            log_success(f"Loaded cold state: {len(personalization.user_profiles)} profiles.")
            return True
        except Exception as e:
            log_error(f"Failed to load state: {e}")
            return False

class IntelligentCacheInvalidator:
    """Invalidate cache entries when source files change."""
    def __init__(self, cache):
        self.cache = cache
        self.file_query_map = defaultdict(set) # file_path -> {queries}
        
    def track(self, query, nodes):
        """Track which files contributed to a query."""
        files = set()
        for node in nodes:
            # Handle both llama_index nodes and raw strings
            metadata = getattr(node, 'metadata', {})
            file_path = metadata.get('file_path') or metadata.get('file_name')
            if file_path:
                files.add(file_path)
        
        for file_path in files:
            self.file_query_map[file_path].add(query)
            
    def invalidate_for_file(self, file_path):
        """Invalidate all queries associated with a file."""
        queries = self.file_query_map.get(file_path, set())
        count = 0
        for query in list(queries):
            exact_removed = self.cache.invalidate_exact(query)
            semantic_removed = self.cache.invalidate_semantic_by_query(query)
            if exact_removed or semantic_removed:
                count += 1
        
        if count > 0:
            log_info(f"Invalidated {count} cache entries due to change in {file_path}")
            del self.file_query_map[file_path]


class ContextWeaver:
    """
    Constructs rich ContextCtx objects from raw bot state.
    Bridges the gap between raw message history and semantic context.
    """
    
    @staticmethod
    def weave(channel_memory: List[Dict[str, str]], active_entity_registry=None) -> ContextCtx:
        """
        Create a ContextCtx object from history.
        
        Args:
            channel_memory: List of dicts {'role': str, 'content': str}
            active_entity_registry: Optional reference to an entity tracking system
        """
        # Extract last turns (Limit to 5 for relevance)
        last_turns = []
        if channel_memory:
            # Get last 5 turns
            recent = list(channel_memory)[-5:]
            for msg in recent:
                if isinstance(msg, dict):
                    role = msg.get('role', 'unknown').capitalize()
                    content = msg.get('content', '')
                else:
                    role = 'System'
                    content = str(msg)
                    
                # Truncate for token efficiency in the Intent prompt
                snippet = (content[:150] + '...') if len(content) > 150 else content
                last_turns.append(f"{role}: {snippet}")
        
        # TODO: Implement active entity extraction from EntityRegistry when available
        active_entities = []

        return ContextCtx(
            last_turns=last_turns,
            active_entities=active_entities,
            user_role="user",
            system_state="active"
        )

class IntentParser:
    """
    Advanced Intent Understanding Engine. 
    Replaces simple classification with cognitive intent parsing.
    """
    

    def __init__(self, ollama_client=None, model="gemma3:12b", logger=None, host="http://localhost:11434", timeout=15.0):
        self.ollama_client = ollama_client
        self.host_model = model
        self.logger = logger or log_info
        self.timeout = timeout
        
        # Optimized options for analysis
        from utils.infrastructure.system.yaml_config import config
        from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager
        
        # LAYER 0: Classification Model Selection (Default to gemma2:2b on CPU)
        # Using a smaller model on CPU prevents GPU semaphore contention.
        self.classification_model = config.get('models.classification_model', 'gemma2:2b')
        self.use_gpu_for_classification = config.get('models.classification_on_gpu', False)
        
        # [MEMORY OPTIMIZATION]: Intent analysis only needs the current query and 
        # minimal context. Requesting 24k tokens (default) triggers massive VRAM/RAM 
        # allocation that can cause OOM/cudaMalloc failures even on CPU.
        # We cap this to 2048 for all classification tasks.
        classification_ctx = 2048
        
        # Get base options
        if self.use_gpu_for_classification:
            gpu_mgr = OllamaGPUManager(self.classification_model)
            self.classification_options = gpu_mgr.get_gpu_options(for_chat=True, num_ctx=classification_ctx)
        else:
            # CPU-only options
            self.classification_options = {
                "num_gpu": 0,
                "num_thread": 8, # Utilize Ryzen 5 9600X cores
                "num_ctx": classification_ctx,
                "num_predict": 256,
                "temperature": 0.1,
                "top_p": 0.9
            }
        
        # Overrides for precise classification if using GPU
        if self.use_gpu_for_classification:
            self.classification_options.update({
                "temperature": 0.1,
                "top_p": 0.9,
                "num_predict": 256
            })
        
        # LAYER 1: Fast Pattern Triggers (Regex)
        self.fast_triggers = {
            "SOCIAL_GREETING": [
                # Added (<@!?\d+>\s*)? to catch Discord pings, and [!?.,]* to catch stray grammar
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
            "SUMMARIZATION": [
                r"^\s*(kaia\s+)?(summarize|summary of|digest|tl;?dr)\b",
                r"\b(give me a summary|brief on|overview of)\b",
                r"\b(recap (the|this)? (thread|conversation|chat))\b"
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

        log_success(f"IntentParser initialized (Model: {self.classification_model})")
    
    def fast_parse(self, query: str) -> Optional[Intent]:
        """Layer 1: Fast Pattern Detection"""
        query_lower = query.lower().strip()
        
        for strategy, patterns in self.fast_triggers.items():
            for pattern in patterns:
                if re.search(pattern, query_lower, re.IGNORECASE):
                    log_debug(f"Fast-path trigger: {strategy} (Matched: {pattern})")
                    
                    # Construct a basic Intent object from the trigger
                    return Intent(
                        explicit_intent=query,
                        implied_needs=["immediate_response"],
                        emotional_context="neutral",
                        temporal_focus="present_immediate",
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
            from utils.infrastructure.gpu.gpu_memory_manager import gpu_memory_manager, GPUTaskPriority
            
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
                "  \"suggested_strategy\": \"PRECISE_RECALL|DIAGNOSTIC_DEEP_DIVE|DREAM_RECALL|CREATIVE_ASSOCIATION|RELATIONAL_MIRROR|SYNTHESIS_SCAN|EXPLORATORY_DIALOGUE\"\n"
                "}\n\n"
                "STRATEGIES:\n"
                "- PRECISE_RECALL: Specific facts, biographies, dates, or identities.\n"
                "- DIAGNOSTIC_DEEP_DIVE: Technical issues, logs, system status, or bugs.\n"
                "- DREAM_RECALL: Inquiries about previous internal dream states.\n"
                "- SYNTHESIS_SCAN: Real-world news, current events, or external global data. (NOT for internal forum news, game updates, or personal news).\n"
                "- EXPLORATORY_DIALOGUE: General multifaceted conversation, philosophical chat, or informal discussion.\n"
                "- RELATIONAL_MIRROR: Social bonding, reflection on user-bot relationship.\n"
                "- CREATIVE_ASSOCIATION: High-variance brainstorming or creative writing.\n"
                f"{hint_str}"
                f"CONTEXT: {ctx_str[:200]}\n"
                f"QUERY: \"{query}\"\nJSON:"
            )


            # EXECUTION: The GPU guard/routing is now handled entirely in the parent parse_intent()
            # method. This child method is a "dumb" executor to avoid re-entrant deadlock.
            response = await self.ollama_client.chat(
                model=self.classification_model,
                messages=[{"role": "user", "content": prompt}],
                options=self.classification_options
            )
            
            raw_json = response['message']['content'].strip()
            # Clean markdown code blocks if present
            raw_json = raw_json.replace("```json", "").replace("```", "").strip()
            
            # Extract data
            data = json.loads(raw_json)
            
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
            if "out of memory" in err_msg or "cudamalloc" in err_msg or "terminat" in err_msg:
                log_error(f"Intent Analysis CRITICAL OOM: {e}. Falling back to fast-path/default.")
            else:
                log_error(f"Intent Analysis Failed: {e}")
                traceback.print_exc()
            
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

    async def pre_warm(self):
        """Pre-warm the model with a direct call (No semaphore needed for tiny load)"""
        log_action("Pre-warming IntentParser model...")
        try:
            # We use generate directly to avoid the semaphore guard in parse_intent
            from utils.infrastructure.system.yaml_config import config
            max_ctx = config.max_context_tokens
            
            # Use the pre-configured classification options (which include num_gpu: 0 by default)
            await self.ollama_client.generate(
                model=self.classification_model,
                prompt=".",
                options=self.classification_options,
                keep_alive=3600
            )
            log_success("IntentParser model warmed.")
        except Exception as e:
            log_error(f"Pre-warm failed: {e}")

# Legacy Alias for Refactor Compatibility
QueryClassifier = IntentParser
