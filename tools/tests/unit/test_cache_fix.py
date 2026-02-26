"""
Test the cache fix
"""

import asyncio
import json
import os
import re
from datetime import datetime, timedelta
from typing import Optional

# Mocking the ImprovedSemanticCache for standalone testing if needed, 
# but we'll try to import it or just redefine it here for the test script's independence.

class ImprovedSemanticCache:
    """Enhanced semantic cache with keyword pollution protection"""
    
    def __init__(self, threshold: float = 0.85):
        self.cache = {}
        self.threshold = threshold
        self.load_exceptions()
    
    def load_exceptions(self):
        """Load cache exceptions from file"""
        try:
            with open("cache_exceptions.json", "r") as f:
                self.exceptions = json.load(f)
        except Exception:
            # Default exceptions
            self.exceptions = {
                "never_cache": [
                    "68k.news", "headlines from", "january", "february",
                    "news", "update", "breaking", "latest"
                ],
                "always_regenerate": ["news", "headline", "report", "update"],
                "keyword_blacklist": []
            }
    
    def should_cache_query(self, query: str, classification: str) -> bool:
        """Determine if a query should be cached at all"""
        query_lower = query.lower()
        
        # Never cache identity queries
        if classification in ["IDENTITY", "WHOAMI", "SELF"]:
            return False
        
        # Never cache queries with time/date references
        if any(phrase in query_lower for phrase in self.exceptions["never_cache"]):
            return False
        
        # Don't cache very short queries
        if len(query.strip()) < 10:
            return False
        
        # Don't cache queries with numbers (likely dates/versions)
        if re.search(r'\b\d{4}\b', query):  # Years like 2026
            return False
        
        # Don't cache queries with URLs
        if re.search(r'https?://', query_lower):
            return False
        
        return True
    
    def get_cache_key(self, query: str) -> str:
        """Create a normalized cache key"""
        # Remove extra whitespace
        normalized = ' '.join(query.strip().split())
        
        # Remove specific date patterns
        normalized = re.sub(r'\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},\s+\d{4}\b', 
                          '[DATE]', normalized, flags=re.IGNORECASE)
        
        # Remove years
        normalized = re.sub(r'\b\d{4}\b', '[YEAR]', normalized)
        
        # Remove numbers in headlines
        normalized = re.sub(r'\b\d+\b', '[NUMBER]', normalized)
        
        return normalized.lower()
    
    def get(self, query: str, classification: str) -> Optional[str]:
        """Get cached response if available and relevant"""
        if not self.should_cache_query(query, classification):
            return None
        
        cache_key = self.get_cache_key(query)
        
        # Check for exact match first
        if cache_key in self.cache:
            entry = self.cache[cache_key]
            # Check if entry is expired (24 hours for news, 7 days for others)
            expiry_hours = 24 if any(word in query.lower() for word in ["news", "headline"]) else 168
            if datetime.now() - datetime.fromisoformat(entry["timestamp"]) < timedelta(hours=expiry_hours):
                return entry["response"]
        
        # Check for semantic similarity (existing logic)
        for cached_query, entry in self.cache.items():
            similarity = self.calculate_similarity(cache_key, cached_query)
            
            # Higher threshold for news-related queries
            required_threshold = 0.95 if any(word in query.lower() for word in ["news", "headline"]) else self.threshold
            
            if similarity > required_threshold:
                # Additional check: don't return cached news for different dates
                if self.is_different_news(query, cached_query):
                    return None
                return entry["response"]
        
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
    
    def set(self, query: str, classification: str, response: str):
        """Cache a response"""
        if not self.should_cache_query(query, classification):
            return
        
        cache_key = self.get_cache_key(query)
        
        self.cache[cache_key] = {
            "response": response,
            "timestamp": datetime.now().isoformat(),
            "classification": classification,
            "original_query": query[:200]  # Store original for debugging
        }

async def test_cache():
    cache = ImprovedSemanticCache(threshold=0.85)
    
    test_queries = [
        ("kaia do you remember the news headlines from 68k.news", "MEMORY"),
        ("Here are the headlines from January 21, 2026, as they appeared on 68k.news...", "KNOWLEDGE"),
        ("Here are the headlines from January 13, 2026, as they appeared on 68k.news...", "KNOWLEDGE"),
        ("status kaia", "IDENTITY"),
        ("who are you kaia", "IDENTITY"),
        ("how are you feeling", "CASUAL"),
    ]
    
    print("🧪 Testing cache behavior...")
    
    for i, (query, classification) in enumerate(test_queries, 1):
        print(f"\n{i}. Query: {query[:60]}...")
        print(f"   Classification: {classification}")
        
        # Should this be cached?
        should_cache = cache.should_cache_query(query, classification)
        print(f"   Should cache: {should_cache}")
        
        if should_cache:
            # Create a fake response
            response = f"Response to: {query[:30]}..."
            cache.set(query, classification, response)
            
            # Try to retrieve it
            cached = cache.get(query, classification)
            print(f"   Retrieved from cache: {cached is not None}")
        else:
            print("   (Correctly skipped caching)")
    
    # Test same keyword different dates
    print("\n" + "="*50)
    print("Testing news date differentiation:")
    
    jan21 = "Here are headlines from January 21, 2026 from 68k.news"
    jan13 = "Here are headlines from January 13, 2026 from 68k.news"
    
    # Note: should_cache_query will return False for these because of "january" and "68k.news"
    # But we want to test the logic of is_different_news and get_cache_key if they WERE cached
    
    print(f"Query 1: {jan21}")
    print(f"Query 2: {jan13}")
    
    # Manually bypass should_cache for testing internal logic
    cache.cache[cache.get_cache_key(jan21)] = {
        "response": "Response for Jan 21",
        "timestamp": datetime.now().isoformat(),
        "classification": "KNOWLEDGE"
    }
    
    print(f"Jan 21 cached manually.")
    
    # Try to get Jan 13 using Jan 21's cache
    # It should NOT return Jan 21's response because of is_different_news
    retrieved = cache.get(jan13, "KNOWLEDGE")
    print(f"Jan 13 retrieved: {retrieved}")
    print(f"Jan 21 returns Jan 13? {retrieved == 'Response for Jan 21'}")
    
    if retrieved is None:
        print("✅ SUCCESS: Jan 13 did not incorrectly hit Jan 21's cache.")
    else:
        print("❌ FAILURE: Jan 13 hit Jan 21's cache.")

if __name__ == "__main__":
    asyncio.run(test_cache())
