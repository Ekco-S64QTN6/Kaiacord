import time
import asyncio
import threading
from enum import Enum
from typing import Callable, Any, Optional
from utils.infrastructure.logging.kaia_logger import log_info, log_warning, log_error

class CircuitState(Enum):
    CLOSED = "CLOSED"      # Normal operation
    OPEN = "OPEN"          # Failed, blocking requests
    HALF_OPEN = "HALF_OPEN" # Testing if service recovered

class CircuitBreaker:
    """
    Standardized Circuit Breaker with support for both sync and async operations.
    Prevents cascading failures by blocking calls to a failing service.
    """
    def __init__(self, 
                 name: str, 
                 failure_threshold: int = 5, 
                 recovery_timeout: float = 60.0):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        
        self.state = CircuitState.CLOSED
        self.failures = 0
        self.last_failure_time: Optional[float] = None
        self._lock = threading.Lock()  # Use thread lock for both sync and async compatibility

    def can_proceed(self) -> bool:
        """Sync check if calls should be allowed through."""
        with self._lock:
            if self.state == CircuitState.CLOSED:
                return True
            
            if self.state == CircuitState.OPEN:
                if time.time() - self.last_failure_time > self.recovery_timeout:
                    log_warning(f"[CIRCUIT BREAKER] {self.name} entering HALF_OPEN state.")
                    self.state = CircuitState.HALF_OPEN
                    return True
                return False
            
            if self.state == CircuitState.HALF_OPEN:
                # In half-open, we allow one trial call. 
                # For simplicity, we just return True and let the next record_ success/failure handle it.
                return True
                
            return False

    def record_success(self) -> None:
        """Record a successful call — resets failure counter."""
        with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                log_info(f"[CIRCUIT BREAKER] {self.name} RECOVERED. Closing circuit.")
            elif self.state == CircuitState.OPEN:
                log_info(f"[CIRCUIT BREAKER] {self.name} manually recovered. Closing circuit.")
            
            self.state = CircuitState.CLOSED
            self.failures = 0
            self.last_failure_time = None

    def record_failure(self) -> None:
        """Record a failed call — opens the breaker after threshold."""
        with self._lock:
            self.failures += 1
            self.last_failure_time = time.time()
            
            if self.failures >= self.failure_threshold:
                if self.state != CircuitState.OPEN:
                    log_error(f"[CIRCUIT BREAKER] {self.name} TRIPPED! Opening circuit for {self.recovery_timeout}s.")
                    self.state = CircuitState.OPEN

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Async wrapper for unified usage."""
        if not self.can_proceed():
            raise RuntimeWarning(f"Circuit breaker {self.name} is OPEN.")

        try:
            # Check if it's a coroutine function
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            self.record_success()
            return result
            
        except Exception as e:
            self.record_failure()
            raise e
