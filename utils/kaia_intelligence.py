import time
import asyncio
import numpy as np
import re
from datetime import datetime
from llama_index.embeddings.ollama import OllamaEmbedding
from utils.kaia_logger import log_info, log_action, log_success, log_error

class PerformanceMonitor:
    """Track and report system performance metrics."""
    def __init__(self):
        self.metrics = {
            'cache_hits': 0,
            'cache_misses': 0,
            'exact_hits': 0,
            'classification_time': [],
            'retrieval_time': [],
            'response_time': [],
        }
        self.start_times = {}
        
    def start_timer(self, key):
        self.start_times[key] = time.time()
        
    def stop_timer(self, key, metric_name):
        if key in self.start_times:
            duration = (time.time() - self.start_times[key]) * 1000 # ms
            self.metrics[metric_name].append(duration)
            del self.start_times[key]
            return duration
        return 0

    def record_hit(self, exact=False):
        self.metrics['cache_hits'] += 1
        if exact:
            self.metrics['exact_hits'] += 1
            
    def record_miss(self):
        self.metrics['cache_misses'] += 1

    def get_report(self):
        total = self.metrics['cache_hits'] + self.metrics['cache_misses']
        hit_rate = (self.metrics['cache_hits'] / total * 100) if total > 0 else 0
        exact_rate = (self.metrics['exact_hits'] / total * 100) if total > 0 else 0
        
        avg_classify = np.mean(self.metrics['classification_time'][-50:]) if self.metrics['classification_time'] else 0
        avg_retrieval = np.mean(self.metrics['retrieval_time'][-50:]) if self.metrics['retrieval_time'] else 0
        avg_response = np.mean(self.metrics['response_time'][-50:]) if self.metrics['response_time'] else 0
        
        return (
            f"\n⚡ Kaia 2.0 Performance Report ⚡\n"
            f"Cache Hit Rate: {hit_rate:.1f}% (Exact: {exact_rate:.1f}%)\n"
            f"Avg Classification: {avg_classify:.0f}ms\n"
            f"Avg Retrieval: {avg_retrieval:.0f}ms\n"
            f"Avg Response: {avg_response:.0f}ms\n"
            f"Total Queries: {total}"
        )

class SemanticCache:
    """Two-level cache: Exact match (fast) + Semantic match (embeddings)."""
    def __init__(self, model_name="nomic-embed-text", max_size=200, threshold=0.80):
        self.exact_cache = {} # {user_id:query_hash: response}
        self.cache = {} # {query: data}
        self.embed_model = OllamaEmbedding(model_name=model_name)
        self.max_size = max_size
        self.threshold = threshold
        
    def _get_exact_key(self, query, user_id):
        return f"{user_id}:{query.strip().lower()}"

    def cosine_similarity(self, a, b):
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
        
    async def get(self, query, user_id=None, monitor=None):
        """Get cached response for similar query."""
        # Level 1: Exact Match
        exact_key = self._get_exact_key(query, user_id)
        if exact_key in self.exact_cache:
            log_success(f"Exact cache hit for user {user_id}")
            if monitor: monitor.record_hit(exact=True)
            return self.exact_cache[exact_key]

        # Level 2: Semantic Match
        if not self.cache:
            if monitor: monitor.record_miss()
            return None
            
        try:
            query_embedding = await self.embed_model.aget_text_embedding(query)
        except Exception as e:
            log_error(f"Error generating embedding for cache: {e}")
            if monitor: monitor.record_miss()
            return None
        
        best_match = None
        highest_similarity = -1
        
        for cached_query, data in self.cache.items():
            if user_id and data.get('user_id') and data['user_id'] != user_id:
                continue
                
            similarity = self.cosine_similarity(query_embedding, data['embedding'])
            if similarity > highest_similarity:
                highest_similarity = similarity
                best_match = data
        
        if highest_similarity >= self.threshold:
            age = time.time() - best_match['timestamp']
            decay = max(0.5, 1 - (age / 86400))
            
            if highest_similarity * decay >= self.threshold:
                log_success(f"Semantic cache hit: {highest_similarity:.3f}")
                if monitor: monitor.record_hit()
                return best_match['response']
        
        if monitor: monitor.record_miss()
        return None
    
    async def set(self, query, response, user_id=None):
        """Cache query-response pair in both levels."""
        try:
            # Set Exact
            exact_key = self._get_exact_key(query, user_id)
            self.exact_cache[exact_key] = response
            
            # Set Semantic
            if len(self.cache) >= self.max_size:
                oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k]['timestamp'])
                del self.cache[oldest_key]
                # Also prune exact cache if it gets too large
                if len(self.exact_cache) > self.max_size * 2:
                    self.exact_cache.clear()
            
            query_embedding = await self.embed_model.aget_text_embedding(query)
            self.cache[query] = {
                'embedding': query_embedding,
                'response': response,
                'user_id': user_id,
                'timestamp': time.time()
            }
        except Exception as e:
            log_error(f"Error setting cache: {e}")

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
            await self.ollama_client.chat(
                model=model_name,
                messages=[{"role": "user", "content": "ready?"}],
                options={"num_predict": 1}
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
                await self.ollama_client.chat(model=model_name, messages=[{"role": "user", "content": "ping"}], options={"num_predict": 1})
            except Exception:
                if model_name in self.pool: del self.pool[model_name]
                break

class QueryClassifier:
    """Hybrid classification: Rules (fast) + Model (accurate)."""
    def __init__(self, ollama_client, model_name="gemma2:2b"):
        self.ollama_client = ollama_client
        self.model_name = model_name
        self.rules = [
            (r'^(hi|hello|hey|sup|yo|morning|evening|greetings)', 'casual'),
            (r'who (am i|is (kaia|you))', 'identity'),
            (r'(my|your) (name|pronoun|profile|history)', 'identity'),
            (r'(draw|paint|generate|create).*(image|picture|art)', 'command'),
            (r'(analyze|look at|describe|what is in).*(image|picture|this)', 'command'), # Routes to vision
            (r'(do you|can you) remember', 'memory'),
            (r'what did (i|we) say', 'memory'),
        ]
    
    async def classify(self, query):
        """Classify query using rules first, then model."""
        query_lower = query.lower().strip()
        
        # 1. Rule-based (Fast)
        for pattern, category in self.rules:
            if re.search(pattern, query_lower):
                log_info(f"Rule-based classification: {category}")
                return category
        
        # 2. Model-based (Accurate)
        system_prompt = (
            "Classify the user query into ONE primary category.\n"
            "Categories: casual, identity, knowledge, memory, creative, command.\n"
            "Respond with ONLY the category name."
        )
        
        try:
            response = await self.ollama_client.chat(
                model=self.model_name,
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": query}],
                options={"temperature": 0.1, "num_predict": 10}
            )
            category = response['message']['content'].strip().lower()
            for cat in ['casual', 'identity', 'knowledge', 'memory', 'creative', 'command']:
                if cat in category: return cat
            return 'knowledge'
        except Exception as e:
            log_error(f"Classification error: {e}")
            return 'knowledge'

class ContextOptimizer:
    """Model-aware token allocation and context trimming."""
    def __init__(self, model_name="gemma3:12b", max_tokens=6000):
        self.model_name = model_name
        self.max_tokens = max_tokens
        # Optimal ratios for different models
        self.ratios = {
            'gemma3:12b': {'persona': 0.10, 'rag': 0.50, 'history': 0.35, 'system': 0.05},
            'llama3.2': {'persona': 0.15, 'rag': 0.45, 'history': 0.35, 'system': 0.05},
            'default': {'persona': 0.10, 'rag': 0.50, 'history': 0.30, 'system': 0.10}
        }
        
    def optimize_context(self, category, persona, rag_nodes, history):
        model_ratios = self.ratios.get(self.model_name, self.ratios['default'])
        
        # Adjust ratios based on category
        if category == 'identity':
            model_ratios['persona'] += 0.10
            model_ratios['rag'] += 0.10
            model_ratios['history'] -= 0.20
        elif category == 'memory':
            model_ratios['history'] += 0.20
            model_ratios['rag'] -= 0.20
            
        token_budget = {k: int(v * self.max_tokens) for k, v in model_ratios.items()}
        
        optimized_persona = self.trim_to_tokens(persona, token_budget['persona'])
        rag_text = "\n\n".join([n.text if hasattr(n, 'text') else str(n) for n in rag_nodes])
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
            'tokens_saved': self.max_tokens - (len(optimized_persona.split()) + len(optimized_rag.split()) + len(optimized_history.split())) * 1.3
        }
    
    def trim_to_tokens(self, text, max_tokens):
        words = text.split()
        if len(words) * 1.3 <= max_tokens: return text
            
        lines = text.split('\n')
        important_lines = [l for l in lines if any(marker in l.lower() for marker in ['###', 'important:', 'core:', 'rule:'])]
        important_tokens = sum(len(l.split()) * 1.3 for l in important_lines)
        remaining_tokens = max_tokens - important_tokens
        
        if remaining_tokens <= 0: return '\n'.join(important_lines[:5])
            
        regular_lines = []
        for line in reversed(lines):
            if line not in important_lines:
                line_tokens = len(line.split()) * 1.3
                if line_tokens <= remaining_tokens:
                    regular_lines.insert(0, line)
                    remaining_tokens -= line_tokens
                else: break
        return '\n'.join(important_lines + regular_lines)

class RelevanceFeedback:
    """Learn from user interactions to improve retrieval."""
    def __init__(self, rag):
        self.rag = rag
        self.feedback_log = []
        
    async def log_interaction(self, query, response, user_id):
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
