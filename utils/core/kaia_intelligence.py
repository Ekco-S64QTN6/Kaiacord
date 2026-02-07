import time
import os
import asyncio
import numpy as np
import re
import json
import hashlib
import threading
from datetime import datetime
from collections import defaultdict
from ollama import Client
from llama_index.embeddings.ollama import OllamaEmbedding
from utils.infrastructure.logging.kaia_logger import log_info, log_action, log_success, log_error, log_warning, log_debug

# NOTE: config is imported lazily in ContextOptimizer.__init__ to avoid circular import

# PerformanceMonitor and SemanticCache have been moved to dedicated utility modules.
# See utils/core/semantic_cache.py for the current implementation.

class ModelWarmPool:
    """Keep models warm between uses to prevent cold starts."""
    def __init__(self, ollama_client):
        self.ollama_client = ollama_client
        self.pool = {}
        self.keep_alive_tasks = {}
        
    async def pre_warm(self, model_name):
        if model_name in self.pool:
            self.pool[model_name]['last_used'] = time.time()
            return True
            
        log_action(f"Pre-warming model: {model_name}...")
        try:
            # Import gpu_manager dynamically to avoid circular imports
            from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager
            gpu_manager = OllamaGPUManager(model_name)
            options = gpu_manager.get_gpu_options(for_chat=True)
            options['num_predict'] = 1
            
            await self.ollama_client.chat(
                model=model_name,
                messages=[{"role": "user", "content": "ready?"}],
                options=options
            )
            self.pool[model_name] = {'last_used': time.time(), 'status': 'ready'}
            if model_name not in self.keep_alive_tasks:
                self.keep_alive_tasks[model_name] = asyncio.create_task(self.keep_alive(model_name))
            return True
        except Exception as e:
            log_error(f"Failed to pre-warm model {model_name}: {e}")
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
                # Use GPU options for keep-alive too
                from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager
                gpu_manager = OllamaGPUManager(model_name)
                options = gpu_manager.get_gpu_options(for_chat=True)
                options['num_predict'] = 1
                
                await self.ollama_client.chat(model=model_name, messages=[{"role": "user", "content": "ping"}], options=options)
            except Exception:
                if model_name in self.pool: del self.pool[model_name]
                break

class QueryClassifier:
    """Query classifier with timeout and improved performance (Consolidated)"""
    
    def __init__(self, ollama_client=None, model="gemma3:12b", logger=None, host="http://localhost:11434", timeout=15.0):
        # Use the provided async ollama_client
        self.ollama_client = ollama_client
        self.model = model
        self.logger = logger or log_info
        self.timeout = timeout
        self.host = host
        
        # Use the main model for classification (it's already loaded/hot)
        self.classification_model = model
        
        # Define classification options - Use GPU for speed
        self.classification_options = {
            "num_gpu": -1,          # Use all layers (main model is already loaded)
            "num_thread": 4,
            "num_ctx": 1024,        # Standard context
            "temperature": 0.0,     # Deterministic
            "top_p": 0.9,
            "top_k": 20,
            "num_predict": 10       # Stop immediately after category
        }
        
        # Enhanced rule-based patterns (fast, no model needed)
        self.patterns = {
            "GREETING": [
                r"^\s*(hi|hello|hey|greetings|sup|yo|hi there|hello there|morning|evening|night)\s*$",
                r"^\s*(hi|hello|hey|greetings|sup|yo)\s+kaia",
                r"^\s*kaia\s*(hi|hello|hey|greetings|sup|yo)",
                r"\b(howdy|hey|yo)\s+kaia\b",
                r"^\s*kaia\?$"
            ],
            "IDENTITY": [
                r"\b(who\s*(are\s*you|am\s*i|is\s*this))\b",
                r"\btell\s+me\s+about\s+(yourself|you)\b",
                r"\bwhat\s+are\s+you\b",
                r"\bwho\s+am\s+i\b",
                r"\bwhat\s+do\s+you\s+know\s+about\s+me\b",
                r"\bdescribe\s+(yourself|kaia)\b",
                r"\byour\s+(persona|identity|creator|origin)\b"
            ],
            "ENTITY": [  # Entity/identity queries
                r"^\s*who (is|are|was|were) ",
                r"^\s*tell me about ",
                r"^\s*what do you know about ",
                r"^\s*who the (hell|fuck) is ",
                r"^\s*who's ",
                r"^\s*explain ",
                r"^\s*describe ",
                r"\b(mark|elara|thorne|jules|elias)\b"  # Specific names mentioned
            ],
            "NEWS": [  # Direct news pattern matching
                r"\bnews\s+(about|on|regarding)\b",
                r"\bwhat('?s| is) the (latest|recent|current|today'?s)?\s*news\b",
                r"\btell\s+me\s+(the\s+)?news\b",
                r"\bany\s+(new|recent)\s+updates\b",
                r"\bwhat'?s\s+happening\b",
                r"\bcurrent\s+events\b",
                r"\bheadlines\b",
                r"\bbreaking\s+news\b"
            ],
            "POLITICS": [
                r"\b(politics|political|election|government|senate|congress)\b",
                r"\b(president|prime minister|minister|policy|legislation)\b"
            ],
            "TECH": [
                r"\b(tech(nology)?|software|hardware|ai\b|llm|gpt)\b",
                r"\b(openai|google|meta|microsoft|apple|tesla|spacex)\b",
                r"\b(quantum|computer|chip|processor|gpu|cpu)\b",
                r"\b(starkind|architecture|mitigate)\b"
            ],
            "SECURITY": [
                r"\b(security|hack|breach|cyber(?!punk)|attack|vulnerability|cve)\b",
                r"\b(ransomware|malware|phishing|zero.?day|exploit)\b"
            ],
            "COMMAND": [
                r"^\s*(status|statistics|stats|info|ping|uptime)\b",
                r"^\s*(list|show|display)\s+users?\b",
                r"^\s*(clear|reset|clean|refresh)\b",
                r"\b(draw|paint|generate|create|sketch|render|portrait|landscape|picture|art|square|circle|triangle)\b",
                r"\b(analyze|look at|describe|what is in)\b.*\b(image|picture|this)\b",
                r"^\s*!(quip|news|dreams|cache)\b",
                r"^\s*/(quip|news|dreams|cache)\b"
            ],
            "PERSONAL": [
                r"how (are|is) you",
                r"how'?s it going",
                r"how are you feeling",
                r"you okay",
                r"what'?s up",
                r"feeling now"
            ],
            "CASUAL": [
                r"^(yeah|no|maybe|ok|okay|sure|cool|nice|thanks|thank you|thx)$",
                r"^(lol|lmao|haha|wow|interesting)$"
            ]
        }
        
        self.category_descriptions = {
            "GREETING": "Greeting or casual conversation",
            "IDENTITY": "Questions about identity",
            "NEWS": "News and current events",
            "POLITICS": "Political news and discussions",
            "TECH": "Technology news and developments",
            "SECURITY": "Security and cybersecurity topics",
            "COMMAND": "Bot commands and status requests",
            "GENERAL": "General conversation and questions",
            "KNOWLEDGE": "Knowledge-based questions",
            "PERSONAL": "Personal or emotional topics",
            "CASUAL": "Casual short responses"
        }
        
        log_success(f"QueryClassifier initialized with timeout: {timeout}s")
    
    def fast_classify(self, query: str) -> str:
        """Rule-based ONLY classification (extremely fast)"""
        return self._classify_rules(query).lower()

    async def _classify_async(self, query: str) -> str:
        """Classify query with async timeout protection"""
        # Check if NEWS is disabled globally
        from utils.core.message_processor import NEWS_AUTO_TRIGGER_ENABLED
        
        query_clean = query.strip()
        query_lower = query_clean.lower()
        word_count = len(query_lower.split())
        
        # First, try rule-based classification
        rule_based_result = self._classify_rules(query_clean)
        
        # Safety Fix: Prevent NEWS from overriding core intents
        if rule_based_result == "NEWS" and not NEWS_AUTO_TRIGGER_ENABLED:
            log_debug("NEWS auto-trigger disabled, suppressing rule-based NEWS match.")
            rule_based_result = "GENERAL"

        # GUARDRAIL: Short conversational turns (<= 6 words) 
        if word_count <= 6 and rule_based_result not in ["GREETING", "IDENTITY", "COMMAND", "CASUAL", "PERSONAL"]:
            log_debug(f"Short query ({word_count} words) detected, defaulting to general.")
            return "general"

        if rule_based_result != "GENERAL":
            return rule_based_result.lower()
        
        # FAST-PATH GUARDRAIL
        if word_count <= 10 and not any(kw in query_lower for kw in ["who", "what", "how", "why", "tell", "explain", "news"]):
            log_debug("Simple query detected, skipping model classification.")
            return "general"
        
        # Async model classification
        model_result = await self._classify_with_model_timeout(query_clean)
        
        # Safety Fix: Prevent NEWS from overriding core intents
        if model_result == "NEWS" and not NEWS_AUTO_TRIGGER_ENABLED:
            log_debug("NEWS auto-trigger disabled, suppressing model-based NEWS match.")
            return "general"
            
        return model_result.lower()
    
    def _classify_rules(self, query: str) -> str:
        """Rule-based classification (fast, no model)"""
        query_lower = query.lower().strip()
        
        # Check each pattern category
        for category, patterns in self.patterns.items():
            for pattern in patterns:
                if re.search(pattern, query_lower, re.IGNORECASE):
                    log_info(f"Rule-based classification: {category} (Matched: {pattern})")
                    return category
        
        return "GENERAL"
    
    async def _classify_with_model_timeout(self, query: str) -> str:
        """Classify using model with async timeout protection"""
        try:
            # Minimal prompt for speed and accuracy
            prompt = f"Classify this query into ONE category (GREETING, IDENTITY, NEWS, POLITICS, TECH, SECURITY, COMMAND, GENERAL).\n\nQuery: \"{query}\"\n\nCategory:"

            # Use asyncio.wait_for for clean cancellation
            response = await asyncio.wait_for(
                self.ollama_client.chat(
                    model=self.classification_model,
                    messages=[{"role": "user", "content": prompt}],
                    stream=False,
                    options=self.classification_options
                ),
                timeout=self.timeout
            )
            
            result = response['message']['content'].strip().upper()
            
            # Map to known categories
            for category in self.category_descriptions.keys():
                if category in result:
                    return category
            
            return "GENERAL"
            
        except asyncio.TimeoutError:
            log_warning(f"Classification timeout after {self.timeout}s")
            return "GENERAL"
        except Exception as e:
            log_error(f"Classification error: {e}")
            return "GENERAL"
    
    async def classify(self, query: str) -> str:
        """Main classification method (Async)"""
        return await self._classify_async(query)

    async def pre_warm(self):
        """Pre-warm the classification model"""
        log_action("Pre-warming classification model (this may take a moment)...")
        try:
            # First call can take longer due to model loading
            start_time = time.time()
            
            # Use a longer timeout for the initial load
            original_timeout = self.timeout
            self.timeout = 30.0 
            
            await self.classify("warm up")
            
            self.timeout = original_timeout
            log_success(f"Classification model warmed up in {time.time() - start_time:.2f}s")
        except Exception as e:
            log_error(f"Pre-warm failed: {e}")

class ContextOptimizer:
    """Model-aware token allocation and context trimming."""
    def __init__(self, model_name="gemma3:12b", max_tokens=28000):
        # Lazy import to avoid circular import during module loading
        from utils.infrastructure.system.yaml_config import config
        
        self.model_name = model_name
        self.max_tokens = max_tokens
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
        self.min_rag_tokens = 1024
        self.min_history_tokens = 512
        
    def optimize_context(self, category, persona, rag_nodes, history):
        """
        Optimize context by treating the persona as a non-negotiable anchor.
        PERSONA IS NEVER TRUNCATED.
        """
        # 1. Persona is non-negotiable - calculate its actual cost first
        optimized_persona = persona 
        persona_tokens = len(persona.split()) * self.token_multiplier
        
        # 2. Reserve tokens for system reinforcement (configurable)
        system_reserve = self.system_reserve
        
        # 3. Calculate remaining budget for RAG and History
        remaining_budget = self.max_tokens - persona_tokens - system_reserve
        
        # 4. Handle emergency budget depletion
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
        
        for n in rag_nodes:
            # Handle both dictionary and object formats for robustness
            metadata = n.get('metadata', {}) if isinstance(n, dict) else getattr(n, 'metadata', {})
            content_raw = n.get('content', str(n)) if isinstance(n, dict) else (n.text if hasattr(n, 'text') else str(n))
            
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
                # Structural isolation wrapping with semantic tagging
                # Tagging as 'RECORDED_KNOWLEDGE' to imply it's something she read/stored
                wrapped_content = f"<recorded_knowledge source=\"{file_name}\">\n{content_raw}\n</recorded_knowledge>"
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
        
    async def log_interaction(self, query, response, user_id):
        # ECHO CHAMBER PROTECTION: Don't log generic "what's new" or status queries
        # as synthetic RAG documents, as they create a feedback loop.
        query_lower = query.lower()
        blacklist = ["what's new", "whats new", "what have you", "learned", "status", "info", "uptime", "stats", "how are you"]
        if any(trigger in query_lower for trigger in blacklist):
            return
            
        self.feedback_log.append({'query': query, 'response': response, 'user_id': user_id, 'timestamp': time.time()})
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
                metadata={'source': 'feedback', 'type': 'successful_qa', 'user_id': str(item['user_id']), 'timestamp': item['timestamp']}
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
        """Inject style instructions into the system prompt."""
        adaptation = "\n\n[STYLE_ADAPTATION]\n"
        if traits['conciseness'] > 0.9:
            adaptation += "- Be concise. 1-2 sentences is plenty.\n"
        else:
            adaptation += "- Be human. Aim for 3-8 sentences for complex topics. A paragraph is fine. No fluff, but don't be a robot.\n"
            
        if traits['technicality'] > 0.7:
            adaptation += "- Use technical language and deep analysis.\n"
        elif traits['technicality'] < 0.3:
            adaptation += "- Use simple, everyday language.\n"

        adaptation += "- STRICTLY FORBIDDEN: Do not invent personal anecdotes, fictional people, or historical dates. No 'I remember back in...' tropes.\n"
            
        return system_prompt + adaptation

    async def learn_from_interaction(self, user_id, query, response):
        """Update user profile based on interaction characteristics."""
        user_id = str(user_id)
        traits = await self.get_user_traits(user_id)
        
        # Simple heuristics for learning
        word_count = len(response.split())
        
        # Conciseness: if user gets long responses and doesn't complain, maybe they like them?
        # Or if they ask short questions, they might want short answers.
        query_len = len(query.split())
        
        # EMA update
        target_conciseness = 0.7 if query_len < 3 else 0.2
        traits['conciseness'] = 0.9 * traits['conciseness'] + 0.1 * target_conciseness
        
        # Technicality: detect technical keywords in query
        tech_keywords = ['how', 'why', 'code', 'implement', 'system', 'architecture', 'error', 'bug']
        has_tech = any(kw in query.lower() for kw in tech_keywords)
        target_tech = 0.9 if has_tech else 0.3
        traits['technicality'] = 0.9 * traits['technicality'] + 0.1 * target_tech
        
        self.user_profiles[user_id] = traits
        log_info(f"Updated personalization for {user_id}: C={traits['conciseness']:.2f}, T={traits['technicality']:.2f}")

class PersistentStateManager:
    """Save and load system state to survive restarts."""
    def __init__(self, state_dir="./memory/state"):
        self.state_dir = state_dir
        os.makedirs(state_dir, exist_ok=True)
        self.state_path = os.path.join(self.state_dir, "kaia_state.json")
        
    def save_state(self, cache, personalization, monitor):
        """Atomic save of critical state."""
        try:
            state = {
                'exact_cache': cache.exact_cache,
                'full_cache': getattr(cache, 'cache', {}),
                'user_profiles': personalization.user_profiles,
                'performance_metrics': {
                    'cache_hits': monitor.metrics['cache_hits'],
                    'cache_misses': monitor.metrics['cache_misses'],
                    'exact_hits': monitor.metrics['exact_hits']
                },
                'saved_at': time.time()
            }
            
            # Delta check: only save if content actually changed
            current_state_str = json.dumps(state, sort_keys=True)
            if hasattr(self, '_last_state_hash'):
                current_hash = hashlib.md5(current_state_str.encode()).hexdigest()
                if current_hash == self._last_state_hash:
                    log_debug("Cold state unchanged, skipping persistence.")
                    return
                self._last_state_hash = current_hash
            else:
                self._last_state_hash = hashlib.md5(current_state_str.encode()).hexdigest()

            temp_path = self.state_path + ".tmp"
            with open(temp_path, 'w') as f:
                f.write(current_state_str)
            os.replace(temp_path, self.state_path)
            log_success("Cold state persisted successfully.")
        except Exception as e:
            log_error(f"Failed to save state: {e}")

    def load_state(self, cache, personalization, monitor):
        """Load state if not too stale."""
        if not os.path.exists(self.state_path): return False
        
        try:
            with open(self.state_path, 'r') as f:
                state = json.load(f)
            
            # 24h stale check
            if time.time() - state.get('saved_at', 0) > 86400:
                log_warning("Persisted state is too old (>24h), skipping.")
                return False
                
            # Correctly handle ImprovedSemanticCache state
            if hasattr(cache, 'cache') and isinstance(cache.cache, dict):
                cache.cache.update(state.get('full_cache', {}))
            
            cache.exact_cache.update(state.get('exact_cache', {}))
            personalization.user_profiles.update(state.get('user_profiles', {}))
            
            metrics = state.get('performance_metrics', {})
            monitor.metrics['cache_hits'] = metrics.get('cache_hits', 0)
            monitor.metrics['cache_misses'] = metrics.get('cache_misses', 0)
            monitor.metrics['exact_hits'] = metrics.get('exact_hits', 0)
            
            log_success(f"Loaded cold state: {len(getattr(cache, 'cache', cache.exact_cache))} cache entries, {len(personalization.user_profiles)} profiles.")
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
