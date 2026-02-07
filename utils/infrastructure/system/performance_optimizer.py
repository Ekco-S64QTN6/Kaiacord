import asyncio
import time
from functools import wraps

def timed_response(threshold=30.0):
    """Decorator to log slow responses"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.time()
            result = await func(*args, **kwargs)
            elapsed = time.time() - start
            
            if elapsed > threshold:
                print(f"⚠️ Slow response: {func.__name__} took {elapsed:.2f}s")
            
            return result
        return wrapper
    return decorator

class ResponseOptimizer:
    """Optimize response times with caching and prioritization"""
    
    def __init__(self):
        self.response_cache = {}
        self.cache_ttl = 30  # 30 seconds
        
    async def get_optimized_response(self, query, response_func, *args, **kwargs):
        """Get response with caching"""
        # Create cache key
        cache_key = hash(query)
        
        # Check cache
        if cache_key in self.response_cache:
            cached_time, response = self.response_cache[cache_key]
            if time.time() - cached_time < self.cache_ttl:
                return response
        
        # Get fresh response
        response = await response_func(*args, **kwargs)
        
        # Cache it
        self.response_cache[cache_key] = (time.time(), response)
        
        return response
