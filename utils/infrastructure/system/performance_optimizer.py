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
                from utils.infrastructure.logging.kaia_logger import log_warning
                log_warning(f"Slow response: {func.__name__} took {elapsed:.2f}s")
            
            return result
        return wrapper
    return decorator
