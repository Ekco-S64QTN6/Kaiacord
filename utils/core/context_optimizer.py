"""
Context Optimization & Personalization
=======================================

Extracted from kaia_intelligence.py (Phase 28 / CQ-01).

Contains:
- Intent, ContextCtx dataclasses (shared types)
- ContextOptimizer: Model-aware token allocation and context trimming
- ContextWeaver: Constructs ContextCtx from raw bot state
- RelevanceFeedback: Learns from user interactions
- PersonalizationEngine: User preference tracking
- PersistentStateManager: State serialization/deserialization
"""

import time
import os
import asyncio
import re
import json
from datetime import datetime
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import List, Optional, Dict

from utils.infrastructure.logging.log_sanitize import summarize_payload
from utils.infrastructure.logging.kaia_logger import (
    log_info, log_action, log_success, log_error, log_warning, log_debug
)

# Pre-compiled hot-path regex patterns
RE_OPTIMIZED_LOG = re.compile(r'\[optimized: saved (\d+) tokens\]')
RE_CLEAN_MD = re.compile(r'```[\s\S]*?```|`[^`]*`|[*_~]')

RE_ORIGINAL_FRAG_HEADER = re.compile(r"## Original Fragment\s*", flags=re.IGNORECASE)
RE_SOURCE_HEADER_MATCH = re.compile(r"Source:\s*(.+)", flags=re.IGNORECASE)
RE_SOURCE_HEADER_STRIP = re.compile(r"Source:\s*.+", flags=re.IGNORECASE)
RE_KAIA_REFLECTION_HEADER = re.compile(r"## Kaia's Reflection\s*", flags=re.IGNORECASE)
RE_DATE_FROM_PATH = re.compile(r'(\d{4})(\d{2})(\d{2})')

# Strip stale time-anchored status responses from history
TIME_ANCHOR_PATTERN = re.compile(r"\bit'?s\s+\d+:\d+\b", re.IGNORECASE)


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
            'gemma4:12b': {'persona': 0.10, 'rag': 0.50, 'history': 0.35, 'system': 0.05},
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
        
    def optimize_context(self, category, persona, rag_nodes, history, strategy=None, user_msg_text=""):
        """
        Optimize context by treating the persona as a non-negotiable anchor.
        PERSONA IS NEVER TRUNCATED.
        """
        # 1. Determine Effective Token Limit (Dynamic scaling for Summarization)
        effective_max_tokens = self.max_tokens
        if strategy == "SUMMARIZATION":
            effective_max_tokens = self.summarization_tokens # Boost for full transcript processing (Safe for 12GB VRAM)
            log_info(f"Summarization strategy detected. Boosting context window to {effective_max_tokens} tokens.")

        # Size only. Interpolating a 150-char slice of the persona still spilled
        # the injected constitution across six log lines per message, because
        # the slice lands mid-document and carries its newlines.
        log_debug(summarize_payload("optimize_context persona", persona))

        # 2. Persona is non-negotiable - calculate its actual token cost
        current_tokens = self._estimate_tokens(persona)

        # 3. Reserve headroom for:
        #    a) Ollama generation response (max_response_tokens, default 2048)
        #    b) System overhead added in _construct_messages (safeguard_block + metadata_block + constraints)
        #       represented accurately by self.system_reserve
        #    c) Current user message tokens
        from utils.infrastructure.system.yaml_config import config as _cfg
        response_reserve = getattr(_cfg, 'max_response_tokens', 2048)
        user_msg_tokens = self._estimate_tokens(user_msg_text) if user_msg_text else 250
        fixed_overhead = self.system_reserve + response_reserve + user_msg_tokens

        # 4. Calculate available budget for RAG and History combined
        remaining_budget = max(effective_max_tokens - current_tokens - fixed_overhead, 0)

        # 5. Allocate remainder based on model ratios
        model_ratios = self.ratios.get(self.model_name, self.ratios['default']).copy()
        if strategy == "SUMMARIZATION":
            rag_weight = 0.95
            hist_weight = 0.05
        else:
            rag_weight = model_ratios['rag']
            hist_weight = model_ratios['history']
            
        total_weight = rag_weight + hist_weight
        
        rag_budget = int((rag_weight / total_weight) * remaining_budget)
        history_budget = remaining_budget - rag_budget
        
        # Ensure safe minimums when remaining budget allows
        if remaining_budget >= (self.min_rag_tokens + self.min_history_tokens):
            rag_budget = max(rag_budget, self.min_rag_tokens)
            history_budget = max(history_budget, self.min_history_tokens)
        elif remaining_budget > 0:
            rag_budget = max(int(remaining_budget * 0.5), 256)
            history_budget = max(remaining_budget - rag_budget, 256)
        else:
            rag_budget = 256
            history_budget = 256
        
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
                original_fragment = RE_ORIGINAL_FRAG_HEADER.sub("", original_fragment)
                
                # Try to extract the source from the header if possible
                file_origin = os.path.basename(path_raw or 'Dream Source')
                source_match = RE_SOURCE_HEADER_MATCH.search(original_fragment)
                if source_match:
                    file_origin = os.path.basename(source_match.group(1).strip())
                    original_fragment = RE_SOURCE_HEADER_STRIP.sub("", original_fragment).strip()
                
                # Add Original Fragment as RECORDED KNOWLEDGE
                wrapped_orig = f"<recorded_knowledge source=\"{file_origin}\">\n{original_fragment}\n</recorded_knowledge>"
                reference_nodes.append(wrapped_orig)
                
                # Add Kaia's Reflection as LIVED EXPERIENCE
                kaia_reflection = RE_KAIA_REFLECTION_HEADER.sub("", kaia_reflection).strip()
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
                elif "user_profile" in path: type_label = "USER PROFILE SUMMARY"
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
        rag_str = ""
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

        # 4. Append History (Pruned list to preserve role metadata)
        optimized_history = []
        if history:
            history_budget = max(effective_max_tokens - current_tokens - fixed_overhead, self.min_history_tokens)
            hist_current = 0
            
            for turn in reversed(history):
                if not isinstance(turn, dict):
                    continue
                    
                t_count = self._estimate_tokens(turn.get('content', ''))
                if hist_current + t_count <= history_budget:
                    if turn.get('role') == 'assistant' and TIME_ANCHOR_PATTERN.search(turn.get('content', '')):
                        continue
                    optimized_history.insert(0, turn.copy())
                    hist_current += t_count
                else:
                    break
            
            if optimized_history:
                log_debug(f"History optimized to {len(optimized_history)} turns within {history_budget} token budget.")
                
        return {
            'persona': persona,
            'rag': rag_str,
            'history': optimized_history
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
        match = RE_DATE_FROM_PATH.search(path)
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
    _DEFAULT_TRAITS = {
        'conciseness': 0.5,
        'technicality': 0.5,
        'formality': 0.5,
        'humor': 0.5
    }

    def __init__(self, max_profiles=500):
        self.user_profiles = OrderedDict()  # LRU via move_to_end
        self.dirty_profiles = set() # user_id
        self.max_profiles = max_profiles
        
    async def get_user_traits(self, user_id):
        uid = str(user_id)
        if uid in self.user_profiles:
            self.user_profiles.move_to_end(uid)  # Touch for LRU
            return self.user_profiles[uid]
        return self._DEFAULT_TRAITS.copy()

    def adapt_prompt(self, system_prompt, traits):
        """Inject lightweight behavioral hints based on learned user traits."""
        hints = []
        if traits.get('technicality', 0.5) < 0.35:
            hints.append("Use plain language. Avoid jargon.")
        elif traits.get('technicality', 0.5) > 0.70:
            hints.append("Technical depth is welcome. Be precise.")
        if traits.get('conciseness', 0.5) > 0.65:
            hints.append("Keep responses short. This user prefers brevity.")
        if traits.get('humor', 0.5) > 0.70:
            hints.append("This user appreciates wit and dry humor.")
        if traits.get('formality', 0.5) < 0.30:
            hints.append("Casual register is fine. Relax.")
        if hints:
            system_prompt += "\n\n[USER PREFERENCE: " + " ".join(hints) + "]"
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
        
        if traits_changed:
            self.user_profiles[canonical_id] = traits
            self.user_profiles.move_to_end(canonical_id)  # LRU touch
            self.dirty_profiles.add(canonical_id)
            log_debug(f"Updated profile for {canonical_id}: C={traits['conciseness']:.2f}, T={traits['technicality']:.2f}")

            # LRU eviction: pop oldest entries when over capacity
            while len(self.user_profiles) > self.max_profiles:
                self.user_profiles.popitem(last=False)  # Evict least-recently-used

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
