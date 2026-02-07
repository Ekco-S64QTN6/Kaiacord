import numpy as np
import asyncio
from llama_index.embeddings.ollama import OllamaEmbedding
from utils.infrastructure.logging.kaia_logger import log_warning, log_info, log_debug, log_success

class ImprovedSemanticCache:
    """Enhanced semantic cache with embedding similarity and intent isolation"""
    
    def __init__(self, threshold: float = 0.85): # Lower threshold for embeddings
        self.cache = {}
        self.exact_cache = {} 
        self.threshold = threshold
        
        # Initialize embedding model
        self.embed_model = OllamaEmbedding(
            model_name="nomic-embed-text",
            base_url="http://localhost:11434"
        )
        
        self.load_exceptions()
        self.load()
        self.performance_monitor = None
    
    def set_performance_monitor(self, monitor):
        self.performance_monitor = monitor

    def load_exceptions(self):
        """Load cache exceptions from file"""
        try:
            with open("config/cache_exceptions.json", "r") as f:
                self.exceptions = json.load(f)
        except:
            # Default exceptions
            self.exceptions = {
                    "never_cache": [
                        "news", "update", "breaking", "latest", "what's new",
                        "whats new", "recently learned", "what have you", "learned recently",
                        "doing lately", "up to lately", "who am i", "what do you know about me",
                        "my name", "my pronoun", "my profile", "hydroponics"
                    ],
                "always_regenerate": ["news", "headline", "report", "update", "learned", "dream"],
                "keyword_blacklist": []
            }
    
    def should_cache_query(self, query: str, classification: str) -> bool:
        """
        Determine if a query should be cached.
        """
        # 1. Bypass for social/casual categories
        if classification in ["SOCIAL", "CASUAL", "GREETING"]:
            return False
            
        # 2. Bypass for very short queries
        if len(query.strip()) < 20:
            return False
            
        # 3. Bypass for identity queries
        identity_keywords = ["who are you", "who am i", "your name", "tell me about yourself"]
        if any(kw in query.lower() for kw in identity_keywords):
            return False
            
        return True
    
    def get_cache_key(self, query: str, user_id: str) -> str:
        """Create a normalized cache key with user isolation"""
        # Remove extra whitespace
        normalized = ' '.join(query.strip().split())
        
        # Remove specific date patterns
        normalized = re.sub(r'\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},\s+\d{4}\b', 
                          '[DATE]', normalized, flags=re.IGNORECASE)
        
        # Remove years
        normalized = re.sub(r'\b\d{4}\b', '[YEAR]', normalized)
        
        # Remove numbers in headlines
        normalized = re.sub(r'\b\d+\b', '[NUMBER]', normalized)
        
        return f"{user_id}:{normalized.lower()}"
    
    async def get(self, query: str, classification: str, user_id: str) -> Optional[str]:
        """Get cached response using embedding similarity and intent isolation"""
        if not self.should_cache_query(query, classification):
            return None
        
        # Calculate embedding for the current query
        try:
            query_embedding = self.embed_model.get_query_embedding(query)
        except Exception as e:
            log_warning(f"Cache embedding failed: {e}")
            return None

        best_similarity = -1.0
        best_response = None
        
        # Filter cache by user and intent category
        for cached_key, entry in self.cache.items():
            # Isolation check: Must match user AND category (intent)
            # This prevents technical answers from hitting social greetings
            if entry.get("user_id") != user_id:
                continue
            
            # Category isolation (Strongest guard)
            cached_category = entry.get("classification", "GENERAL").lower()
            current_category = classification.lower()
            
            # Categories must be related to share cache
            # e.g., 'tech' can hit 'general', but 'greeting' cannot hit 'tech'
            if cached_category != current_category:
                related = {
                    'general': ['tech', 'news', 'entity'],
                    'social_identity': ['identity'],
                    'identity': ['social_identity']
                }
                if current_category not in related.get(cached_category, []):
                    continue

            # Semantic similarity check
            cached_emb = entry.get("embedding")
            if not cached_emb:
                continue # Skip legacy entries without embeddings
                
            similarity = self._cosine_similarity(query_embedding, cached_emb)
            
            # Dynamic threshold based on length and category
            required_threshold = self.threshold
            if len(query) < 30: required_threshold = 0.95 # Higher for short queries
            if current_category == "news": required_threshold = 0.98 # Very strict for news
            
            if similarity >= required_threshold and similarity > best_similarity:
                # Additional check: don't return cached news for different dates
                if self.is_different_news(query, entry.get("original_query", "")):
                    continue
                best_similarity = similarity
                best_response = entry["response"]
        
        if best_response:
            if self.performance_monitor: self.performance_monitor.record_hit()
            log_debug(f"Semantic Cache HIT (Sim: {best_similarity:.4f})")
            return best_response
            
        return None
    
    def _cosine_similarity(self, a, b) -> float:
        """Calculate cosine similarity between two vectors"""
        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        return dot_product / (norm_a * norm_b) if norm_a > 0 and norm_b > 0 else 0.0
    
    async def set(self, query: str, classification: str, response: str, user_id: str):
        """Cache a response with embedding and isolation metadata"""
        if not self.should_cache_query(query, classification):
            return
        
        try:
            embedding = self.embed_model.get_text_embedding(query)
        except Exception as e:
            log_warning(f"Cache embedding failed during set: {e}")
            return

        cache_key = self.get_cache_key(query, user_id)
        
        self.cache[cache_key] = {
            "response": response,
            "embedding": embedding,
            "timestamp": datetime.now().isoformat(),
            "classification": classification,
            "user_id": user_id,
            "original_query": query[:200]
        }
        
        # Sync for exact cache
        self.exact_cache[cache_key] = response
        
        # SMART PERSISTENCE: Save every time for now given the critical nature
        self.save()

        # Limit cache size (LRU)
        if len(self.cache) > 2000:
            sorted_entries = sorted(self.cache.items(), key=lambda x: x[1]["timestamp"])
            for key, _ in sorted_entries[:200]:
                del self.cache[key]
    
    def calculate_similarity(self, query1: str, query2: str) -> float:
        """Calculate similarity between two queries"""
        # Simple Jaccard similarity for now
        # In production, you'd use embeddings
        words1 = set(query1.lower().split())
        words2 = set(query2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return intersection / union
    
    def save(self):
        """Save cache to disk"""
        memory_dir = "memory"
        if not os.path.exists(memory_dir):
            os.makedirs(memory_dir)
            
        with open(os.path.join(memory_dir, "semantic_cache.json"), "w") as f:
            json.dump(self.cache, f, indent=2)
    
    def load(self):
        """Load cache from disk"""
        try:
            cache_path = os.path.join("memory", "semantic_cache.json")
            if os.path.exists(cache_path):
                with open(cache_path, "r") as f:
                    self.cache = json.load(f)
        except:
            self.cache = {}

    def invalidate_exact(self, query):
        """For compatibility with IntelligentCacheInvalidator"""
        # Note: This needs user_id to be truly compatible, or we scan all user_ids
        # For simple invalidation, we might just clear based on normalized string
        normalized = ' '.join(query.strip().split()).lower()
        keys_to_del = [k for k in self.cache.keys() if normalized in k]
        for k in keys_to_del:
            del self.cache[k]
        return len(keys_to_del) > 0

    def invalidate_semantic_by_query(self, query):
        """For compatibility with IntelligentCacheInvalidator"""
        return self.invalidate_exact(query)
