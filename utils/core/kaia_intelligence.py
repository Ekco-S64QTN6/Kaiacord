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
from collections import defaultdict, OrderedDict
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
        self._scheduler_task = None
        self._cached_options = {}  # model_name -> gpu_options (avoids re-instantiation)
        
    async def pre_warm(self, model_name):
        if not model_name: return
        if model_name in self.pool:
            self.pool[model_name]['last_used'] = time.time()
            return

        log_action(f"Adding {model_name} to keep-alive pool...")
        self.pool[model_name] = {'last_used': time.time()}
        
        # Initial warm
        try:
            options = self._cached_options.get(model_name, {'num_predict': 1})
            await self.ollama_client.generate(model=model_name, prompt=".", options=options)
        except Exception: pass

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
                        timeout=600.0  # Increased from 300s to handle high-load boot cycles
                    )
                    self.pool[model_name] = {'last_used': time.time(), 'status': 'ready'}
                    return True
                except asyncio.TimeoutError:
                    if attempt < max_attempts:
                        log_warning(f"Model {model_name} pre-warm timed out (attempt {attempt}/{max_attempts}). "
                                    f"CPU may be busy with embeddings. Retrying in 120s...")
                        await asyncio.sleep(120)
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
                    options = self._cached_options.get(model_name, {'num_predict': 1})
                    # Lighter: generate(prompt=".") instead of chat()
                    await self.ollama_client.generate(model=model_name, prompt=".", options=options, keep_alive=3600)
                    log_debug(f"Tickled model: {model_name}")
                except Exception as e:
                    log_warning(f"Failed to tickle {model_name}: {e}")
                    models_to_remove.append(model_name)
            
            for m in models_to_remove:
                if m in self.pool: del self.pool[m]
                
        log_debug("Model warm pool scheduler stopped (pool empty).")

class ContextOptimizer:
    """Model-aware token allocation and context trimming."""
    def __init__(self, model_name=None, max_tokens=None):
        # Lazy import to avoid circular import during module loading
        from utils.infrastructure.system.yaml_config import config
        
        # Use config as single source of truth if not explicitly provided
        self.model_name = model_name or config.chat_model
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
        self._token_cache = OrderedDict() # LRU
        self._max_cache_size = 500
        # Precompiled prompt segments
        self._rag_header = (
            "\n[RELEVANT_KNOWLEDGE_ARCHIVE]\n"
            "Context from your memories, knowledge, and past interactions:\n"
        )
        self._history_header = "\n[CONVERSATION_HISTORY]\n"
        
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
                else:
                    # Add user name and date provenance
                    provenance = []
                    if user_name: provenance.append(user_name)
                    date_str = self._extract_date_from_path(path)
                    if date_str: provenance.append(date_str)
                    if provenance: type_label += f": {' | '.join(provenance)}"
                history_nodes.append(f"[{type_label}]\n{content_raw}")
            elif source_type == 'news' or "news" in path:
                news_nodes.append(f"{content_raw}")
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
        # 1. Start with Persona (Anchor)
        current_tokens = self._estimate_tokens(persona)
        
        # 2. Append Categorized RAG Nodes (Incremental assembly)
        rag_str = ""
        
        # Allocation: RAG gets up to 45% of remaining budget
        remaining = self.max_tokens - current_tokens - 1000 # Leave buffer
        rag_budget = int(remaining * 0.45)
        rag_current = 0
        
        def _fit_nodes(nodes, budget_remaining):
            """Fit as many nodes as possible within the token budget."""
            fitted = []
            used = 0
            for text in nodes:
                if not text: continue
                t_count = self._estimate_tokens(text)
                if used + t_count <= budget_remaining:
                    fitted.append(text)
                    used += t_count
                else:
                    if budget_remaining - used > 200:
                        fitted.append(self.trim_to_tokens(text, budget_remaining - used))
                        used = budget_remaining
                    break
            return fitted, used
        
        # Assemble with structural group headers for source attribution
        sections = []
        
        if news_nodes:
            fitted, used = _fit_nodes(news_nodes, rag_budget - rag_current)
            if fitted:
                sections.append("[EXTERNAL NEWS]\n" + "\n---\n".join(fitted))
                rag_current += used
        
        if reference_nodes:
            fitted, used = _fit_nodes(reference_nodes, rag_budget - rag_current)
            if fitted:
                sections.append("[REFERENCE KNOWLEDGE]\n" + "\n---\n".join(fitted))
                rag_current += used
        
        if history_nodes:
            fitted, used = _fit_nodes(history_nodes, rag_budget - rag_current)
            if fitted:
                sections.append("[OBSERVED INTERACTIONS]\n" + "\n---\n".join(fitted))
                rag_current += used
        
        if sections:
            rag_str = self._rag_header + "\n\n".join(sections)
            current_tokens += rag_current

        # 3. Append History (Incremental)
        hist_str = ""
        if history:
            history_budget = self.max_tokens - current_tokens - 500
            hist_parts = []
            hist_current = 0
            
            # Add latest first, but keep chronological order in final output
            for turn in reversed(history):
                # Ensure the turn is a string for joining later
                if isinstance(turn, dict):
                    turn_str = turn.get('content', str(turn))
                else:
                    turn_str = str(turn)
                    
                t_count = self._estimate_tokens(turn_str)
                if hist_current + t_count <= history_budget:
                    hist_parts.insert(0, turn_str)
                    hist_current += t_count
                else:
                    break
            
            if hist_parts:
                hist_str = self._history_header + "\n".join(hist_parts)
                
        return {
            'persona': persona,
            'rag': rag_str,
            'history': hist_str
        }
        
    def _estimate_tokens(self, text) -> int:
        """Estimate tokens with LRU caching.
        Handles both strings and legacy dict objects gracefully.
        """
        if isinstance(text, dict):
            text = text.get('content', '')
            
        text = str(text)
        if not text: return 0
        h = hash(text)
        if h in self._token_cache:
            # Move to end (LRU)
            self._token_cache.move_to_end(h)
            return self._token_cache[h]
            
        # Approx 4 chars per token or split variant
        count = int(len(text.split()) * self.token_multiplier)
        
        self._token_cache[h] = count
        if len(self._token_cache) > self._max_cache_size:
            self._token_cache.popitem(last=False) # Evict oldest
        return count

    def trim_to_tokens(self, text, max_tokens):
        if not text: return ""
        text_tokens = self._estimate_tokens(text)
        if text_tokens <= max_tokens: return text
            
        lines = text.split('\n')
        # Precompute line tokens once
        line_data = [] # (line, tokens, is_important)
        important_tokens = 0
        important_set = set()
        
        for l in lines:
            l_lower = l.lower()
            is_imp = '###' in l_lower or 'important:' in l_lower or 'core:' in l_lower or 'rule:' in l_lower
            t_count = self._estimate_tokens(l)
            line_data.append((l, t_count, is_imp))
            if is_imp:
                important_tokens += t_count
                important_set.add(l)

        remaining_tokens = max_tokens - important_tokens
        
        if remaining_tokens <= 0: 
            # Fallback to just the most critical lines or character truncation
            critical = [d[0] for d in line_data if d[2]]
            return '\n'.join(critical[:5]) if critical else text[:int(max_tokens * 3)]
            
        regular_lines = []
        for line, t_count, is_imp in reversed(line_data):
            if not is_imp:
                if t_count <= remaining_tokens:
                    regular_lines.insert(0, line)
                    remaining_tokens -= t_count
                else: 
                    # Last chunk if room
                    if remaining_tokens > 150:
                        words = line.split()
                        chunk = ' '.join(words[:int(remaining_tokens/self.token_multiplier)])
                        regular_lines.insert(0, chunk)
                    break
        
        important_lines = [d[0] for d in line_data if d[2]]
        return '\n'.join(important_lines + regular_lines)

    @staticmethod
    def _extract_date_from_path(path: str) -> str:
        """Extract a readable date from file paths like 'interactions_20260221.md'."""
        match = re.search(r'(\d{4})(\d{2})(\d{2})', path)
        if match:
            try:
                from datetime import datetime as _dt
                d = _dt(int(match.group(1)), int(match.group(2)), int(match.group(3)))
                return d.strftime("%b %d")
            except ValueError:
                pass
        return ""

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
                # BATCH INSERTION: Single thread-hop for all documents
                def _batch_insert():
                    for doc in synthetic_docs:
                        self.rag.indices['logs'].insert(doc)
                
                await asyncio.to_thread(_batch_insert)
                log_success(f"Added {len(synthetic_docs)} feedback nodes to RAG (Batch).")
            except Exception as e:
                log_error(f"Error adding feedback to RAG: {e}")

class PersonalizationEngine:
    """Learn user preferences and adapt responses."""
    def __init__(self, max_profiles=500):
        self.user_profiles = {} # user_id -> {traits}
        self.dirty_profiles = set() # user_id
        self.max_profiles = max_profiles
        
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
        traits_changed = False
        if abs(traits['conciseness'] - (0.9 * traits['conciseness'] + 0.1 * target_conciseness)) > 0.01:
            traits['conciseness'] = 0.9 * traits['conciseness'] + 0.1 * target_conciseness
            traits_changed = True
        
        # Technicality: detect technical keywords in query
        tech_keywords = ['how', 'why', 'code', 'implement', 'system', 'architecture', 'error', 'bug', 'terminal', 'logs']
        has_tech = any(kw in query.lower() for kw in tech_keywords)
        target_tech = 0.8 if has_tech else 0.4
        if abs(traits['technicality'] - (0.9 * traits['technicality'] + 0.1 * target_tech)) > 0.01:
            traits['technicality'] = 0.9 * traits['technicality'] + 0.1 * target_tech
            traits_changed = True
        
        # Pruning: If pool grows too large, clear 10% (simplest eviction)
        if len(self.user_profiles) > self.max_profiles:
            # Drop older entries (not true LRU but keeps it bounded)
            keys = list(self.user_profiles.keys())
            # Evict at least 1, or 10%
            evict_count = max(1, int(self.max_profiles * 0.1))
            for k in keys[:evict_count]:
                del self.user_profiles[k]
           
        if traits_changed:
            self.user_profiles[user_id] = traits
            self.dirty_profiles.add(user_id)
            log_debug(f"Updated profile for {user_id}: C={traits['conciseness']:.2f}, T={traits['technicality']:.2f}")

class PersistentStateManager:
    """Save and load system state to survive restarts."""
    def __init__(self, state_dir="./memory/state"):
        self.state_dir = state_dir
        self.profiles_dir = os.path.join(self.state_dir, "profiles")
        os.makedirs(self.profiles_dir, exist_ok=True)
        self.state_path = os.path.join(self.state_dir, "kaia_state.json")
        
    async def save_state_async(self, personalization, monitor, cache=None):
        """Async wrapper for save_state."""
        await asyncio.to_thread(self.save_state, personalization, monitor, cache)

    def save_state(self, personalization, monitor, cache=None):
        """Atomic save of critical state (Thread-safe synchronous version)."""
        try:
            # 1. Save general metrics
            state = {
                'performance_metrics': {
                    'cache_hits': monitor.metrics.get('cache_hits', 0),
                    'cache_misses': monitor.metrics.get('cache_misses', 0),
                    'exact_hits': monitor.metrics.get('exact_hits', 0)
                },
                'saved_at': time.time()
            }
            
            # Atomic write for general state
            current_state_str = json.dumps(state, sort_keys=True)
            temp_path = self.state_path + ".tmp"
            with open(temp_path, 'w') as f:
                f.write(current_state_str)
            os.replace(temp_path, self.state_path)

            # 2. Save User Profiles individually for scalability
            saved_count = 0
            # Determine which profiles to save
            targets = list(personalization.user_profiles.keys())
            # If we have dirty tracking, use it
            if hasattr(personalization, 'dirty_profiles') and personalization.dirty_profiles:
                targets = list(personalization.dirty_profiles)

            for user_id in targets:
                profile = personalization.user_profiles[user_id]
                # Sanitize ID for filename
                safe_id = "".join([c for c in str(user_id) if c.isalnum() or c in ('-', '_')])
                profile_path = os.path.join(self.profiles_dir, f"{safe_id}.json")
                
                with open(profile_path, 'w') as f:
                    json.dump(profile, f)
                saved_count += 1
                
            # Clear dirty tracking after successful save
            if hasattr(personalization, 'dirty_profiles'):
                personalization.dirty_profiles.clear()

            log_success(f"Cold state persisted. Saved {saved_count} profiles.")
        except Exception as e:
            log_error(f"Failed to save state: {e}")

    async def load_state_async(self, personalization, monitor, cache=None):
        """Async wrapper for load_state."""
        return await asyncio.to_thread(self.load_state, personalization, monitor, cache)

    def load_state(self, personalization, monitor, cache=None):
        """Load state if not too stale (Thread-safe synchronous version)."""
        # 1. Load general metrics
        if os.path.exists(self.state_path):
            try:
                with open(self.state_path, 'r') as f:
                    state = json.load(f)
                
                # 48h stale check for metrics (more lenient than before)
                if time.time() - state.get('saved_at', 0) < 172800:
                    metrics = state.get('performance_metrics', {})
                    monitor.metrics['cache_hits'] = metrics.get('cache_hits', 0)
                    monitor.metrics['cache_misses'] = metrics.get('cache_misses', 0)
                    monitor.metrics['exact_hits'] = metrics.get('exact_hits', 0)
                    log_debug("Loaded performance metrics from state.")
            except Exception as e:
                log_warning(f"Failed to load metrics state: {e}")

        # 2. Load User Profiles from individual files
        try:
            profile_files = os.listdir(self.profiles_dir)
            loaded_count = 0
            for filename in profile_files:
                if filename.endswith(".json"):
                    user_id = filename[:-5] # Strip .json
                    path = os.path.join(self.profiles_dir, filename)
                    try:
                        with open(path, 'r') as f:
                            profile = json.load(f)
                        personalization.user_profiles[user_id] = profile
                        loaded_count += 1
                    except Exception: continue
            
            if loaded_count > 0:
                log_success(f"Loaded {loaded_count} user profiles from persistent storage.")
                return True
        except Exception as e:
            log_error(f"Failed to load user profiles: {e}")
            
        return False




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
        
        # [MEMORY OPTIMIZATION]: Intent analysis only needs the current query and 
        # minimal context. 
        # We cap this to the value in config (default 2048).
        classification_ctx = config.classification_context_tokens
        
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
        
        for strategy, patterns in raw_triggers.items():
            self.fast_triggers[strategy] = [re.compile(p, re.IGNORECASE) for p in patterns]

        log_success(f"IntentParser initialized (Model: {self.classification_model})")
    
    def fast_parse(self, query: str) -> Optional[Intent]:
        """Layer 1: Fast Pattern Detection"""
        query_lower = query.lower().strip()
        
        for strategy, patterns in self.fast_triggers.items():
            for compiled_re in patterns:
                if compiled_re.search(query_lower):
                    log_debug(f"Fast-path trigger: {strategy}")
                    
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
            response = await asyncio.wait_for(
                self.ollama_client.chat(
                    model=self.classification_model,
                    messages=[{"role": "user", "content": prompt}],
                    options=self.classification_options
                ),
                timeout=self.config.classification_timeout
            )
            
            raw_json = response['message']['content'].strip()
            
            clean_json = await self._repair_json(raw_json)
            data = json.loads(clean_json)
            
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
                import traceback
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

    async def _repair_json(self, text: str) -> str:
        """Attempt to repair broken JSON from LLM output using precompiled regex."""
        # Remove markdown code blocks if present
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```', '', text).strip()
        
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
            import traceback
            log_error(f"Pre-warm failed: {e}")
            log_debug(f"IntentParser Pre-warm Traceback:\n{traceback.format_exc()}")

# Legacy Alias for Refactor Compatibility
QueryClassifier = IntentParser
