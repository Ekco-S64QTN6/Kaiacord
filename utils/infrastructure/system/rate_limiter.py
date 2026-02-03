"""
Rate Limiter
============

Per-user rate limiting to prevent abuse.

Extracted from Kaiacord.py to improve modularity.
"""

import time
from collections import defaultdict
from typing import Dict, List


class RateLimiter:
    """Per-user rate limiting"""
    def __init__(self, requests_per_minute: int = 30):
        self.requests: Dict[int, List[float]] = defaultdict(list)
        self.limit = requests_per_minute
        
    def is_allowed(self, user_id: int) -> bool:
        """
        Check if user is allowed to make a request.
        
        Args:
            user_id: Discord user ID
            
        Returns:
            True if request is allowed, False if rate limited
        """
        now = time.time()
        user_requests = self.requests[user_id]
        
        # Remove old requests (outside the 1-minute window)
        user_requests = [req for req in user_requests if now - req < 60]
        self.requests[user_id] = user_requests
        
        if len(user_requests) >= self.limit:
            return False
            
        user_requests.append(now)
        return True

    def cleanup(self):
        """
        Remove inactive users to prevent unbounded memory growth.
        
        Should be called periodically (e.g., every 5 minutes).
        """
        now = time.time()
        # Remove users with no requests in the last 5 minutes
        to_remove = [uid for uid, reqs in self.requests.items() 
                     if not reqs or now - max(reqs) >= 300]
        for uid in to_remove:
            del self.requests[uid]
    
    def get_remaining(self, user_id: int) -> int:
        """
        Get remaining requests for a user.
        
        Args:
            user_id: Discord user ID
            
        Returns:
            Number of remaining requests in current minute
        """
        now = time.time()
        user_requests = self.requests[user_id]
        
        # Remove old requests
        user_requests = [req for req in user_requests if now - req < 60]
        self.requests[user_id] = user_requests
        
        return max(0, self.limit - len(user_requests))
