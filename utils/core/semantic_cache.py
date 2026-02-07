import json
import re
import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from utils.infrastructure.logging.kaia_logger import log_warning

class ImprovedSemanticCache:
    """Enhanced semantic cache with keyword pollution protection"""
    
    def __init__(self, threshold: float = 0.99):
        self.cache = {}
        self.exact_cache = {} # For compatibility with PersistentStateManager
        self.access_counts = {} # For compatibility with IntelligentCacheInvalidator
        self.threshold = threshold
        self.load_exceptions()
        self.load()
        self.performance_monitor = None # Set after initialization
    
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
    
    def get(self, query: str, classification: str, user_id: str) -> Optional[str]:
        """Get cached response if available and relevant"""
        if not self.should_cache_query(query, classification):
            if self.performance_monitor and hasattr(self.performance_monitor, 'record_miss'):
                self.performance_monitor.record_miss()
            return None
        
        cache_key = self.get_cache_key(query, user_id)
        
        # Check for exact match first
        if cache_key in self.cache:
            entry = self.cache[cache_key]
            # Check if entry is expired (24 hours for news, 7 days for others)
            expiry_hours = 24 if any(word in query.lower() for word in ["news", "headline"]) else 168
            if datetime.now() - datetime.fromisoformat(entry["timestamp"]) < timedelta(hours=expiry_hours):
                if self.performance_monitor and hasattr(self.performance_monitor, 'record_hit'):
                    self.performance_monitor.record_hit(exact=True)
                return entry["response"]
        
        # Check for semantic similarity (existing logic)
        for cached_query, entry in self.cache.items():
            # Extract user_id from cached key safely
            cached_user_id = cached_query.split(':', 1)[0] if ':' in cached_query else None
            if cached_user_id != user_id:
                continue

            similarity = self.calculate_similarity(cache_key, cached_query)
            
            # Higher threshold for specific query types or very short queries
            required_threshold = self.threshold
            if any(word in query.lower() for word in ["news", "headline", "learned", "doing", "up to", "think", "see", "view"]):
                required_threshold = 0.995
            
            # Very short queries (under 30 chars) must be nearly identical
            if len(query) < 30:
                required_threshold = max(required_threshold, 0.99)
            
            if similarity >= required_threshold:
                # Additional check: don't return cached news for different dates
                if self.is_different_news(query, cached_query):
                    continue
                if self.performance_monitor and hasattr(self.performance_monitor, 'record_hit'):
                    self.performance_monitor.record_hit()
                return entry["response"]
        
        if self.performance_monitor and hasattr(self.performance_monitor, 'record_miss'):
            self.performance_monitor.record_miss()
        return None
    
    def is_different_news(self, query1: str, query2: str) -> bool:
        """Check if two news queries are about different dates/topics"""
        # Extract dates
        date_pattern = r'\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},\s+\d{4}\b'
        
        date1 = re.search(date_pattern, query1, re.IGNORECASE)
        date2 = re.search(date_pattern, query2, re.IGNORECASE)
        
        # If both have dates and they're different, they're different news
        if date1 and date2 and date1.group(0).lower() != date2.group(0).lower():
            return True
        
        # Check for different years
        year1 = re.search(r'\b\d{4}\b', query1)
        year2 = re.search(r'\b\d{4}\b', query2)
        if year1 and year2 and year1.group(0) != year2.group(0):
            return True
        
        return False
    
    def set(self, query: str, classification: str, response: str, user_id: str):
        """Cache a response with user isolation"""
        if not self.should_cache_query(query, classification):
            return
        
        # PREVENTIVE FILTERING: Never cache hallucinations
        # NOTE: Circular import issue avoid - HallucinationDetector check should happen in the logic layer
        # if HallucinationDetector.contains_hallucination(response):
        #     log_warning(f"Hallucination detected in response for {user_id}. Refusing to cache.")
        #     return
        
        cache_key = self.get_cache_key(query, user_id)
        
        self.cache[cache_key] = {
            "response": response,
            "timestamp": datetime.now().isoformat(),
            "classification": classification,
            "user_id": user_id,
            "original_query": query[:200]  # Store original for debugging
        }
        
        # Sync with exact_cache for PersistentStateManager compatibility
        self.exact_cache[cache_key] = response
        
        # Limit cache size
        if len(self.cache) > 1000:
            # Remove oldest entries
            sorted_entries = sorted(self.cache.items(), 
                                   key=lambda x: x[1]["timestamp"])
            for key, _ in sorted_entries[:100]:
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
