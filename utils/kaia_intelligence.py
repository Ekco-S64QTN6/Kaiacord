import time
import asyncio
import numpy as np
from datetime import datetime
from llama_index.embeddings.ollama import OllamaEmbedding
from utils.kaia_logger import log_info, log_action, log_success, log_error

class SemanticCache:
    """Cache semantically similar queries to avoid redundant LLM calls."""
    def __init__(self, model_name="nomic-embed-text", max_size=100, threshold=0.80):
        self.cache = {}
        self.embed_model = OllamaEmbedding(model_name=model_name)
        self.max_size = max_size
        self.threshold = threshold
        
    def cosine_similarity(self, a, b):
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
        
    async def get(self, query, user_id=None):
        """Get cached response for similar query."""
        if not self.cache:
            return None
            
        try:
            query_embedding = await self.embed_model.aget_text_embedding(query)
        except Exception as e:
            log_error(f"Error generating embedding for cache: {e}")
            return None
        
        best_match = None
        highest_similarity = -1
        
        for cached_query, data in self.cache.items():
            # Check if same user context if provided
            if user_id and data.get('user_id') and data['user_id'] != user_id:
                continue
                
            similarity = self.cosine_similarity(query_embedding, data['embedding'])
            
            if similarity > highest_similarity:
                highest_similarity = similarity
                best_match = data
        
        if highest_similarity >= self.threshold:
            # Age-based decay (24-hour half-life)
            age = time.time() - best_match['timestamp']
            decay = max(0.5, 1 - (age / 86400))
            
            if highest_similarity * decay >= self.threshold:
                log_success(f"Semantic cache hit: {highest_similarity:.3f} (decayed: {highest_similarity * decay:.3f})")
                return best_match['response']
                
        return None
    
    async def set(self, query, response, user_id=None):
        """Cache query-response pair."""
        try:
            if len(self.cache) >= self.max_size:
                # Remove oldest
                oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k]['timestamp'])
                del self.cache[oldest_key]
            
            query_embedding = await self.embed_model.aget_text_embedding(query)
            
            self.cache[query] = {
                'embedding': query_embedding,
                'response': response,
                'user_id': user_id,
                'timestamp': time.time()
            }
        except Exception as e:
            log_error(f"Error setting semantic cache: {e}")

class ModelWarmPool:
    """Keep models warm between uses to prevent cold starts."""
    def __init__(self, ollama_client):
        self.ollama_client = ollama_client
        self.pool = {}
        self.keep_alive_tasks = {}
        
    async def pre_warm(self, model_name):
        """Pre-warm a model with a simple query."""
        if model_name in self.pool:
            self.pool[model_name]['last_used'] = time.time()
            return True
            
        log_action(f"Pre-warming model: {model_name}...")
        try:
            # Use a very short query to load the model
            await self.ollama_client.chat(
                model=model_name,
                messages=[{"role": "user", "content": "ready?"}],
                options={"num_predict": 1}
            )
            self.pool[model_name] = {
                'last_used': time.time(),
                'status': 'ready'
            }
            
            # Start keep-alive task
            if model_name not in self.keep_alive_tasks:
                self.keep_alive_tasks[model_name] = asyncio.create_task(
                    self.keep_alive(model_name)
                )
            return True
        except Exception as e:
            log_error(f"Failed to pre-warm model {model_name}: {e}")
            return False
    
    async def keep_alive(self, model_name):
        """Send periodic keep-alive queries."""
        while True:
            await asyncio.sleep(300)  # Every 5 minutes
            if model_name not in self.pool:
                break
                
            # If not used for 30 minutes, let it unload
            if time.time() - self.pool[model_name]['last_used'] > 1800:
                log_info(f"Model {model_name} idle for 30m, stopping keep-alive.")
                del self.pool[model_name]
                break
                
            try:
                await self.ollama_client.chat(
                    model=model_name,
                    messages=[{"role": "user", "content": "ping"}],
                    options={"num_predict": 1}
                )
            except Exception:
                if model_name in self.pool:
                    del self.pool[model_name]
                break

class QueryClassifier:
    """Fast classification for routing decisions using a small model."""
    def __init__(self, ollama_client, model_name="gemma2:2b"):
        self.ollama_client = ollama_client
        self.model_name = model_name
        self.categories = ['casual', 'identity', 'knowledge', 'memory', 'creative', 'command']
    
    async def classify(self, query):
        """Classify query into a category."""
        system_prompt = (
            "Classify the user query into ONE primary category.\n"
            "Categories: casual, identity, knowledge, memory, creative, command.\n"
            "Respond with ONLY the category name."
        )
        
        try:
            response = await self.ollama_client.chat(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query}
                ],
                options={
                    "temperature": 0.1,
                    "num_predict": 10
                }
            )
            category = response['message']['content'].strip().lower()
            # Clean up potential punctuation or extra words
            for cat in self.categories:
                if cat in category:
                    return cat
            return 'knowledge'
        except Exception as e:
            log_error(f"Classification error: {e}")
            return 'knowledge'

class ContextOptimizer:
    """Allocate tokens based on query type and trim context."""
    def __init__(self, max_tokens=6000):
        self.max_tokens = max_tokens
        
    def optimize_context(self, category, persona, rag_nodes, history):
        """Allocate tokens based on query type."""
        token_budget = {
            'persona': 500 if category in ['casual', 'identity'] else 300,
            'rag': 3000 if category == 'knowledge' else 1500,
            'history': 2000 if category == 'memory' else 800,
            'system': 200,
            'buffer': 500
        }
        
        optimized_persona = self.trim_to_tokens(persona, token_budget['persona'])
        # rag_nodes is expected to be a list of strings or objects with text
        rag_text = "\n\n".join([n.text if hasattr(n, 'text') else str(n) for n in rag_nodes])
        optimized_rag = self.trim_to_tokens(rag_text, token_budget['rag'])
        
        # history is expected to be a list of dicts or strings
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
            'history': optimized_history
        }
    
    def trim_to_tokens(self, text, max_tokens):
        """Smart token-aware trimming (approximate)."""
        words = text.split()
        # Rough estimation: 1.3 tokens per word
        if len(words) * 1.3 <= max_tokens:
            return text
            
        # Preserve important sections (lines with markers)
        lines = text.split('\n')
        important_lines = [l for l in lines if any(marker in l.lower() for marker in ['###', 'important:', 'core:', 'rule:'])]
        
        # Calculate remaining budget
        important_tokens = sum(len(l.split()) * 1.3 for l in important_lines)
        remaining_tokens = max_tokens - important_tokens
        
        if remaining_tokens <= 0:
            return '\n'.join(important_lines[:5]) # Fallback to first few important lines
            
        regular_lines = []
        # Take regular lines from the end (most recent usually)
        for line in reversed(lines):
            if line not in important_lines:
                line_tokens = len(line.split()) * 1.3
                if line_tokens <= remaining_tokens:
                    regular_lines.insert(0, line)
                    remaining_tokens -= line_tokens
                else:
                    break
                    
        return '\n'.join(important_lines + regular_lines)

class RelevanceFeedback:
    """Learn from user interactions to improve retrieval."""
    def __init__(self, rag):
        self.rag = rag
        self.feedback_log = []
        
    async def log_interaction(self, query, response, user_id):
        """Log interaction for future learning."""
        self.feedback_log.append({
            'query': query,
            'response': response,
            'user_id': user_id,
            'timestamp': time.time()
        })
        
        # Periodically "learn" (every 50 interactions)
        if len(self.feedback_log) >= 50:
            await self.process_feedback()
            
    async def process_feedback(self):
        """Convert successful interactions into synthetic knowledge."""
        log_action("Processing relevance feedback to improve RAG...")
        # For now, we just take the last 50 and treat them as successful Q&A pairs
        # In a real scenario, we might look for positive user sentiment
        recent_pairs = self.feedback_log[-50:]
        self.feedback_log = [] # Clear log
        
        from llama_index.core import Document
        synthetic_docs = []
        for item in recent_pairs:
            doc = Document(
                text=f"User Query: {item['query']}\nKaia Response: {item['response']}",
                metadata={
                    'source': 'feedback',
                    'type': 'successful_qa',
                    'user_id': str(item['user_id']),
                    'timestamp': item['timestamp']
                }
            )
            synthetic_docs.append(doc)
            
        if synthetic_docs:
            # Insert into logs index
            try:
                # We use the rag's internal method to add documents
                # This will use the correct node parser for logs
                for doc in synthetic_docs:
                    await asyncio.to_thread(self.rag.logs_index.insert, doc)
                log_success(f"Added {len(synthetic_docs)} feedback nodes to RAG.")
            except Exception as e:
                log_error(f"Error adding feedback to RAG: {e}")
