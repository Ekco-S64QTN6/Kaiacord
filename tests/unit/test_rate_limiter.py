import time
from collections import defaultdict
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mocking the RateLimiter class from Kaiacord.py for isolated testing
# In a real scenario, we might import it, but it's embedded in Kaiacord.py
class RateLimiter:
    """Per-user rate limiting"""
    def __init__(self, requests_per_minute: int = 30):
        self.requests = defaultdict(list)
        self.limit = requests_per_minute
        
    def is_allowed(self, user_id: int) -> bool:
        now = time.time()
        user_requests = self.requests[user_id]
        
        # Remove old requests
        user_requests = [req for req in user_requests if now - req < 60]
        self.requests[user_id] = user_requests
        
        if len(user_requests) >= self.limit:
            return False
            
        user_requests.append(now)
        return True

    def cleanup(self):
        """Fixed cleanup that maintains defaultdict"""
        now = time.time()
        to_remove = [uid for uid, reqs in self.requests.items() 
                     if not reqs or now - max(reqs) >= 300]
        for uid in to_remove:
            del self.requests[uid]

def test_rate_limiter():
    print("Testing RateLimiter...")
    rl = RateLimiter()
    
    # Add a user
    rl.is_allowed(123)
    print("User 123 allowed")
    
    # Run cleanup
    print("Running cleanup...")
    rl.cleanup()
    
    try:
        print("Testing new user 456...")
        rl.is_allowed(456)
        print("✅ User 456 allowed after cleanup!")
    except KeyError:
        print("❌ Caught KeyError after cleanup!")
        sys.exit(1)

if __name__ == "__main__":
    test_rate_limiter()
